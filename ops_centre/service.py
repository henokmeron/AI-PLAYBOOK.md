"""Facade used by the web console and AI Ops tools."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .alerts import AlertService
from .detections import COVERAGE, run_detections
from .health import HealthAggregator
from .incidents import IncidentService
from .models import AlertStatus, Verification
from .store import EventStore


def default_data_dir() -> Path:
    env = os.environ.get("OPS_CENTRE_DIR")
    if env:
        return Path(env)
    volume = Path("/workspace/ops-centre")
    if Path("/workspace").is_dir() and os.access("/workspace", os.W_OK):
        return volume
    return Path("/tmp/ops-centre")


@dataclass
class OpsCentreConfig:
    data_dir: Path | None = None
    tenant_id: str = "local-console"


class OpsCentre:
    def __init__(self, config: OpsCentreConfig | None = None) -> None:
        self.config = config or OpsCentreConfig()
        root = self.config.data_dir or default_data_dir()
        root.mkdir(parents=True, exist_ok=True)
        self.events = EventStore(root / "events.jsonl")
        self.alerts = AlertService(root / "alerts.json")
        self.incidents = IncidentService(root / "incidents.json")
        self.health = HealthAggregator()
        self.data_dir = root

    def record_event(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("tenant_id", self.config.tenant_id)
        return self.events.append(**kwargs).to_public()

    def refresh_health(self) -> dict[str, Any]:
        snap = self.health.snapshot()
        for service in snap.get("services") or []:
            state = service.get("state")
            if state in {"unavailable", "degraded"}:
                self.events.append(
                    event_type="health.probe",
                    component=str(service.get("name") or "unknown"),
                    outcome=str(state),
                    severity="critical" if state == "unavailable" else "high",
                    summary=f"{service.get('name')} {state}: {service.get('detail')}",
                    detail={
                        "check_kind": service.get("check_kind"),
                        "latency_ms": service.get("latency_ms"),
                        "http_status": service.get("http_status"),
                    },
                    verification=Verification.OBSERVED.value,
                )
            elif state == "healthy":
                # Record sparse healthy heartbeats so timeline shows checks ran
                self.events.append(
                    event_type="health.probe",
                    component=str(service.get("name") or "unknown"),
                    outcome="healthy",
                    severity="info",
                    summary=f"{service.get('name')} healthy",
                    detail={"latency_ms": service.get("latency_ms")},
                    verification=Verification.OBSERVED.value,
                )
        return snap

    def run_detections(self) -> dict[str, Any]:
        chain = self.events.verify_chain()
        if not chain.get("ok"):
            self.events.append(
                event_type="ops.audit_chain_broken",
                component="ops_centre",
                outcome="failed",
                severity="critical",
                summary="Event store hash chain verification failed",
                detail=chain,
                verification=Verification.OBSERVED.value,
            )
        hits = run_detections(self.events.list(limit=500))
        created = self.alerts.ingest_hits(hits)
        return {
            "hits": len(hits),
            "alerts_created": len(created),
            "alerts": [a.to_public() for a in created],
            "coverage": COVERAGE.strip(),
        }

    def overview(self) -> dict[str, Any]:
        health = self.refresh_health()
        detection = self.run_detections()
        open_alerts = self.alerts.list(limit=20)
        unresolved = [a for a in open_alerts if a.status != AlertStatus.RESOLVED.value]
        open_incidents = [
            i for i in self.incidents.list(limit=20)
            if i.status not in {"resolved", "closed"}
        ]
        pending_approvals = [
            e for e in self.events.list(limit=50, event_type="agent.approval_pending")
        ]
        failed_tasks = [
            e for e in self.events.list(limit=50, event_type="agent.task_failed")
        ]
        from .health_window import evidence_is_current, failure_window_seconds, within_window

        now = datetime.now(timezone.utc)
        window = failure_window_seconds()
        recent_failed = []
        for event in failed_tasks:
            current = within_window(event.at, now=now, window_seconds=window)
            if current is not False:
                recent_failed.append(event)
        current_alerts = [
            alert for alert in unresolved
            if evidence_is_current(list(alert.evidence or []), now=now, window_seconds=window)
        ]
        historical_alerts = [alert for alert in unresolved if alert not in current_alerts]
        overall = health.get("overall") or "unknown"
        if any(a.severity in {"critical", "high"} for a in current_alerts):
            # A high alert whose evidence is still inside the health window
            # keeps the overview out of healthy. Older open alerts stay open.
            if overall == "healthy":
                overall = "degraded"
        return {
            "overall": overall,
            "verification": health.get("verification"),
            "verified_at": health.get("verified_at"),
            "health": health,
            "alert_counts": self.alerts.open_counts(),
            "open_alerts": [a.to_public() for a in unresolved[:10]],
            "open_incidents": [i.to_public() for i in open_incidents[:10]],
            "pending_approvals": len(pending_approvals),
            "recent_failed_tasks": len(recent_failed),
            "retained_failed_audit_rows": len(failed_tasks),
            "open_alerts_outside_health_window": len(historical_alerts),
            "detections": {
                "hits": detection.get("hits"),
                "alerts_created": detection.get("alerts_created"),
            },
            "integrity": self.events.verify_chain(),
            "coverage_note": (
                "Green/healthy only means probes succeeded just now. "
                "Open critical/high alerts whose evidence is inside the health window "
                "force overall away from healthy. Older alerts stay open and are not deleted."
            ),
            "data_dir": str(self.data_dir),
        }

    def timeline(self, **filters: Any) -> dict[str, Any]:
        events = self.events.list(**filters)
        return {
            "events": [e.to_public() for e in events],
            "count": len(events),
            "note": "Events are observed platform signals or labelled probe results; not invented identities.",
        }

    def collect_agent_snapshot(self, desk: Any) -> dict[str, Any]:
        """Pull pending approvals and recent history from AgentDesk without inventing data."""
        recorded = 0
        try:
            history = desk.history_list(limit=20)
        except Exception:  # noqa: BLE001 — collector must not break console
            history = []
        seen = {
            (event.event_type, event.correlation_id)
            for event in self.events.list(limit=500, component="agent")
            if event.correlation_id
        }
        for row in history or []:
            if not isinstance(row, dict):
                continue
            execution = row.get("execution")
            task_id = str(row.get("task_id") or "").strip()
            if not task_id:
                continue
            if execution == "failed":
                event_type = "agent.task_failed"
                if (event_type, task_id) in seen:
                    continue
                self.events.append(
                    event_type=event_type,
                    component="agent",
                    outcome="failed",
                    severity="high",
                    correlation_id=task_id,
                    summary=(row.get("failure") or row.get("goal") or "agent task failed")[:400],
                    detail={"goal": (row.get("goal") or "")[:200]},
                )
                seen.add((event_type, task_id))
                recorded += 1
            elif execution == "awaiting_approval":
                event_type = "agent.approval_pending"
                if (event_type, task_id) in seen:
                    continue
                pending = row.get("pending_approval") or {}
                self.events.append(
                    event_type=event_type,
                    component="agent",
                    outcome="pending",
                    severity="medium",
                    correlation_id=task_id,
                    summary=f"Approval pending for {pending.get('tool') or 'tool'}",
                    detail={"tool": pending.get("tool"), "call_id": pending.get("call_id")},
                )
                seen.add((event_type, task_id))
                recorded += 1
        return {"recorded": recorded, "audit_preserved": True}
