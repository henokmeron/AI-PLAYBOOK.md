"""Append-only, hash-chained event store (redacted). Not forensic-grade WORM."""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agents.redaction import redact

from .models import OpsEvent

GENESIS = "0" * 64


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _digest(fields: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()


class EventStore:
    """Central ops/security event log.

    Integrity: hash chaining detects silent rewrites of the in-memory/file
    sequence *if* an attacker cannot rewrite the chain consistently. A root
    user on the host can still replace the file. Do not claim forensic-grade
    tamper resistance.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        clock: Callable[[], str] = utc_now,
        max_events: int = 50_000,
    ) -> None:
        self._path = path
        self._clock = clock
        self._max = max(100, int(max_events))
        self._lock = threading.Lock()
        self._events: list[OpsEvent] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._load(path)

    def _load(self, path: Path) -> None:
        if not path.is_file():
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines[-self._max :]:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                self._events.append(OpsEvent(**{
                    k: raw.get(k) for k in OpsEvent.__dataclass_fields__
                }))
            except (TypeError, ValueError, json.JSONDecodeError, KeyError):
                continue

    def append(
        self,
        *,
        event_type: str,
        component: str,
        outcome: str,
        severity: str = "info",
        tenant_id: str = "local-console",
        correlation_id: str | None = None,
        actor: str | None = None,
        summary: str = "",
        detail: dict[str, Any] | None = None,
        verification: str = "observed",
        event_id: str | None = None,
    ) -> OpsEvent:
        with self._lock:
            prev = self._events[-1].hash if self._events else GENESIS
            fields = {
                "event_id": event_id or uuid.uuid4().hex,
                "at": self._clock(),
                "event_type": event_type,
                "component": component,
                "outcome": outcome,
                "severity": severity,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "actor": actor,
                "summary": (summary or "")[:500],
                "detail": redact(detail or {}),
                "verification": verification,
                "prev_hash": prev,
            }
            fields["hash"] = _digest({k: v for k, v in fields.items() if k != "hash"})
            event = OpsEvent(**fields)
            self._events.append(event)
            if len(self._events) > self._max:
                self._events = self._events[-self._max :]
            if self._path is not None:
                with self._path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event.to_public(), sort_keys=True, default=str) + "\n")
            return event

    def list(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
        component: str | None = None,
        severity: str | None = None,
        tenant_id: str | None = None,
        correlation_id: str | None = None,
        q: str | None = None,
    ) -> list[OpsEvent]:
        rows = list(self._events)
        if tenant_id:
            rows = [e for e in rows if e.tenant_id == tenant_id]
        if event_type:
            rows = [e for e in rows if e.event_type == event_type]
        if component:
            rows = [e for e in rows if e.component == component]
        if severity:
            rows = [e for e in rows if e.severity == severity]
        if correlation_id:
            rows = [e for e in rows if e.correlation_id == correlation_id]
        if q:
            needle = q.lower()
            rows = [
                e for e in rows
                if needle in e.summary.lower()
                or needle in e.event_type.lower()
                or needle in e.component.lower()
            ]
        return list(reversed(rows[-max(1, min(limit, 500)) :]))

    def get(self, event_id: str) -> OpsEvent | None:
        for event in reversed(self._events):
            if event.event_id == event_id:
                return event
        return None

    def verify_chain(self) -> dict[str, Any]:
        prev = GENESIS
        for index, event in enumerate(self._events):
            fields = event.to_public()
            stored = fields.pop("hash")
            if fields.get("prev_hash") != prev or _digest(fields) != stored:
                return {
                    "ok": False,
                    "broken_at_index": index,
                    "event_id": event.event_id,
                    "detail": "hash chain mismatch — file may have been edited or truncated inconsistently",
                }
            prev = stored
        return {"ok": True, "events": len(self._events), "detail": "chain verifies for loaded events"}
