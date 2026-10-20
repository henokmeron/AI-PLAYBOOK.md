"""File-backed test device for registered diagnostic jobs.

This is not a Windows service. Enrolment does not grant repair authority.
The state file must stay outside the source tree.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from integrations.endpoint import assert_safe_state_path

from .engine import RepairDenied
from .providers import LIVE_PROCEDURES, LiveWindowsProvider

_READ_ONLY = tuple(LIVE_PROCEDURES)
STALE_AFTER_SECONDS = 86400
_FAILED_OUTCOMES = frozenset({"failed", "approval_rejected", "needs_administrator"})


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class DeviceStore:
    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time, ttl: float = 300) -> None:
        self.path = assert_safe_state_path(path)
        self._clock = clock
        self._ttl = ttl
        self._key = secrets.token_bytes(32)
        self.devices: dict[str, dict[str, Any]] = {}
        self.jobs: list[dict[str, Any]] = []
        self.job_states: dict[str, dict[str, Any]] = {}
        self.nonces: list[str] = []
        self.audit: list[dict[str, Any]] = []
        if self.path.is_file():
            self._load()

    def enrol(self, tenant_id: str, secret: str) -> str:
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
        operator: str,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        if procedure_id not in _READ_ONLY and procedure_id != "print.spooler.restart":
            raise RepairDenied("procedure is not registered for a device job")
        self._device(tenant_id, device_id)
        now = self._clock()
        body = {
            "job_id": uuid.uuid4().hex,
            "tenant_id": tenant_id,
            "device_id": device_id,
            "procedure_id": procedure_id,
            "operator": operator,
            "approval_id": approval_id,
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
        self._audit("issue", tenant_id, device_id, procedure_id, operator, job_id=body["job_id"])
        self._save()
        return signed

    def accept(self, secret: str, envelope: dict[str, Any], *, provider: Any | None = None) -> dict[str, Any]:
        body = {k: v for k, v in envelope.items() if k != "signature"}
        expected = hmac.new(self._key, _canonical(body), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(envelope.get("signature") or "")):
            raise RepairDenied("job signature is invalid")
        job_id = str(envelope.get("job_id") or "")
        if self._clock() > float(envelope["expires_at"]):
            self._set_lifecycle(job_id, "expired", expired_at=self._clock())
            raise RepairDenied("job expired")
        nonce = str(envelope["nonce"])
        if nonce in self.nonces:
            raise RepairDenied("job replay rejected")
        device = self.devices.get(str(envelope["device_id"]))
        if device is None or device["revoked"] or device["tenant_id"] != envelope["tenant_id"]:
            raise RepairDenied("device is not enrolled")
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(digest, device["secret_hash"]):
            raise RepairDenied("device authentication failed")
        procedure_id = str(envelope["procedure_id"])
        if procedure_id not in _READ_ONLY:
            raise RepairDenied("this device job is not a read-only diagnostic")
        self.nonces.append(nonce)
        device["last_seen"] = self._clock()
        collector = provider or LiveWindowsProvider()
        result = collector.collect(procedure_id)
        result["job_id"] = envelope["job_id"]
        result["device_id"] = device["device_id"]
        result["tenant_id"] = device["tenant_id"]
        result["operator"] = envelope.get("operator")
        if "problem_resolved" not in result:
            result["problem_resolved"] = False
        status = str(result.get("status") or "done")
        self._set_lifecycle(
            job_id,
            "accepted",
            accepted_at=device["last_seen"],
            status=status[:40],
            ok=bool(result.get("ok")) if "ok" in result else status == "collected",
            problem_resolved=bool(result.get("problem_resolved")),
            evidence_source=str(result.get("evidence_source") or "")[:40],
            save=False,
        )
        self._audit("accept", device["tenant_id"], device["device_id"], status, envelope.get("operator"), job_id=job_id)
        self._save()
        return result

    def summary(self) -> dict[str, Any]:
        seen = [item["last_seen"] for item in self.devices.values() if isinstance(item.get("last_seen"), (int, float))]
        last_seen = max(seen) if seen else None
        age = None if last_seen is None else self._clock() - float(last_seen)
        counts = {"issued": 0, "accepted": 0, "expired": 0}
        for job in self.jobs:
            counts[self._lifecycle_of(job)] += 1
        failed = [row for row in self.audit if row.get("outcome") in _FAILED_OUTCOMES]
        return {
            "device_count": len(self.devices),
            "revoked": sum(1 for item in self.devices.values() if item["revoked"]),
            "last_seen": last_seen,
            "last_seen_age_seconds": None if age is None else int(age),
            "stale": age is not None and age > STALE_AFTER_SECONDS,
            "failed_jobs": len(failed),
            "pending_jobs": counts["issued"],
            "open_jobs": counts["issued"],
            "accepted_jobs": counts["accepted"],
            "expired_jobs": counts["expired"],
            "issued_jobs": len(self.jobs),
        }

    def _device(self, tenant_id: str, device_id: str) -> dict[str, Any]:
        device = self.devices.get(device_id)
        if device is None or device["tenant_id"] != tenant_id or device["revoked"]:
            raise RepairDenied("device is not enrolled for this organisation")
        return device

    def _lifecycle_of(self, job: dict[str, Any]) -> str:
        job_id = str(job.get("job_id") or "")
        recorded = self.job_states.get(job_id) or {}
        lifecycle = str(recorded.get("lifecycle") or "issued")
        if lifecycle == "accepted":
            return "accepted"
        if lifecycle == "expired":
            return "expired"
        try:
            expires = float(job["expires_at"])
        except (KeyError, TypeError, ValueError):
            return "expired"
        if self._clock() > expires:
            return "expired"
        return "issued"

    def _set_lifecycle(self, job_id: str, lifecycle: str, *, save: bool = True, **extra: Any) -> None:
        if not job_id or not any(str(job.get("job_id")) == job_id for job in self.jobs):
            return
        current = dict(self.job_states.get(job_id) or {})
        if current.get("lifecycle") == "accepted" and lifecycle != "accepted":
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

    def _save(self) -> None:
        payload = {
            "version": 1,
            "key": self._key.hex(),
            "devices": self.devices,
            "jobs": self.jobs,
            "job_states": self.job_states,
            "nonces": self.nonces,
            "audit": self.audit[-200:],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("version") != 1:
            raise RepairDenied("device state file is not usable")
        self._key = bytes.fromhex(str(raw["key"]))
        self.devices = dict(raw.get("devices") or {})
        self.jobs = list(raw.get("jobs") or [])
        states = raw.get("job_states") or {}
        self.job_states = dict(states) if isinstance(states, dict) else {}
        self.nonces = list(raw.get("nonces") or [])
        self.audit = list(raw.get("audit") or [])


def dev_self_test(path: Path) -> dict[str, Any]:
    """Enrol a throwaway device and run one live read-only job. Does not install a service."""
    secret = secrets.token_urlsafe(32)
    store = DeviceStore(path)
    device_id = store.enrol("local-test", secret)
    envelope = store.issue(tenant_id="local-test", device_id=device_id, procedure_id="win.storage.space", operator="dev-self-test")
    result = store.accept(secret, envelope)
    result["repair_authority"] = False
    return result
