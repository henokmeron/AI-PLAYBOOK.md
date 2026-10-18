"""Signed repair jobs for an enrolled device.

The existing endpoint connector remains read-only check-in. Repair jobs are a
separate allowlist. Development mode does not store an administrator password
and does not open a shell.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .engine import RepairDenied, execute


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class DeviceRecord:
    device_id: str
    tenant_id: str
    secret_hash: str
    revoked: bool = False


@dataclass
class CaseRecord:
    case_id: str
    tenant_id: str
    device_id: str
    symptom: str
    status: str = "open"


class JobService:
    def __init__(self, *, key: bytes | None = None, clock: Callable[[], float] = time.time, ttl: float = 300) -> None:
        self._key = key or secrets.token_bytes(32)
        self._clock = clock
        self._ttl = ttl
        self.devices: dict[str, DeviceRecord] = {}
        self.cases: dict[str, CaseRecord] = {}
        self._nonces: set[str] = set()
        self.audit: list[dict[str, Any]] = []

    def enrol(self, tenant_id: str, secret: str) -> str:
        device_id = uuid.uuid4().hex
        self.devices[device_id] = DeviceRecord(
            device_id=device_id,
            tenant_id=tenant_id,
            secret_hash=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
        )
        self._audit("enrol", tenant_id, device_id, "enrolled")
        return device_id

    def revoke(self, tenant_id: str, device_id: str) -> None:
        device = self._device(tenant_id, device_id)
        device.revoked = True
        self._audit("revoke", tenant_id, device_id, "revoked")

    def open_case(self, tenant_id: str, device_id: str, symptom: str) -> CaseRecord:
        self._device(tenant_id, device_id)
        case = CaseRecord(case_id=uuid.uuid4().hex, tenant_id=tenant_id, device_id=device_id, symptom=symptom[:300])
        self.cases[case.case_id] = case
        return case

    def get_case(self, tenant_id: str, case_id: str) -> CaseRecord:
        case = self.cases.get(case_id)
        if case is None or case.tenant_id != tenant_id:
            raise RepairDenied("case not found for this organisation")
        return case

    def issue(
        self,
        *,
        tenant_id: str,
        device_id: str,
        procedure_id: str,
        operator: str,
        approval_id: str | None = None,
        fixture: str | None = None,
    ) -> dict[str, Any]:
        self._device(tenant_id, device_id)
        now = self._clock()
        body = {
            "job_id": uuid.uuid4().hex,
            "tenant_id": tenant_id,
            "device_id": device_id,
            "procedure_id": procedure_id,
            "operator": operator,
            "approval_id": approval_id,
            "fixture": fixture,
            "nonce": secrets.token_hex(16),
            "issued_at": now,
            "expires_at": now + self._ttl,
        }
        body["signature"] = hmac.new(self._key, _canonical({k: v for k, v in body.items() if k != "signature"}), hashlib.sha256).hexdigest()
        self._audit("issue", tenant_id, device_id, procedure_id, operator=operator)
        return body

    def accept(self, secret: str, envelope: dict[str, Any], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        body = {k: v for k, v in envelope.items() if k != "signature"}
        expected = hmac.new(self._key, _canonical(body), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(envelope.get("signature") or "")):
            raise RepairDenied("job signature is invalid")
        if self._clock() > float(envelope["expires_at"]):
            raise RepairDenied("job expired")
        nonce = str(envelope["nonce"])
        if nonce in self._nonces:
            raise RepairDenied("job replay rejected")
        device = self.devices.get(str(envelope["device_id"]))
        if device is None or device.revoked:
            raise RepairDenied("device is not enrolled")
        if device.tenant_id != envelope["tenant_id"]:
            raise RepairDenied("tenant mismatch")
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(digest, device.secret_hash):
            raise RepairDenied("device authentication failed")
        self._nonces.add(nonce)
        result = execute(
            str(envelope["procedure_id"]),
            evidence=evidence,
            fixture=envelope.get("fixture"),
            approval_id=envelope.get("approval_id"),
            operator=str(envelope.get("operator") or "operator"),
        )
        result["job_id"] = envelope["job_id"]
        result["tenant_id"] = device.tenant_id
        result["device_id"] = device.device_id
        self._audit("accept", device.tenant_id, device.device_id, result.get("status") or "done", operator=result.get("operator"))
        return result

    def _device(self, tenant_id: str, device_id: str) -> DeviceRecord:
        device = self.devices.get(device_id)
        if device is None or device.tenant_id != tenant_id or device.revoked:
            raise RepairDenied("device is not enrolled for this organisation")
        return device

    def _audit(self, action: str, tenant_id: str, device_id: str, outcome: str, operator: str | None = None) -> None:
        self.audit.append({
            "action": action,
            "tenant_id": tenant_id,
            "device_id": device_id,
            "outcome": outcome,
            "operator": operator,
            "at": self._clock(),
        })
