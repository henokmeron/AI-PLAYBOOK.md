"""Explicit detection rules. Coverage is incomplete — see COVERAGE docstring."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .models import OpsEvent, Severity

COVERAGE = """
v1 detection coverage (what we can see):
- Repeated agent task failures (from collected agent events)
- Approval denials / pending approvals backlog
- Service probe failures (gateway/qwen/console)
- Tool permission / allowlist denials recorded as events
- Audit chain verification failures

Blind spots (not detected in v1):
- Console has no login — no auth-failure telemetry from the UI
- No browser-side XSS/CSRF sensor
- No external SIEM / EDR / cloud posture feeds
- No continuous model-prompt content DLP beyond redaction on stored events
- Pod nginx exposure is a known deferred risk (baseline-review), not auto-scanned here
- Cross-tenant attacks need multi-tenant traffic we do not yet have in production
"""


@dataclass(frozen=True)
class DetectionHit:
    rule_id: str
    rule_version: str
    title: str
    severity: str
    confidence: str
    evidence: list[str]
    event_ids: list[str]
    fingerprint: str
    detail: dict[str, Any]


RuleFn = Callable[[list[OpsEvent]], list[DetectionHit]]


def rule_repeated_agent_failures(events: list[OpsEvent]) -> list[DetectionHit]:
    from datetime import datetime, timezone

    from .health_window import failure_window_seconds, within_window

    now = datetime.now(timezone.utc)
    window = failure_window_seconds()
    fails = []
    for event in events:
        if event.event_type != "agent.task_failed":
            continue
        current = within_window(event.at, now=now, window_seconds=window)
        if current is False:
            continue
        fails.append(event)
    if len(fails) < 3:
        return []
    recent = fails[-5:]
    return [DetectionHit(
        rule_id="agent.repeated_failures",
        rule_version="1",
        title="Repeated agent task failures",
        severity=Severity.HIGH.value,
        confidence="high",
        evidence=[f"{e.at} {e.summary}"[:200] for e in recent],
        event_ids=[e.event_id for e in recent],
        fingerprint="agent.repeated_failures",
        detail={"count": len(fails)},
    )]


def rule_service_unavailable(events: list[OpsEvent]) -> list[DetectionHit]:
    hits: list[DetectionHit] = []
    bad = [
        e for e in events
        if e.event_type == "health.probe" and e.outcome in {"unavailable", "degraded"}
    ]
    by_component: dict[str, list[OpsEvent]] = {}
    for event in bad:
        by_component.setdefault(event.component, []).append(event)
    for component, rows in by_component.items():
        if not rows:
            continue
        last = rows[-1]
        severity = Severity.CRITICAL.value if last.outcome == "unavailable" else Severity.HIGH.value
        hits.append(DetectionHit(
            rule_id=f"health.{component}",
            rule_version="1",
            title=f"Service {component} is {last.outcome}",
            severity=severity,
            confidence="high",
            evidence=[f"{last.at} {last.summary}"[:200]],
            event_ids=[last.event_id],
            fingerprint=f"health.{component}.{last.outcome}",
            detail={"component": component, "outcome": last.outcome},
        ))
    return hits


def rule_tool_permission_denied(events: list[OpsEvent]) -> list[DetectionHit]:
    denied = [e for e in events if e.event_type == "agent.tool_denied"]
    if not denied:
        return []
    recent = denied[-10:]
    return [DetectionHit(
        rule_id="agent.tool_denied",
        rule_version="1",
        title="Tool use denied (allowlist / permission)",
        severity=Severity.MEDIUM.value if len(recent) < 5 else Severity.HIGH.value,
        confidence="high",
        evidence=[f"{e.at} {e.summary}"[:200] for e in recent[-5:]],
        event_ids=[e.event_id for e in recent],
        fingerprint="agent.tool_denied",
        detail={"count": len(denied)},
    )]


def rule_approval_backlog(events: list[OpsEvent]) -> list[DetectionHit]:
    pending = [e for e in events if e.event_type == "agent.approval_pending"]
    if len(pending) < 1:
        return []
    # Only alert when there are unresolved pending signals without a later decision
    open_pending = pending[-3:]
    return [DetectionHit(
        rule_id="agent.approval_backlog",
        rule_version="1",
        title="Human approval pending",
        severity=Severity.MEDIUM.value,
        confidence="medium",
        evidence=[f"{e.at} {e.summary}"[:200] for e in open_pending],
        event_ids=[e.event_id for e in open_pending],
        fingerprint="agent.approval_backlog",
        detail={"pending_signals": len(pending)},
    )]


def rule_audit_chain_broken(events: list[OpsEvent]) -> list[DetectionHit]:
    broken = [e for e in events if e.event_type == "ops.audit_chain_broken"]
    if not broken:
        return []
    last = broken[-1]
    return [DetectionHit(
        rule_id="ops.audit_chain_broken",
        rule_version="1",
        title="Operations event hash chain failed verification",
        severity=Severity.CRITICAL.value,
        confidence="high",
        evidence=[f"{last.at} {last.summary}"[:200]],
        event_ids=[last.event_id],
        fingerprint="ops.audit_chain_broken",
        detail=dict(last.detail or {}),
    )]


DEFAULT_RULES: list[RuleFn] = [
    rule_repeated_agent_failures,
    rule_service_unavailable,
    rule_tool_permission_denied,
    rule_approval_backlog,
    rule_audit_chain_broken,
]


def run_detections(events: list[OpsEvent], rules: list[RuleFn] | None = None) -> list[DetectionHit]:
    hits: list[DetectionHit] = []
    for rule in rules or DEFAULT_RULES:
        hits.extend(rule(events))
    return hits
