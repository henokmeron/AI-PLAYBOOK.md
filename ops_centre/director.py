"""On-demand AI Operations Director.

This report is built from Operations Centre probes and stored events.
It does not call a language model, start services, or run shell commands.
A durable schedule file can run the report on an interval. The schedule never
starts the model or paid services.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .health_window import failure_window_seconds, within_window

from .service import OpsCentre

# Least-privilege profile: read existing ops tools only.
# The Director must not register or call anything outside this set.
READ_ONLY_TOOLS = (
    "ops_get_overview",
    "ops_get_health",
    "ops_search_events",
    "ops_list_alerts",
    "ops_get_alert",
    "ops_get_incident_report",
)

# Explicit deny list. These names are not tools and must never be added.
FORBIDDEN_CAPABILITIES = (
    "shell",
    "python_exec",
    "sql",
    "delete_audit",
    "disable_monitoring",
    "grant_permission",
    "change_security_policy",
    "bypass_approval",
    "read_secrets",
)

def _scheduler_status() -> dict[str, Any]:
    try:
        from .director_schedule import DirectorSchedule, DirectorScheduleError

        return DirectorSchedule().status()
    except Exception as exc:  # noqa: BLE001 — report stays useful when the schedule file is missing
        return {
            "available": False,
            "enabled": False,
            "reason": f"Director schedule is not usable ({type(exc).__name__}). Use the manual command.",
        }


_STATE = {
    "healthy": "HEALTHY",
    "degraded": "DEGRADED",
    "unavailable": "DEGRADED",
    "unknown": "UNKNOWN",
    "not_configured": "NOT CONFIGURED",
}


def map_state(raw: str | None) -> str:
    if raw is None:
        return "UNKNOWN"
    return _STATE.get(str(raw).strip().casefold(), "UNKNOWN")


def _service_rows(health: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in health.get("services") or []:
        if isinstance(item, dict) and item.get("name"):
            rows[str(item["name"])] = item
    return rows


def _component(
    name: str,
    state: str,
    *,
    evidence: list[str],
    detail: str,
    checked_at: str | None,
) -> dict[str, Any]:
    if state not in {"HEALTHY", "DEGRADED", "UNKNOWN", "NOT CONFIGURED"}:
        state = "UNKNOWN"
        evidence = evidence + ["state was not one of the four allowed labels; forced UNKNOWN"]
    if state != "NOT CONFIGURED" and not checked_at:
        state = "UNKNOWN"
        evidence = evidence + ["no timestamp; treated as unchecked"]
    return {
        "name": name,
        "state": state,
        "checked_at": checked_at,
        "detail": detail[:400],
        "evidence": evidence[:12],
        "kind": "verified_fact",
    }


def _endpoint_fleet(verified_at: str | None) -> dict[str, Any]:
    raw = os.environ.get("ENDPOINT_STATE_FILE", "").strip()
    if not raw:
        return _component(
            "endpoint_fleet",
            "UNKNOWN",
            evidence=["ENDPOINT_STATE_FILE is unset"],
            detail="Last-seen times were not collected.",
            checked_at=verified_at,
        )
    try:
        import time
        from pathlib import Path
        from integrations.endpoint import DeviceRegistry

        registry = DeviceRegistry(Path(raw))
        snapshot = registry.fleet_snapshot()
        count = int(snapshot["enrolled"])
        newest = float(snapshot["last_report_at"] or 0)
        if count == 0 or newest <= 0:
            return _component(
                "endpoint_fleet",
                "UNKNOWN",
                evidence=[f"enrolled={count}", "no last-seen timestamp", "repair_authority=false"],
                detail="The check-in file has no recent report. Enrolment does not grant repair authority.",
                checked_at=verified_at,
            )
        age = time.time() - newest
        coverage = str(snapshot["coverage"])
        evidence_stale = bool(snapshot.get("evidence_stale"))
        if age > 86400:
            state = "DEGRADED"
            detail = "The newest check-in is older than one day."
        elif coverage != "registered":
            state = "UNKNOWN"
            detail = "Only the short disk check-in is present. Registered diagnostics were not collected."
        elif int(snapshot["failed_checks"]):
            state = "DEGRADED"
            detail = "One or more registered diagnostics failed."
        elif evidence_stale:
            state = "DEGRADED"
            detail = "Registered diagnostics are present, but the collection time is missing or older than one day. Stale evidence is not healthy."
        else:
            state = "HEALTHY"
            detail = "Registered read-only diagnostics are fresh. This is not remote control or a repair."
        evidence = [
            f"enrolled={count}",
            f"last_report_unix={int(newest)}",
            f"age_seconds={int(age)}",
            f"coverage={coverage}",
            f"failed_checks={snapshot['failed_checks']}",
            f"evidence_collected_at={snapshot.get('evidence_collected_at')}",
            f"evidence_age_seconds={snapshot.get('evidence_age_seconds')}",
            f"evidence_stale={str(evidence_stale).lower()}",
            "repair_authority=false",
        ]
        failed_names = snapshot.get("failed_procedures") or []
        if failed_names:
            evidence.append("failed_procedures=" + ",".join(str(item) for item in failed_names)[:160])
        return _component(
            "endpoint_fleet",
            state,
            evidence=evidence,
            detail=detail,
            checked_at=verified_at,
        )
    except Exception as exc:  # noqa: BLE001
        return _component(
            "endpoint_fleet",
            "DEGRADED",
            evidence=[type(exc).__name__],
            detail="The endpoint check-in file could not be read.",
            checked_at=verified_at,
        )


def _repair_jobs(verified_at: str | None) -> dict[str, Any]:
    raw = os.environ.get("REPAIR_DEVICE_STATE", "").strip()
    if not raw:
        return _component(
            "repair_jobs",
            "NOT CONFIGURED",
            evidence=["REPAIR_DEVICE_STATE is unset"],
            detail="No dedicated test-device job file is configured.",
            checked_at=verified_at,
        )
    try:
        from pathlib import Path
        from windows_repair.device_store import DeviceStore

        summary = DeviceStore(Path(raw)).summary()
        age = summary.get("last_seen_age_seconds")
        live = int(summary.get("live_accepted_jobs") or 0)
        stale_evidence = int(summary.get("stale_evidence_jobs") or 0)
        rejected = int(summary.get("rejected_jobs") or 0)
        if summary["device_count"] == 0 or summary["last_seen"] is None or age is None:
            state = "UNKNOWN"
            if rejected:
                detail = "A job was rejected for a revoked or unauthorised device. No completed check-in is recorded."
            else:
                detail = "No completed device check-in is recorded. A missing last-seen is not healthy."
        elif age < 0:
            state = "UNKNOWN"
            detail = "The last-seen time is ahead of this clock. That is not a healthy check-in."
        elif summary.get("stale"):
            state = "DEGRADED"
            detail = "The newest device check-in is older than one day. Stale evidence is not healthy."
        elif summary["failed_jobs"] or int(summary.get("failed_evidence_jobs") or 0):
            state = "DEGRADED"
            detail = "A device job failed or diagnostic collection failed. This file is not a healthy repair fleet."
        elif stale_evidence and live < 1:
            state = "DEGRADED"
            detail = "Live evidence is missing a collection time or is older than one day. Stale evidence is not healthy."
        elif live < 1:
            state = "UNKNOWN"
            detail = "No accepted job has fresh live_windows evidence. A mock, fixture, or unlabelled result is not healthy."
        else:
            state = "HEALTHY"
            detail = "A read-only live_windows job with a fresh collection time was accepted. This is not a repair and not a deployment."
        return _component(
            "repair_jobs",
            state,
            evidence=[
                f"devices={summary['device_count']}",
                f"last_seen={summary['last_seen']}",
                f"age_seconds={age}",
                f"accepted_jobs={summary['accepted_jobs']}",
                f"live_accepted_jobs={summary.get('live_accepted_jobs')}",
                f"expired_jobs={summary['expired_jobs']}",
                f"rejected_jobs={rejected}",
                f"failed_jobs={summary['failed_jobs']}",
                f"stale_evidence_jobs={stale_evidence}",
                f"evidence_age_seconds={summary.get('evidence_age_seconds')}",
                "repair_authority=false",
            ],
            detail=detail,
            checked_at=verified_at,
        )
    except Exception as exc:  # noqa: BLE001
        return _component(
            "repair_jobs",
            "DEGRADED",
            evidence=[type(exc).__name__],
            detail="The repair device file could not be read.",
            checked_at=verified_at,
        )


def _stored_operator(item: Any) -> tuple[str, str, bool] | None:
    """Match a row the auth store can load. The password hash is not returned."""
    if not isinstance(item, dict):
        return None
    try:
        operator_id = str(item["operator_id"]).strip()
        username = str(item["username"]).strip()
        password_hash = str(item["password_hash"])
        role = str(item["role"])
        disabled = bool(item.get("disabled", False))
    except (KeyError, TypeError, ValueError):
        return None
    from web.auth.passwords import scrypt_hash_well_formed

    if not operator_id or not username or role not in {"admin", "operator", "viewer"}:
        return None
    if not scrypt_hash_well_formed(password_hash):
        return None
    return operator_id, role, disabled


def _operator_auth(verified_at: str | None) -> dict[str, Any]:
    """Report whether named operators are provisioned. Never copy password hashes."""
    try:
        from web.auth.service import default_auth_dir
    except Exception as exc:  # noqa: BLE001
        return _component(
            "operator_auth",
            "UNKNOWN",
            evidence=[type(exc).__name__],
            detail="Operator-auth status could not be loaded.",
            checked_at=verified_at,
        )
    path = default_auth_dir() / "operators.json"
    if path.is_symlink():
        return _component(
            "operator_auth",
            "DEGRADED",
            evidence=["operators.json is a symlink"],
            detail="A linked operator file is not a provisioned account store. The link target was not read.",
            checked_at=verified_at,
        )
    if not path.is_file():
        return _component(
            "operator_auth",
            "NOT CONFIGURED",
            evidence=["operators.json is missing"],
            detail="No operator accounts are provisioned. Privileged console APIs fail closed.",
            checked_at=verified_at,
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return _component(
            "operator_auth",
            "DEGRADED",
            evidence=["operators.json could not be read"],
            detail="The operator file is present but unreadable. Do not treat login as healthy.",
            checked_at=verified_at,
        )
    rows = raw.get("operators") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return _component(
            "operator_auth",
            "DEGRADED",
            evidence=["operators.json has no operator list"],
            detail="The operator file is not usable. Privileged console APIs fail closed.",
            checked_at=verified_at,
        )
    loaded: dict[str, tuple[str, bool]] = {}
    for item in rows:
        parsed = _stored_operator(item)
        if parsed is None:
            continue
        operator_id, role, disabled = parsed
        loaded[operator_id] = (role, disabled)
    active_rows = [(role, disabled) for role, disabled in loaded.values() if not disabled]
    active = len(active_rows)
    admins = sum(1 for role, _disabled in active_rows if role == "admin")
    if admins < 1:
        return _component(
            "operator_auth",
            "DEGRADED",
            evidence=[f"active_operators={active}", "active_admins=0"],
            detail="An active administrator is required. Password hashes are not included in this report.",
            checked_at=verified_at,
        )
    return _component(
        "operator_auth",
        "HEALTHY",
        evidence=[f"active_operators={active}", f"active_admins={admins}"],
        detail="At least one active administrator is provisioned. This is not a deployment check.",
        checked_at=verified_at,
    )


def _agent_health(centre: OpsCentre, verified_at: str | None) -> dict[str, Any]:
    """Classify agent failures without deleting audit events."""
    now = datetime.now(timezone.utc)
    window = failure_window_seconds()
    agent_events = centre.events.list(limit=500, component="agent")
    if not agent_events:
        return _component(
            "agents",
            "UNKNOWN",
            evidence=["no agent events in the retained log", "audit_preserved=true"],
            detail="No agent telemetry was found. This is not evidence that agents are healthy.",
            checked_at=verified_at,
        )
    failed = [event for event in agent_events if event.event_type == "agent.task_failed"]
    pending = [event for event in agent_events if event.event_type == "agent.approval_pending"]
    current: list[Any] = []
    historical: list[Any] = []
    for event in failed:
        flag = within_window(event.at, now=now, window_seconds=window)
        if flag is False:
            historical.append(event)
        else:
            current.append(event)
    evidence = [
        "audit_preserved=true",
        f"current_failed_tasks={len(current)}",
        f"historical_failed_tasks={len(historical)}",
        f"window_seconds={window}",
    ]
    evidence.extend(
        f"{event.event_id} {event.event_type} at={event.at}"
        for event in (current or historical or agent_events)[:5]
    )
    if current:
        state = "DEGRADED"
        detail = (
            f"failed={len(current)} inside {window}s. "
            f"historical_retained={len(historical)} stay in the audit log and were not deleted."
        )
    elif historical:
        state = "UNKNOWN"
        detail = (
            f"No agent failure is inside the {window}s window. "
            f"historical_retained={len(historical)} stay in the audit log and do not mark current health as failed."
        )
    else:
        state = "HEALTHY"
        detail = f"No agent.task_failed events in the retained log. pending_approvals={len(pending)}."
    return _component(
        "agents",
        state,
        evidence=evidence,
        detail=detail,
        checked_at=current[0].at if current else agent_events[0].at,
    )


def _rag_health(verified_at: str | None) -> dict[str, Any]:
    rag_dir = os.environ.get("RAG_DOCS_DIR", "").strip()
    if not rag_dir:
        return _component(
            "rag",
            "NOT CONFIGURED",
            evidence=["RAG_DOCS_DIR is unset in this process"],
            detail="Document retrieval was not probed. Unset means not configured for this report, not that RAG code is absent.",
            checked_at=verified_at,
        )
    if not os.path.isdir(rag_dir) or os.path.islink(rag_dir):
        return _component(
            "rag",
            "DEGRADED",
            evidence=["RAG_DOCS_DIR is set but is not a directory"],
            detail="The configured document directory is missing.",
            checked_at=verified_at,
        )
    try:
        from .rag_probe import probe_folder

        probed = probe_folder(Path(rag_dir))
    except Exception as exc:  # noqa: BLE001
        return _component(
            "rag",
            "UNKNOWN",
            evidence=[type(exc).__name__, "model_called=false"],
            detail="The retrieval probe could not be completed.",
            checked_at=verified_at,
        )
    evidence = [
        f"grounded={str(bool(probed.get('grounded'))).lower()}",
        f"abstained={str(bool(probed.get('abstained'))).lower()}",
        "model_called=false",
    ]
    citation = probed.get("citation_file")
    if isinstance(citation, str) and citation and "/" not in citation and "\\" not in citation:
        evidence.append(f"citation_file={citation[:160]}")
    return _component(
        "rag",
        str(probed.get("state") or "UNKNOWN"),
        evidence=evidence,
        detail=str(probed.get("detail") or "Retrieval probe finished."),
        checked_at=str(probed.get("checked_at") or verified_at or "") or None,
    )


def build_report(centre: OpsCentre, *, desk: Any | None = None) -> dict[str, Any]:
    """Return a Director status report. Side effect: one append-only audit event."""
    if desk is not None:
        try:
            centre.collect_agent_snapshot(desk)
        except Exception as exc:  # noqa: BLE001 — report must still be produced
            centre.record_event(
                event_type="director.telemetry_gap",
                component="director",
                outcome="unknown",
                severity="medium",
                actor="director",
                summary="Agent snapshot could not be collected",
                detail={"error_type": type(exc).__name__},
            )

    health = centre.refresh_health()
    overview = centre.overview()
    services = _service_rows(health)
    verified_at = health.get("verified_at") if isinstance(health.get("verified_at"), str) else None

    def from_probe(label: str, *keys: str) -> dict[str, Any]:
        found = [services[key] for key in keys if key in services]
        if not found:
            return _component(
                label,
                "UNKNOWN",
                evidence=[f"no probe named {', '.join(keys)}"],
                detail="This report cannot check this component. The probe is not configured.",
                checked_at=verified_at,
            )
        states = [map_state(item.get("state")) for item in found]
        if "DEGRADED" in states:
            state = "DEGRADED"
        elif "UNKNOWN" in states:
            state = "UNKNOWN"
        elif states and all(item == "HEALTHY" for item in states):
            state = "HEALTHY"
        else:
            state = "UNKNOWN"
        evidence = []
        details = []
        stamps = []
        for item in found:
            evidence.append(
                f"{item.get('name')} state={item.get('state')} http={item.get('http_status')} at={item.get('verified_at')}"
            )
            if item.get("detail"):
                details.append(str(item.get("detail")))
            if item.get("verified_at"):
                stamps.append(str(item.get("verified_at")))
        return _component(
            label,
            state,
            evidence=evidence,
            detail="; ".join(details) or "probe completed",
            checked_at=stamps[-1] if stamps else None,
        )

    components = [
        from_probe("model", "qwen"),
        from_probe("gateway", "gateway_live", "gateway_ready"),
        from_probe("console", "console"),
        from_probe("local_disk", "disk"),
        _component(
            "monitoring",
            "HEALTHY" if verified_at else "UNKNOWN",
            evidence=["this process built a report from OpsCentre"] if verified_at else ["health snapshot had no timestamp"],
            detail="The Operations Centre process answered. External log export is not configured. A local hash chain is not tamper-proof storage.",
            checked_at=verified_at,
        ),
    ]

    components.append(_agent_health(centre, verified_at))
    components.append(_rag_health(verified_at))

    if os.environ.get("MICROSOFT_CLIENT_ID", "").strip():
        components.append(_component(
            "microsoft_graph",
            "UNKNOWN",
            evidence=["MICROSOFT_CLIENT_ID is set; no Graph call was made by this report"],
            detail="An application id is configured. This report did not sign in or read mail.",
            checked_at=verified_at,
        ))
    else:
        components.append(_component(
            "microsoft_graph",
            "NOT CONFIGURED",
            evidence=["MICROSOFT_CLIENT_ID is unset"],
            detail="Outlook mail search is not connected in this process.",
            checked_at=verified_at,
        ))

    try:
        from windows_repair.engine import list_procedures

        procedures = list_procedures()
        components.append(_component(
            "repair_catalogue",
            "HEALTHY" if procedures else "DEGRADED",
            evidence=[f"registered_procedures={len(procedures)}"],
            detail="The procedure catalogue loaded in this process. That does not mean a customer PC was repaired.",
            checked_at=verified_at,
        ))
    except Exception as exc:  # noqa: BLE001
        components.append(_component(
            "repair_catalogue",
            "UNKNOWN",
            evidence=[type(exc).__name__],
            detail="The repair catalogue could not be loaded.",
            checked_at=verified_at,
        ))
    components.append(_endpoint_fleet(verified_at))
    components.append(_repair_jobs(verified_at))
    components.append(_operator_auth(verified_at))

    try:
        from windows_repair.remote_support import check_remote

        remote = check_remote()
        components.append(_component(
            "remote_support",
            str(remote.get("state") or "UNKNOWN"),
            evidence=[str(remote.get("detail") or "no detail")],
            detail=str(remote.get("detail") or ""),
            checked_at=verified_at if remote.get("state") != "NOT CONFIGURED" else verified_at,
        ))
    except Exception as exc:  # noqa: BLE001
        components.append(_component(
            "remote_support",
            "UNKNOWN",
            evidence=[type(exc).__name__],
            detail="Remote-support status could not be collected.",
            checked_at=verified_at,
        ))

    alerts = overview.get("open_alerts") or []
    incidents = overview.get("open_incidents") or []
    facts = [
        {
            "statement": f"Health overall from probes is {health.get('overall')}.",
            "evidence": [f"verified_at={verified_at}", f"verification={health.get('verification')}"],
            "kind": "verified_fact",
        },
        {
            "statement": f"Open alerts={len(alerts)}; open incidents={len(incidents)}; pending approval events={overview.get('pending_approvals')}.",
            "evidence": [f"alert_id={a.get('alert_id')}" for a in alerts[:5] if isinstance(a, dict)],
            "kind": "verified_fact",
        },
    ]
    integrity = overview.get("integrity") or {}
    facts.append({
        "statement": "Event-store hash chain check: " + ("ok" if integrity.get("ok") else "not ok"),
        "evidence": [str(integrity.get("detail") or integrity.get("events") or "see integrity object")],
        "kind": "verified_fact",
        "limitation": (
            "A hash chain detects some local rewrites of the file this process writes. "
            "A host administrator can replace the file. This is not tamper-proof storage."
        ),
    })

    recommendations = []
    for component in components:
        if component["state"] == "DEGRADED":
            recommendations.append({
                "component": component["name"],
                "action": f"Investigate {component['name']} using the probe evidence. Do not treat this text as a fix.",
                "requires_approval": True,
                "executed": False,
            })
        elif component["state"] in {"UNKNOWN", "NOT CONFIGURED"}:
            recommendations.append({
                "component": component["name"],
                "action": f"Collect telemetry for {component['name']} before calling it healthy.",
                "requires_approval": False,
                "executed": False,
            })

    ranked = [c["state"] for c in components]
    if "DEGRADED" in ranked:
        overall = "DEGRADED"
    elif "UNKNOWN" in ranked:
        overall = "UNKNOWN"
    elif ranked and all(item == "HEALTHY" for item in ranked):
        overall = "HEALTHY"
    elif ranked and all(item in {"HEALTHY", "NOT CONFIGURED"} for item in ranked):
        overall = "DEGRADED"
    else:
        overall = "UNKNOWN"

    report = {
        "kind": "director_report",
        "overall": overall,
        "verified_at": verified_at,
        "scheduler": _scheduler_status(),
        "model_explanation": None,
        "hypotheses": [],
        "hypothesis_note": "This report does not add model-written guesses. Empty hypotheses means none were generated.",
        "components": components,
        "facts": facts,
        "open_alerts": alerts[:10],
        "open_incidents": incidents[:10],
        "pending_approvals": overview.get("pending_approvals"),
        "recent_failed_tasks": overview.get("recent_failed_tasks"),
        "retained_failed_audit_rows": overview.get("retained_failed_audit_rows"),
        "open_alerts_outside_health_window": overview.get("open_alerts_outside_health_window"),
        "recommendations": recommendations,
        "tool_allowlist": list(READ_ONLY_TOOLS),
        "forbidden_capabilities": list(FORBIDDEN_CAPABILITIES),
        "cannot_claim": [
            "compliance certification",
            "live Microsoft or Azure connectivity",
            "that a DEGRADED or UNKNOWN component is safe",
        ],
    }
    centre.record_event(
        event_type="director.report",
        component="director",
        outcome=overall.lower().replace(" ", "_"),
        severity="info",
        actor="director",
        summary=f"Director report overall {overall}",
        detail={
            "components": [{"name": c["name"], "state": c["state"]} for c in components],
            "recommendation_count": len(recommendations),
        },
    )
    report["audit_event_type"] = "director.report"
    return report


def main() -> int:
    centre = OpsCentre()
    print(json.dumps(build_report(centre), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
