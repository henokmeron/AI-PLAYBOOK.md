"""Security/operations incidents — distinct from IT Helpdesk incident reports."""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from .models import Alert, SecurityIncident, IncidentStatus
from .store import utc_now


class IncidentService:
    def __init__(self, path: Path | None = None, *, clock: Callable[[], str] = utc_now) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._incidents: dict[str, SecurityIncident] = {}
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
        for item in raw.get("incidents") or []:
            try:
                incident = SecurityIncident(**{k: item.get(k) for k in SecurityIncident.__dataclass_fields__})
                self._incidents[incident.incident_id] = incident
            except TypeError:
                continue

    def _persist(self) -> None:
        if self._path is None:
            return
        payload = {"incidents": [i.to_public() for i in self._incidents.values()]}
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def create_from_alert(self, alert: Alert, *, actor: str, title: str | None = None) -> SecurityIncident:
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor is required")
        with self._lock:
            incident = SecurityIncident(
                incident_id=uuid.uuid4().hex,
                title=title or alert.title,
                severity=alert.severity,
                status=IncidentStatus.OPEN.value,
                created_at=self._clock(),
                updated_at=self._clock(),
                tenant_id=alert.tenant_id,
                detection_source=alert.rule_id,
                alert_ids=[alert.alert_id],
                event_ids=list(alert.event_ids),
                timeline=[{
                    "at": self._clock(),
                    "kind": "opened",
                    "actor": actor.strip()[:120],
                    "detail": f"Opened from alert {alert.alert_id}",
                }],
                facts=[f"Alert rule {alert.rule_id} v{alert.rule_version}"] + list(alert.evidence[:6]),
                hypotheses=[
                    "AI-generated hypotheses are not present yet; mark any model output as hypothesis when added."
                ],
            )
            self._incidents[incident.incident_id] = incident
            self._persist()
            return incident

    def list(self, *, status: str | None = None, limit: int = 50) -> list[SecurityIncident]:
        rows = list(self._incidents.values())
        if status:
            rows = [i for i in rows if i.status == status]
        rows.sort(key=lambda i: i.updated_at, reverse=True)
        return rows[: max(1, min(limit, 200))]

    def get(self, incident_id: str) -> SecurityIncident | None:
        return self._incidents.get(incident_id)

    def add_note(self, incident_id: str, *, actor: str, note: str, kind: str = "note") -> SecurityIncident:
        if not note.strip():
            raise ValueError("note is required")
        with self._lock:
            incident = self._incidents.get(incident_id)
            if incident is None:
                raise KeyError(incident_id)
            entry = {
                "at": self._clock(),
                "kind": kind,
                "actor": (actor or "operator")[:120],
                "detail": note.strip()[:1000],
            }
            incident.timeline.append(entry)
            if kind == "hypothesis":
                incident.hypotheses.append(note.strip()[:500])
            elif kind == "fact":
                incident.facts.append(note.strip()[:500])
            else:
                incident.notes.append(note.strip()[:500])
            incident.updated_at = self._clock()
            self._persist()
            return incident

    def transition(
        self,
        incident_id: str,
        *,
        status: str,
        actor: str,
        summary: str = "",
    ) -> SecurityIncident:
        allowed = {s.value for s in IncidentStatus}
        if status not in allowed:
            raise ValueError(f"invalid incident status {status!r}")
        with self._lock:
            incident = self._incidents.get(incident_id)
            if incident is None:
                raise KeyError(incident_id)
            incident.status = status
            incident.updated_at = self._clock()
            if summary:
                if status in {IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value}:
                    incident.resolution_summary = summary[:2000]
                incident.actions_taken.append(summary[:400])
            incident.timeline.append({
                "at": self._clock(),
                "kind": "status",
                "actor": (actor or "operator")[:120],
                "detail": f"status → {status}",
            })
            self._persist()
            return incident

    def report(self, incident_id: str) -> dict[str, Any]:
        incident = self.get(incident_id)
        if incident is None:
            raise KeyError(incident_id)
        return {
            "title": incident.title,
            "severity": incident.severity,
            "status": incident.status,
            "detection_source": incident.detection_source,
            "facts": incident.facts,
            "hypotheses": incident.hypotheses,
            "timeline": incident.timeline,
            "actions_taken": incident.actions_taken,
            "verification": incident.verification,
            "resolution_summary": incident.resolution_summary,
            "lessons_learned": incident.lessons_learned,
            "integrity_note": (
                "This report summarises operator/SOC records. Hypotheses are not facts. "
                "Event hash-chain verification is separate (GET /api/ops/integrity)."
            ),
        }
