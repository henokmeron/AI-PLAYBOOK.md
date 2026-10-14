"""Append-only, hash-chained audit trail for connector operations (redacted)."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from agents.redaction import redact

GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    at: float
    tenant_id: str
    principal: str
    connector: str
    operation: str
    access: str
    outcome: str
    error_category: str | None
    detail: dict[str, Any]
    prev_hash: str
    hash: str


def _digest(fields: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()


class AuditLog:
    def __init__(self, sink_path: Path | None = None, clock: Callable[[], float] = time.time) -> None:
        self._entries: list[AuditEntry] = []
        self._sink = sink_path
        self._clock = clock
        self._lock = threading.Lock()

    def record(
        self, *, tenant_id: str, principal: str, connector: str, operation: str, access: str,
        outcome: str, error_category: str | None = None, detail: dict[str, Any] | None = None,
    ) -> AuditEntry:
        with self._lock:
            prev = self._entries[-1].hash if self._entries else GENESIS
            fields = {
                "seq": len(self._entries) + 1, "at": round(self._clock(), 3), "tenant_id": tenant_id,
                "principal": principal, "connector": connector, "operation": operation, "access": access,
                "outcome": outcome, "error_category": error_category,
                "detail": redact(detail or {}), "prev_hash": prev,
            }
            entry = AuditEntry(**fields, hash=_digest(fields))
            self._entries.append(entry)
            if self._sink is not None:
                with self._sink.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(asdict(entry), sort_keys=True, default=str) + "\n")
            return entry

    def entries(self, tenant_id: str | None = None) -> list[AuditEntry]:
        return [e for e in self._entries if tenant_id is None or e.tenant_id == tenant_id]

    def verify_chain(self) -> bool:
        prev = GENESIS
        for entry in self._entries:
            fields = asdict(entry)
            stored = fields.pop("hash")
            if fields["prev_hash"] != prev or _digest(fields) != stored:
                return False
            prev = stored
        return True
