"""File-backed test device for registered diagnostic jobs.

This is not a Windows service. Enrolment does not grant repair authority.
The state file must stay outside the source tree.

The in-process lock is not enough when two processes open the same file.
Each public operation also holds a lock file, reloads, and writes back before
releasing it. The collector must not call back into the store: the lock is not
re-entrant. The console records a result. It does not run the collector.
The endpoint worker collects on the enrolled computer, then submits the result.

Permission failures raise. They are not ignored. On Windows the ACL is set and
read back. That ACL does not stop an administrator with take-ownership or
backup privilege, and creating the file is not itself proof of a private ACL.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from integrations.endpoint import assert_safe_state_path
from integrations.state_guard import CrossProcessLock, StateLockError, StatePermissionError, restrict_private
from web.auth.store import SessionRecord

from .engine import RepairDenied
from .providers import LIVE_PROCEDURES

_READ_ONLY = tuple(LIVE_PROCEDURES)
STALE_AFTER_SECONDS = 86400
_FUTURE_SKEW_SECONDS = 120
_FAILED_OUTCOMES = frozenset({"failed", "approval_rejected", "needs_administrator"})
_TERMINAL = frozenset({"accepted", "rejected", "expired", "failed"})
_ISSUING_ROLES = frozenset({"admin", "operator"})
_OPERATOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}\Z")
_SEAL = object()


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


_RESULT_SOURCES = frozenset({"live_windows", "unavailable", "mock", "fixture"})
_SIGNATURE_FIELDS = frozenset({"signature", "device_signature", "result_signature"})


def job_body(envelope: dict[str, Any]) -> dict[str, Any]:
    """Fields covered by the server signature and the device signature."""
    return {key: value for key, value in envelope.items() if key not in _SIGNATURE_FIELDS}


def result_signing_view(result: dict[str, Any], procedure_id: str) -> dict[str, Any]:
    """The result fields the device signs. A repair claim is not one of them."""
    status = str(result.get("status") or "collected")[:40]
    ok = bool(result.get("ok")) if "ok" in result else status == "collected"
    source = result.get("evidence_source")
    if source not in _RESULT_SOURCES:
        source = "unavailable"
    stamp = result.get("collected_at_unix")
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
        stamp = None
    else:
        stamp = int(stamp)
    return {
        "collected_at_unix": stamp,
        "collected_by": "endpoint_worker",
        "evidence_source": source,
        "ok": ok,
        "procedure_id": procedure_id,
        "status": status,
    }


class OperatorGrant:
    """Authority taken from a server-side session. A username string is not a grant."""

    def __init__(
        self,
        *,
        operator_id: str,
        username: str,
        role: str,
        tenant_id: str,
        session_id: str,
        seal: object,
    ) -> None:
        if seal is not _SEAL:
            raise RepairDenied("operator session is required")
        self.operator_id = operator_id
        self.username = username
        self.role = role
        self.tenant_id = tenant_id
        self.session_id = session_id


def _is_project_session(session: Any) -> bool:
    """True only for SessionRecord defined by this repo's auth store.

    The console imports that class as auth.store and the device store imports
    it as web.auth.store. Those are the same file with two module objects, so
    isinstance against one of them rejects a real signed-in session. A class
    with the same fields in any other file still fails.
    """
    cls = type(session)
    if cls.__name__ != "SessionRecord":
        return False
    module = sys.modules.get(cls.__module__)
    source = getattr(module, "__file__", None) if module is not None else None
    if not source:
        return False
    expected = Path(__file__).resolve().parents[1] / "web" / "auth" / "store.py"
    try:
        return Path(source).resolve() == expected
    except OSError:
        return False


def grant_from_session(session: Any, tenant_id: str) -> OperatorGrant:
    """Build a grant from the authenticated session record, never from a request name.

    An object that merely has the same attributes is not a session. The console
    route must pass the SessionRecord returned by the server-side auth store
    after the cookie and CSRF checks, and must not read the operator name from
    the request body.
    """
    if not _is_project_session(session):
        raise RepairDenied("operator session is required")
    session_id = str(session.session_id or "")
    operator_id = str(session.operator_id or "")
    username = str(session.username or "")
    role = str(session.role or "")
    if not session_id or not operator_id or not username or not str(session.csrf_token or ""):
        raise RepairDenied("operator session is required")
    now = time.time()
    if float(session.expires_at) <= now or float(session.absolute_expires_at) <= now:
        raise RepairDenied("operator session is required")
    if role not in _ISSUING_ROLES:
        raise RepairDenied("operator is not authorised to issue a device job")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise RepairDenied("tenant is required")
    if not _OPERATOR.fullmatch(username):
        raise RepairDenied("operator is not authorised to issue a device job")
    return OperatorGrant(
        operator_id=operator_id,
        username=username,
        role=role,
        tenant_id=tenant_id.strip(),
        session_id=session_id,
        seal=_SEAL,
    )


class _Exclusive:
    """Hold the cross-process lock, then the in-process lock, and reload first."""

    def __init__(self, store: "DeviceStore", *, reload: bool) -> None:
        self.store = store
        self.reload = reload
        self._locked = False

    def __enter__(self) -> "DeviceStore":
        self.store._ensure_parent()
        try:
            self.store._process_lock.__enter__()
        except StateLockError as exc:
            raise RepairDenied("device state file is not usable") from exc
        try:
            self.store._lock.acquire()
            self._locked = True
            if self.reload:
                self.store._reload()
        except Exception:
            self._unlock()
            raise
        return self.store

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._unlock()

    def _unlock(self) -> None:
        try:
            if self._locked:
                self.store._lock.release()
                self._locked = False
        finally:
            self.store._process_lock.__exit__(None, None, None)


class DeviceStore:
    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time, ttl: float = 300) -> None:
        self.path = assert_safe_state_path(path)
        self._clock = clock
        self._ttl = ttl
        self._lock = threading.RLock()
        self._key = secrets.token_bytes(32)
        self.devices: dict[str, dict[str, Any]] = {}
        self.jobs: list[dict[str, Any]] = []
        self.job_states: dict[str, dict[str, Any]] = {}
        self.nonces: list[str] = []
        self.audit: list[dict[str, Any]] = []
        self._ensure_parent()
        self._process_lock = CrossProcessLock(self.path.with_name(self.path.name + ".lock"))
        try:
            with self._process_lock:
                with self._lock:
                    if self.path.is_symlink() or self.path.is_file():
                        self._load()
        except StateLockError as exc:
            raise RepairDenied("device state file is not usable") from exc

    def _exclusive(self, reload: bool = True):
        return _Exclusive(self, reload=reload)

    def enrol(self, tenant_id: str, secret: str) -> str:
        with self._exclusive():
            return self._enrol(tenant_id, secret)

    def _enrol(self, tenant_id: str, secret: str) -> str:
        if len(secret) < 32:
            raise RepairDenied("device secret is too short")
        device_id = uuid.uuid4().hex
        self.devices[device_id] = {
            "device_id": device_id,
            "tenant_id": tenant_id,
            "secret_hash": hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            "mac_key": secrets.token_hex(32),
            "revoked": False,
            "repair_authority": False,
            "last_seen": None,
        }
        self._audit("enrol", tenant_id, device_id, "enrolled", None)
        self._save()
        return device_id

    def revoke(self, tenant_id: str, device_id: str) -> None:
        with self._exclusive():
            device = self._device(tenant_id, device_id)
            device["revoked"] = True
            self._audit("revoke", tenant_id, device_id, "revoked", None)
            self._save()

    def issue(
        self,
        *,
        tenant_id: str,
        device_id: str,
        procedure_id: str,
        grant: OperatorGrant | None = None,
        operator: str | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        with self._exclusive():
            return self._issue(
                tenant_id=tenant_id,
                device_id=device_id,
                procedure_id=procedure_id,
                grant=grant,
                operator=operator,
                approval_id=approval_id,
            )

    def _issue(
        self,
        *,
        tenant_id: str,
        device_id: str,
        procedure_id: str,
        grant: OperatorGrant | None,
        operator: str | None,
        approval_id: str | None,
    ) -> dict[str, Any]:
        if not isinstance(grant, OperatorGrant):
            raise RepairDenied("operator session is required")
        if grant.tenant_id != tenant_id:
            raise RepairDenied("operator is not authorised for this organisation")
        if operator is not None and operator != grant.username:
            raise RepairDenied("operator is not authorised to issue a device job")
        if approval_id:
            raise RepairDenied("device jobs cannot carry a repair approval")
        if procedure_id not in _READ_ONLY:
            raise RepairDenied("procedure is not a read-only device diagnostic")
        device = self._device(tenant_id, device_id)
        now = self._clock()
        body = {
            "job_id": uuid.uuid4().hex,
            "tenant_id": tenant_id,
            "device_id": device_id,
            "procedure_id": procedure_id,
            "operator": grant.username,
            "operator_id": grant.operator_id,
            "approval_id": None,
            "nonce": secrets.token_hex(16),
            "issued_at": now,
            "expires_at": now + self._ttl,
        }
        signed = dict(body)
        digest = _canonical(body)
        signed["device_signature"] = hmac.new(bytes.fromhex(device["mac_key"]), digest, hashlib.sha256).hexdigest()
        signed["signature"] = hmac.new(self._key, digest, hashlib.sha256).hexdigest()
        self.jobs.append(signed)
        self.job_states[body["job_id"]] = {
            "lifecycle": "issued",
            "procedure_id": procedure_id,
            "issued_at": now,
            "expires_at": body["expires_at"],
        }
        self._audit("issue", tenant_id, device_id, procedure_id, grant.username, job_id=body["job_id"])
        self._save()
        return signed

    def mac_key(self, device_id: str) -> str:
        """Signing key delivered once at enrolment. Later status calls must not use this."""
        with self._exclusive():
            device = self.devices.get(device_id)
            if device is None:
                raise RepairDenied("device is not enrolled for this organisation")
            return str(device["mac_key"])

    def accept(self, secret: str, envelope: dict[str, Any], *, provider: Any | None = None, result: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record a result the endpoint already collected.

        Passing a provider runs that collector in this process and is only for
        a test or a worker that is this process. The console HTTP route must
        call record_result and must not pass a provider.
        """
        if result is None and provider is None:
            raise RepairDenied("the console does not run the endpoint collector")
        if provider is not None and result is not None:
            raise RepairDenied("the endpoint submits one result")
        if provider is not None:
            prepared = self.prepare_collection(secret, envelope)
            from integrations.endpoint_worker import execute_assigned_job

            result = execute_assigned_job(
                envelope,
                device_id=prepared["device_id"],
                tenant_id=prepared["tenant_id"],
                mac_key=prepared["mac_key"],
                provider=provider,
                now=self._clock(),
            )
        return self.record_result(secret, envelope, result or {})

    def prepare_collection(self, secret: str, envelope: dict[str, Any]) -> dict[str, str]:
        """Reject a job the worker must not run. Does not collect and does not consume the nonce."""
        with self._exclusive():
            device = self._authorise(secret, envelope, consume=False)
            return {
                "device_id": device["device_id"],
                "tenant_id": device["tenant_id"],
                "mac_key": device["mac_key"],
            }

    def record_result(self, secret: str, envelope: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        """Store a worker result. This method never calls a collector."""
        with self._exclusive():
            return self._record(secret, envelope, result)

    def pending_jobs(self, secret: str) -> list[dict[str, Any]]:
        """Issued jobs for the authenticated device only."""
        with self._exclusive():
            device = self._device_for_secret(secret)
            if device is None:
                raise RepairDenied("device authentication failed")
            if device["revoked"]:
                raise RepairDenied("device credential is revoked")
            device["last_seen"] = self._clock()
            rows = []
            for job in self.jobs:
                if str(job.get("device_id") or "") != device["device_id"]:
                    continue
                lifecycle = self._lifecycle_of(job)
                if lifecycle != "issued":
                    continue
                if self._clock() >= float(job.get("expires_at") or 0):
                    self._set_lifecycle(str(job.get("job_id") or ""), "expired", expired_at=self._clock(), save=False)
                    continue
                rows.append({key: value for key, value in job.items() if key != "mac_key"})
            self._save()
            return rows

    def check_in(self, secret: str) -> dict[str, Any]:
        with self._exclusive():
            device = self._device_for_secret(secret)
            if device is None:
                raise RepairDenied("device authentication failed")
            if device["revoked"]:
                raise RepairDenied("device credential is revoked")
            device["last_seen"] = self._clock()
            pending = 0
            for job in self.jobs:
                if str(job.get("device_id") or "") == device["device_id"] and self._lifecycle_of(job) == "issued":
                    pending += 1
            self._audit("check-in", device["tenant_id"], device["device_id"], "seen", None)
            self._save()
            return {
                "device_id": device["device_id"],
                "tenant_id": device["tenant_id"],
                "pending_jobs": pending,
                "last_seen": device["last_seen"],
                "repair_authority": False,
                "remote_control": False,
            }

    def _device_for_secret(self, secret: str) -> dict[str, Any] | None:
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        for device in self.devices.values():
            if hmac.compare_digest(digest, str(device.get("secret_hash") or "")):
                return device
        return None

    def _authorise(self, secret: str, envelope: dict[str, Any], *, consume: bool) -> dict[str, Any]:
        body = job_body(envelope)
        if any(name in body for name in ("command", "shell", "argv", "script")):
            raise RepairDenied("endpoint jobs cannot carry a command")
        expected = hmac.new(self._key, _canonical(body), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(envelope.get("signature") or "")):
            raise RepairDenied("job signature is invalid")
        job_id = str(envelope.get("job_id") or "")
        stored = next((job for job in self.jobs if str(job.get("job_id")) == job_id), None)
        if stored is None:
            raise RepairDenied("job is not authorised")
        if _canonical(job_body(stored)) != _canonical(body):
            raise RepairDenied("job does not match the issued job")
        if "lifecycle" in body:
            raise RepairDenied("device job lifecycle is not taken from the payload")
        if body.get("approval_id") is not None:
            raise RepairDenied("device jobs cannot carry a repair approval")
        if str(body.get("procedure_id") or "") not in _READ_ONLY:
            raise RepairDenied("this device job is not a read-only diagnostic")
        device_id = str(body.get("device_id") or "")
        tenant_id = str(body.get("tenant_id") or "")
        device = self.devices.get(device_id)
        if device is None or device["tenant_id"] != tenant_id:
            self._reject(job_id, tenant_id, device_id, "unauthorised")
        assert device is not None
        device_mac = hmac.new(bytes.fromhex(str(device["mac_key"])), _canonical(body), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(device_mac, str(envelope.get("device_signature") or "")):
            raise RepairDenied("job signature is invalid")
        if device["revoked"]:
            self._reject(job_id, device["tenant_id"], device["device_id"], "revoked")
        secret_digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(secret_digest, device["secret_hash"]):
            self._reject(job_id, device["tenant_id"], device["device_id"], "unauthorised")
        current = str((self.job_states.get(job_id) or {}).get("lifecycle") or "issued")
        if current == "accepted" and consume:
            return device
        if self._clock() >= float(body["expires_at"]):
            self._set_lifecycle(job_id, "expired", expired_at=self._clock())
            raise RepairDenied("job expired")
        nonce = str(body["nonce"])
        if current == "accepted":
            raise RepairDenied("job replay rejected")
        if current in {"rejected", "expired", "failed"}:
            raise RepairDenied("job was rejected" if current == "rejected" else f"job {current}")
        if nonce in self.nonces and current != "accepted":
            self._set_lifecycle(job_id, "rejected", rejected_at=self._clock(), reason="replay", save=False)
            self._audit("reject", tenant_id, device_id, "replay", None, job_id=job_id)
            self._save()
            raise RepairDenied("job replay rejected")
        if not consume:
            if (self.job_states.get(job_id) or {}).get("in_flight"):
                raise RepairDenied("job is already being collected")
            self._set_lifecycle(job_id, "issued", in_flight=True)
        return device

    def _record(self, secret: str, envelope: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise RepairDenied("endpoint result is not usable")
        if any(name in result for name in ("command", "shell", "argv", "script")):
            raise RepairDenied("endpoint results cannot carry a command")
        device = self._authorise(secret, envelope, consume=True)
        body = job_body(envelope)
        job_id = str(body["job_id"])
        procedure_id = str(body["procedure_id"])
        view = result_signing_view(result, procedure_id)
        expected_result = hmac.new(bytes.fromhex(str(device["mac_key"])), _canonical(view), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_result, str(result.get("result_signature") or "")):
            raise RepairDenied("result signature is invalid")
        current = str((self.job_states.get(job_id) or {}).get("lifecycle") or "issued")
        digest = hashlib.sha256(_canonical(view)).hexdigest()
        if current == "accepted":
            stored_digest = str((self.job_states.get(job_id) or {}).get("result_digest") or "")
            if stored_digest and hmac.compare_digest(stored_digest, digest):
                previous = dict((self.job_states.get(job_id) or {}).get("public_result") or view)
                previous["duplicate"] = True
                previous["problem_resolved"] = False
                previous["repair_authority"] = False
                return previous
            raise RepairDenied("job replay rejected")
        nonce = str(body["nonce"])
        if nonce in self.nonces:
            raise RepairDenied("job replay rejected")
        self.nonces.append(nonce)
        device["last_seen"] = self._clock()
        fresh, stamp, age = self._evidence_clock(view)
        public = dict(view)
        public["job_id"] = job_id
        public["device_id"] = device["device_id"]
        public["tenant_id"] = device["tenant_id"]
        public["operator"] = body.get("operator")
        public["evidence_fresh"] = fresh
        public["collected_at_unix"] = stamp
        public["problem_resolved"] = False
        public["repair_authority"] = False
        public["remote_control"] = False
        public["duplicate"] = False
        if "mocked" in result:
            public["mocked"] = bool(result["mocked"])
        detail = result.get("detail")
        if isinstance(detail, str) and detail:
            public["detail"] = " ".join(detail.split())[:120]
        status = str(public["status"])
        ok = bool(public["ok"])
        failed = (not ok) or status in _FAILED_OUTCOMES
        outcome = "failed" if failed else status
        self._set_lifecycle(
            job_id,
            "failed" if failed else "accepted",
            accepted_at=device["last_seen"],
            status=outcome[:40],
            ok=ok,
            problem_resolved=False,
            evidence_source=str(public["evidence_source"])[:40],
            evidence_fresh=fresh,
            collected_at_unix=stamp,
            evidence_age_seconds=age,
            collected_by="endpoint_worker",
            result_digest=digest,
            public_result=public,
            in_flight=False,
            save=False,
        )
        if isinstance(result.get("result_signature"), str):
            public["result_signature"] = result["result_signature"]
        self._audit(
            "accept",
            device["tenant_id"],
            device["device_id"],
            outcome[:40],
            body.get("operator"),
            job_id=job_id,
        )
        self._save()
        return public

    def summary(self) -> dict[str, Any]:
        with self._exclusive():
            return self._summary()

    def _summary(self) -> dict[str, Any]:
        seen = [item["last_seen"] for item in self.devices.values() if isinstance(item.get("last_seen"), (int, float))]
        last_seen = max(seen) if seen else None
        age = None if last_seen is None else self._clock() - float(last_seen)
        counts = {"issued": 0, "accepted": 0, "expired": 0, "rejected": 0, "failed": 0}
        live_accepted = 0
        stale_evidence = 0
        stamps: list[int] = []
        for job in self.jobs:
            lifecycle = self._lifecycle_of(job)
            counts[lifecycle] = counts.get(lifecycle, 0) + 1
            recorded = self.job_states.get(str(job.get("job_id") or "")) or {}
            source = self._evidence_source(job)
            fresh = recorded.get("evidence_fresh") is True
            ok = recorded.get("ok") is True
            stamp = recorded.get("collected_at_unix")
            if isinstance(stamp, int) and not isinstance(stamp, bool):
                stamps.append(stamp)
            if lifecycle == "accepted" and source == "live_windows" and ok and fresh:
                live_accepted += 1
            elif lifecycle == "accepted" and source == "live_windows" and not fresh:
                stale_evidence += 1
        newest_stamp = max(stamps) if stamps else None
        evidence_age = None if newest_stamp is None else int(self._clock() - newest_stamp)
        failed = [row for row in self.audit if row.get("outcome") in _FAILED_OUTCOMES]
        return {
            "device_count": len(self.devices),
            "revoked": sum(1 for item in self.devices.values() if item["revoked"]),
            "last_seen": last_seen,
            "last_seen_age_seconds": None if age is None else int(age),
            "stale": age is not None and age > STALE_AFTER_SECONDS,
            "failed_jobs": len(failed),
            "failed_evidence_jobs": counts["failed"],
            "pending_jobs": counts["issued"],
            "open_jobs": counts["issued"],
            "accepted_jobs": counts["accepted"],
            "expired_jobs": counts["expired"],
            "rejected_jobs": counts["rejected"],
            "issued_jobs": len(self.jobs),
            "live_accepted_jobs": live_accepted,
            "stale_evidence_jobs": stale_evidence,
            "evidence_collected_at": newest_stamp,
            "evidence_age_seconds": evidence_age,
            "jobs": self._public_jobs(),
            "collector": "endpoint_worker",
        }

    def _public_jobs(self) -> list[dict[str, Any]]:
        rows = []
        for job in self.jobs[-20:]:
            state = self.job_states.get(str(job.get("job_id") or "")) or {}
            rows.append({
                "job_id": job.get("job_id"),
                "device_id": job.get("device_id"),
                "procedure_id": job.get("procedure_id"),
                "lifecycle": state.get("lifecycle") or "issued",
                "evidence_source": state.get("evidence_source"),
                "collected_at_unix": state.get("collected_at_unix"),
                "collected_by": state.get("collected_by"),
                "ok": state.get("ok"),
                "problem_resolved": False if state.get("lifecycle") else None,
                "status": state.get("status"),
            })
        return rows

    def _reject(self, job_id: str, tenant_id: str, device_id: str, reason: str) -> None:
        self._set_lifecycle(job_id, "rejected", rejected_at=self._clock(), reason=reason, save=False)
        self._audit("reject", tenant_id, device_id, reason, None, job_id=job_id)
        self._save()
        if reason == "revoked":
            raise RepairDenied("device credential is revoked")
        raise RepairDenied("device authentication failed")

    def _evidence_clock(self, result: dict[str, Any]) -> tuple[bool, int | None, int | None]:
        raw = result.get("collected_at_unix")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return False, None, None
        stamp = int(raw)
        age = int(self._clock() - stamp)
        fresh = -_FUTURE_SKEW_SECONDS <= age <= STALE_AFTER_SECONDS
        return fresh, stamp, age

    def _device(self, tenant_id: str, device_id: str) -> dict[str, Any]:
        device = self.devices.get(device_id)
        if device is None or device["tenant_id"] != tenant_id or device["revoked"]:
            raise RepairDenied("device is not enrolled for this organisation")
        return device

    def _evidence_source(self, job: dict[str, Any]) -> str:
        job_id = str(job.get("job_id") or "")
        recorded = self.job_states.get(job_id) or {}
        return str(recorded.get("evidence_source") or "")

    def _lifecycle_of(self, job: dict[str, Any]) -> str:
        job_id = str(job.get("job_id") or "")
        recorded = self.job_states.get(job_id) or {}
        lifecycle = str(recorded.get("lifecycle") or "issued")
        nonce = str(job.get("nonce") or "")
        if lifecycle in _TERMINAL:
            return lifecycle
        if nonce and nonce in self.nonces:
            return "rejected"
        try:
            expires = float(job["expires_at"])
        except (KeyError, TypeError, ValueError):
            return "expired"
        if self._clock() >= expires:
            return "expired"
        return "issued"

    def _set_lifecycle(self, job_id: str, lifecycle: str, *, save: bool = True, **extra: Any) -> None:
        if not job_id or not any(str(job.get("job_id")) == job_id for job in self.jobs):
            return
        current = dict(self.job_states.get(job_id) or {})
        if current.get("lifecycle") in _TERMINAL and lifecycle != current.get("lifecycle"):
            return
        current["lifecycle"] = lifecycle
        current.update(extra)
        self.job_states[job_id] = current
        if save:
            self._save()

    def _audit(
        self,
        action: str,
        tenant_id: str,
        device_id: str,
        outcome: str,
        operator: str | None,
        job_id: str | None = None,
    ) -> None:
        row = {
            "action": action,
            "tenant_id": tenant_id,
            "device_id": device_id,
            "outcome": outcome,
            "operator": operator,
            "at": self._clock(),
        }
        if job_id:
            row["job_id"] = job_id
        self.audit.append(row)

    def _key_path(self) -> Path:
        return self.path.with_name(self.path.name + ".key")

    def _reload(self) -> None:
        if self.path.is_symlink() or self.path.is_file():
            self._load()

    def _ensure_parent(self) -> None:
        parent = self.path.parent
        if parent.is_symlink():
            raise RepairDenied("device state directory must not be a link")
        missing: list[Path] = []
        cursor = parent
        while not cursor.exists():
            missing.append(cursor)
            if cursor.parent == cursor:
                break
            cursor = cursor.parent
        parent.mkdir(parents=True, exist_ok=True)
        for directory in reversed(missing):
            if directory.is_symlink() or not directory.is_dir():
                raise RepairDenied("device state directory must not be a link")
            try:
                restrict_private(directory)
            except StatePermissionError as exc:
                raise RepairDenied("device state permissions could not be enforced") from exc

    def _discard_temp(self, temporary: Path) -> None:
        if temporary.is_symlink() or not temporary.is_file():
            return
        try:
            temporary.unlink()
        except OSError:
            pass

    def _write_atomic(self, path: Path, text: str) -> None:
        if path.is_symlink():
            raise RepairDenied("device state file must be a regular file")
        if path.parent.is_symlink():
            raise RepairDenied("device state directory must not be a link")
        temporary = path.with_name(path.name + ".tmp")
        if temporary.is_symlink() or (temporary.exists() and not temporary.is_file()):
            raise RepairDenied("device state temporary file must be a regular file")
        if temporary.is_file():
            self._discard_temp(temporary)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if os.name == "posix" and hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(str(temporary), flags, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                restrict_private(temporary)
            except StatePermissionError as exc:
                raise RepairDenied("device state permissions could not be enforced") from exc
            os.replace(str(temporary), str(path))
        except RepairDenied:
            self._discard_temp(temporary)
            raise
        except OSError as exc:
            self._discard_temp(temporary)
            raise RepairDenied("device state file is not usable") from exc
        try:
            restrict_private(path)
        except StatePermissionError as exc:
            raise RepairDenied("device state permissions could not be enforced") from exc

    def _save(self) -> None:
        payload = {
            "version": 2,
            "devices": self.devices,
            "jobs": self.jobs,
            "job_states": self.job_states,
            "nonces": self.nonces,
            "audit": self.audit[-200:],
        }
        self._ensure_parent()
        self._write_atomic(self._key_path(), self._key.hex() + "\n")
        self._write_atomic(self.path, json.dumps(payload, sort_keys=True) + "\n")

    def _parse_key(self, text: str) -> bytes:
        try:
            key = bytes.fromhex(text.strip())
        except ValueError as exc:
            raise RepairDenied("device state file is not usable") from exc
        if len(key) != 32:
            raise RepairDenied("device state file is not usable")
        return key

    def _load(self) -> None:
        if self.path.is_symlink() or not self.path.is_file():
            raise RepairDenied("device state file is not usable")
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RepairDenied("device state file is not usable") from exc
        if not isinstance(raw, dict) or raw.get("version") not in (1, 2):
            raise RepairDenied("device state file is not usable")
        sidecar = self._key_path()
        file_key: bytes | None = None
        if sidecar.exists() or sidecar.is_symlink():
            if sidecar.is_symlink() or not sidecar.is_file():
                raise RepairDenied("device state file is not usable")
            try:
                key_text = sidecar.read_text(encoding="utf-8")
            except OSError as exc:
                raise RepairDenied("device state file is not usable") from exc
            file_key = self._parse_key(key_text)
        embedded = raw.get("key")
        embedded_key = self._parse_key(str(embedded)) if isinstance(embedded, str) else None
        if file_key is not None and embedded_key is not None and file_key != embedded_key:
            raise RepairDenied("device state file is not usable")
        key = file_key or embedded_key
        if key is None:
            raise RepairDenied("device state file is not usable")
        devices = raw.get("devices") or {}
        jobs = raw.get("jobs") or []
        states = raw.get("job_states") or {}
        nonces = raw.get("nonces") or []
        audit = raw.get("audit") or []
        if not isinstance(devices, dict) or not isinstance(jobs, list) or not isinstance(nonces, list):
            raise RepairDenied("device state file is not usable")
        if "job_states" in raw and not isinstance(states, dict):
            raise RepairDenied("device state file is not usable")
        if "audit" in raw and not isinstance(audit, list):
            raise RepairDenied("device state file is not usable")
        self._key = key
        self.devices = dict(devices)
        self.jobs = list(jobs)
        self.job_states = dict(states) if isinstance(states, dict) else {}
        self.nonces = [str(item) for item in nonces]
        self.audit = list(audit) if isinstance(audit, list) else []
        missing_mac = False
        for device in self.devices.values():
            if not isinstance(device, dict):
                continue
            mac = device.get("mac_key")
            if not isinstance(mac, str) or len(mac) != 64:
                device["mac_key"] = secrets.token_hex(32)
                missing_mac = True
        if missing_mac or raw.get("version") != 2 or "key" in raw or not sidecar.is_file():
            self._save()


def dev_self_test(path: Path) -> dict[str, Any]:
    """Enrol a throwaway device and run one live read-only job. Does not install a service."""
    secret = secrets.token_urlsafe(32)
    store = DeviceStore(path)
    device_id = store.enrol("local-test", secret)
    now = time.time()
    grant = grant_from_session(
        SessionRecord(
            session_id="dev-self-test",
            operator_id="dev-self-test",
            username="dev-self-test",
            role="operator",
            csrf_token="dev-self-test-csrf",
            created_at=now,
            last_seen=now,
            expires_at=now + 600,
            absolute_expires_at=now + 600,
        ),
        "local-test",
    )
    envelope = store.issue(tenant_id="local-test", device_id=device_id, procedure_id="win.storage.space", grant=grant)
    from .providers import LiveWindowsProvider

    result = store.accept(secret, envelope, provider=LiveWindowsProvider())
    result["collected_on"] = "this-process"
    result["repair_authority"] = False
    return result
