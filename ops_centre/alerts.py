"""Alert lifecycle with deduplication and cooldowns."""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from .detections import DetectionHit
from .models import Alert, AlertStatus
from .store import utc_now


class AlertService:
    def __init__(
        self,
        path: Path | None = None,
        *,
        clock: Callable[[], str] = utc_now,
        cooldown_seconds: int = 300,
    ) -> None:
        self._path = path
        self._clock = clock
        self._cooldown = max(30, int(cooldown_seconds))
        self._lock = threading.Lock()
        self._alerts: dict[str, Alert] = {}
        self._last_fire: dict[str, float] = {}
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._load(path)

    def _load(self, path: Path) -> None:
        if not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for item in raw.get("alerts") or []:
            try:
                alert = Alert(**{k: item.get(k) for k in Alert.__dataclass_fields__})
                self._alerts[alert.alert_id] = alert
            except TypeError:
                continue

    def _persist(self) -> None:
        if self._path is None:
            return
        payload = {"alerts": [a.to_public() for a in self._alerts.values()]}
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def ingest_hits(self, hits: list[DetectionHit], *, now_mono: float | None = None) -> list[Alert]:
        import time

        mono = time.monotonic() if now_mono is None else now_mono
        created: list[Alert] = []
        with self._lock:
            for hit in hits:
                last = self._last_fire.get(hit.fingerprint, 0.0)
                open_existing = next(
                    (
                        a for a in self._alerts.values()
                        if a.fingerprint == hit.fingerprint
                        and a.status not in {AlertStatus.RESOLVED.value}
                    ),
                    None,
                )
                if open_existing is not None:
                    # Refresh evidence; do not storm
                    open_existing.evidence = hit.evidence
                    open_existing.event_ids = hit.event_ids
                    open_existing.updated_at = self._clock()
                    continue
                if mono - last < self._cooldown:
                    continue
                alert = Alert(
                    alert_id=uuid.uuid4().hex,
                    rule_id=hit.rule_id,
                    rule_version=hit.rule_version,
                    title=hit.title,
                    severity=hit.severity,
                    status=AlertStatus.NEW.value,
                    created_at=self._clock(),
                    updated_at=self._clock(),
                    evidence=hit.evidence,
                    event_ids=hit.event_ids,
                    confidence=hit.confidence,
                    fingerprint=hit.fingerprint,
                )
                self._alerts[alert.alert_id] = alert
                self._last_fire[hit.fingerprint] = mono
                created.append(alert)
            self._persist()
        return created

    def list(self, *, status: str | None = None, limit: int = 100) -> list[Alert]:
        rows = list(self._alerts.values())
        if status:
            rows = [a for a in rows if a.status == status]
        rows.sort(key=lambda a: a.updated_at, reverse=True)
        return rows[: max(1, min(limit, 500))]

    def get(self, alert_id: str) -> Alert | None:
        return self._alerts.get(alert_id)

    def transition(
        self,
        alert_id: str,
        *,
        status: str,
        actor: str,
        note: str = "",
    ) -> Alert:
        allowed = {s.value for s in AlertStatus}
        if status not in allowed:
            raise ValueError(f"invalid alert status {status!r}")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor is required")
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                raise KeyError(alert_id)
            alert.status = status
            alert.updated_at = self._clock()
            alert.owner = actor.strip()[:120]
            if status == AlertStatus.ACKNOWLEDGED.value:
                alert.ack_note = note[:500]
            if status == AlertStatus.RESOLVED.value:
                alert.resolution = note[:1000]
            if status == AlertStatus.REOPENED.value:
                alert.resolution = ""
            self._persist()
            return alert

    def open_counts(self) -> dict[str, int]:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total_open": 0}
        for alert in self._alerts.values():
            if alert.status == AlertStatus.RESOLVED.value:
                continue
            counts["total_open"] += 1
            if alert.severity in counts:
                counts[alert.severity] += 1
        return counts
