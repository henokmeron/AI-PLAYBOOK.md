"""File-backed test device for registered diagnostic jobs.

This is not a Windows service. Enrolment does not grant repair authority.
The state file must stay outside the source tree.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from integrations.endpoint import assert_safe_state_path

from .engine import RepairDenied
from .providers import LIVE_PROCEDURES, LiveWindowsProvider

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


def grant_from_session(session: Any, tenant_id: str) -> OperatorGrant:
    """Build a grant from the authenticated session record, never from a request name."""
    if session is None or isinstance(session, (str, bytes, dict)):
        raise RepairDenied("operator session is required")
    session_id = str(getattr(session, "session_id", "") or "")
    operator_id = str(getattr(session, "operator_id", "") or "")
    username = str(getattr(session, "username", "") or "")
    role = str(getattr(session, "role", "") or "")
    if not session_id or not operator_id or not username:
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
        if self.path.is_file():
            self._load()

    def enrol(self, tenant_id: str, secret: str) -> str:
        with self._lock:
            return self._enrol(tenant_id, secret)

    def _enrol(self, tenant_id: str, secret: str) -> str:
        if len(secret) < 32:
            raise RepairDenied("device secret is too short")
        device_id = uuid.uuid4().hex
        self.devices[device_id] = {
            "device_id": device_id,
            "tenant_id": tenant_id,
            "secret_hash": hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            "revoked": False,
            "repair_authority": False,
            "last_seen": None,
        }
        self._audit("enrol", tenant_id, device_id, "enrolled", None)
        self._save()
        return device_id

    def revoke(self, tenant_id: str, device_id: str) -> None:
        with self._lock:
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
        with self._lock:
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
        self._device(tenant_id, device_id)
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
        signed["signature"] = hmac.new(self._key, _canonical(body), hashlib.sha256).hexdigest()
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

    def accept(self, secret: str, envelope: dict[str, Any], *, provider: Any | None = None) -> dict[str, Any]:
        with self._lock:
            return self._accept(secret, envelope, provider=provider)

    def _accept(self, secret: str, envelope: dict[str, Any], *, provider: Any | None) -> dict[str, Any]:
        body = {k: v for k, v in envelope.items() if k != "signature"}
        expected = hmac.new(self._key, _canonical(body), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(envelope.get("signature") or "")):
            raise RepairDenied("job signature is invalid")
        job_id = str(envelope.get("job_id") or "")
        if not any(str(job.get("job_id")) == job_id for job in self.jobs):
            raise RepairDenied("job is not authorised")
        current = str((self.job_states.get(job_id) or {}).get("lifecycle") or "issued")
        if current == "accepted":
            raise RepairDenied("job replay rejected")
        if current == "rejected":
            raise RepairDenied("job was rejected")
        if current == "expired":
            raise RepairDenied("job expired")
        if current == "failed":
            raise RepairDenied("job already failed")
        device_id = str(envelope.get("device_id") or "")
        tenant_id = str(envelope.get("tenant_id") or "")
        device = self.devices.get(device_id)
        if device is None or device["tenant_id"] != tenant_id:
            self._reject(job_id, tenant_id, device_id, "unauthorised")
        assert device is not None
        if device["revoked"]:
            self._reject(job_id, device["tenant_id"], device["device_id"], "revoked")
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(digest, device["secret_hash"]):
            self._reject(job_id, device["tenant_id"], device["device_id"], "unauthorised")
        if self._clock() >= float(envelope["expires_at"]):
            self._set_lifecycle(job_id, "expired", expired_at=self._clock())
            raise RepairDenied("job expired")
        nonce = str(envelope["nonce"])
        if nonce in self.nonces:
            self._set_lifecycle(job_id, "rejected", rejected_at=self._clock(), reason="replay", save=False)
            self._audit("reject", tenant_id, device_id, "replay", None, job_id=job_id)
            self._save()
            raise RepairDenied("job replay rejected")
        procedure_id = str(envelope["procedure_id"])
        if procedure_id not in _READ_ONLY:
            raise RepairDenied("this device job is not a read-only diagnostic")
        self.nonces.append(nonce)
        device["last_seen"] = self._clock()
        collector = provider or LiveWindowsProvider()
        try:
            result = collector.collect(procedure_id)
        except Exception as exc:  # noqa: BLE001 — a failed read must not look like a healthy accept
            result = {
                "evidence_source": "unavailable",
                "ok": False,
                "status": "failed",
                "problem_resolved": False,
                "detail": type(exc).__name__,
            }
        if not isinstance(result, dict):
            result = {
                "evidence_source": "unavailable",
                "ok": False,
                "status": "failed",
                "problem_resolved": False,
                "detail": "unreadable collector result",
            }
        result = dict(result)
        fresh, stamp, age = self._evidence_clock(result)
        result["job_id"] = envelope["job_id"]
        result["device_id"] = device["device_id"]
        result["tenant_id"] = device["tenant_id"]
        result["operator"] = envelope.get("operator")
        result["evidence_fresh"] = fresh
        if stamp is not None:
            result["collected_at_unix"] = stamp
        if "problem_resolved" not in result:
            result["problem_resolved"] = False
        status = str(result.get("status") or "done")
        ok = bool(result.get("ok")) if "ok" in result else status == "collected"
        failed = (not ok) or status in _FAILED_OUTCOMES
        outcome = "failed" if failed else status
        self._set_lifecycle(
            job_id,
            "failed" if failed else "accepted",
            accepted_at=device["last_seen"],
            status=outcome[:40],
            ok=ok,
            problem_resolved=bool(result.get("problem_resolved")),
            evidence_source=str(result.get("evidence_source") or "")[:40],
            evidence_fresh=fresh,
            collected_at_unix=stamp,
            evidence_age_seconds=age,
            save=False,
        )
        self._audit(
            "accept",
            device["tenant_id"],
            device["device_id"],
            outcome[:40],
            envelope.get("operator"),
            job_id=job_id,
        )
        self._save()
        return result

    def summary(self) -> dict[str, Any]:
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
        }

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

    def _restrict(self, path: Path) -> None:
        if os.name != "posix" or not path.is_file():
            return
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _write_atomic(self, path: Path, text: str) -> None:
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        self._restrict(temporary)
        os.replace(temporary, path)
        self._restrict(path)

    def _save(self) -> None:
        payload = {
            "version": 2,
            "devices": self.devices,
            "jobs": self.jobs,
            "job_states": self.job_states,
            "nonces": self.nonces,
            "audit": self.audit[-200:],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RepairDenied("device state file is not usable") from exc
        if not isinstance(raw, dict) or raw.get("version") not in (1, 2):
            raise RepairDenied("device state file is not usable")
        sidecar = self._key_path()
        file_key = self._parse_key(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else None
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
        if raw.get("version") != 2 or "key" in raw or not sidecar.is_file():
            self._save()


def dev_self_test(path: Path) -> dict[str, Any]:
    """Enrol a throwaway device and run one live read-only job. Does not install a service."""
    from types import SimpleNamespace

    secret = secrets.token_urlsafe(32)
    store = DeviceStore(path)
    device_id = store.enrol("local-test", secret)
    grant = grant_from_session(
        SimpleNamespace(
            session_id="dev-self-test",
            operator_id="dev-self-test",
            username="dev-self-test",
            role="operator",
        ),
        "local-test",
    )
    envelope = store.issue(tenant_id="local-test", device_id=device_id, procedure_id="win.storage.space", grant=grant)
    result = store.accept(secret, envelope)
    result["repair_authority"] = False
    return result
