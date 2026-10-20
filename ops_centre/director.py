"""On-demand AI Operations Director.

This report is built from Operations Centre probes and stored events.
It does not call a language model, start services, or run shell commands.
There is no scheduler in this repository; run the report when you need it.
"""
from __future__ import annotations

import json
import os
from typing import Any

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
        "evidence": evidence[:8],
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
        if age > 86400:
            state = "DEGRADED"
            detail = "The newest check-in is older than one day."
        elif coverage != "registered":
            state = "UNKNOWN"
            detail = "Only the short disk check-in is present. Registered diagnostics were not collected."
        elif int(snapshot["failed_checks"]):
            state = "DEGRADED"
            detail = "One or more registered diagnostics failed."
        else:
            state = "HEALTHY"
            detail = "Registered read-only diagnostics are fresh. This is not remote control or a repair."
        return _component(
            "endpoint_fleet",
            state,
            evidence=[
                f"enrolled={count}",
                f"last_report_unix={int(newest)}",
                f"age_seconds={int(age)}",
                f"coverage={coverage}",
                f"failed_checks={snapshot['failed_checks']}",
                "repair_authority=false",
            ],
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
        if summary["device_count"] == 0 or summary["last_seen"] is None or age is None:
            state = "UNKNOWN"
            detail = "No completed device check-in is recorded. A missing last-seen is not healthy."
        elif age < 0:
            state = "UNKNOWN"
            detail = "The last-seen time is ahead of this clock. That is not a healthy check-in."
        elif summary.get("stale"):
            state = "DEGRADED"
            detail = "The newest device check-in is older than one day. Stale evidence is not healthy."
        elif summary["failed_jobs"]:
            state = "DEGRADED"
            detail = "A device job failed. This file is not a healthy repair fleet."
        else:
            state = "HEALTHY"
            detail = "A read-only device job was accepted recently. This is not a repair and not a deployment."
        return _component(
            "repair_jobs",
            state,
            evidence=[
                f"devices={summary['device_count']}",
                f"last_seen={summary['last_seen']}",
                f"age_seconds={age}",
                f"open_jobs={summary['open_jobs']}",
                f"accepted_jobs={summary['accepted_jobs']}",
                f"expired_jobs={summary['expired_jobs']}",
                f"failed_jobs={summary['failed_jobs']}",
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
    active = 0
    admins = 0
    for item in rows:
        if not isinstance(item, dict) or item.get("disabled"):
            continue
        active += 1
        if item.get("role") == "admin":
            admins += 1
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

    agent_events = centre.events.list(limit=30, component="agent")
    if not agent_events:
        components.append(_component(
            "agents",
            "UNKNOWN",
            evidence=["no agent events in the retained window"],
            detail="No agent telemetry was found. This is not evidence that agents are healthy.",
            checked_at=verified_at,
        ))
    else:
        failed = [e for e in agent_events if e.event_type == "agent.task_failed"]
        pending = [e for e in agent_events if e.event_type == "agent.approval_pending"]
        state = "DEGRADED" if failed else "HEALTHY"
        components.append(_component(
            "agents",
            state,
            evidence=[f"{e.event_id} {e.event_type} at={e.at}" for e in (failed or pending or agent_events)[:5]],
            detail=f"failed={len(failed)} pending_approvals={len(pending)} in the latest agent events",
            checked_at=agent_events[0].at,
        ))

    rag_dir = os.environ.get("RAG_DOCS_DIR", "").strip()
    if not rag_dir:
        components.append(_component(
            "rag",
            "NOT CONFIGURED",
            evidence=["RAG_DOCS_DIR is unset in this process"],
            detail="Document retrieval was not probed. Unset means not configured for this report, not that RAG code is absent.",
            checked_at=verified_at,
        ))
    elif not os.path.isdir(rag_dir):
        components.append(_component(
            "rag",
            "DEGRADED",
            evidence=[f"RAG_DOCS_DIR is set but is not a directory"],
            detail="The configured document directory is missing.",
            checked_at=verified_at,
        ))
    else:
        components.append(_component(
            "rag",
            "UNKNOWN",
            evidence=["document directory exists; retrieval quality was not executed"],
            detail="Directory presence is not evidence that answers are grounded.",
            checked_at=verified_at,
        ))

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
        "scheduler": {
            "available": False,
            "reason": "No job runner or cron integration exists in this repository. Use the manual command.",
        },
        "model_explanation": None,
        "hypotheses": [],
        "hypothesis_note": "This report does not add model-written guesses. Empty hypotheses means none were generated.",
        "components": components,
        "facts": facts,
        "open_alerts": alerts[:10],
        "open_incidents": incidents[:10],
        "pending_approvals": overview.get("pending_approvals"),
        "recent_failed_tasks": overview.get("recent_failed_tasks"),
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
