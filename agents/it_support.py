"""IT support coworker helpers: playbook text and incident report schema.

These do not grant remote control. They steer the existing agent loop to
diagnose with permitted tools, verify outcomes, and write a clear report.
"""
from __future__ import annotations

import re
from typing import Any

IT_HINT = re.compile(
    r"\b("
    r"it support|helpdesk|help desk|ticket|incident|outage|vpn|wifi|wi-?fi|"
    r"password reset|locked out|cannot (?:log|sign) ?in|blue screen|bsod|"
    r"disk (?:full|space)|slow (?:pc|computer|laptop)|printer|endpoint|"
    r"enrolled (?:device|computer)|diagnostics|maintenance flag|"
    r"gateway|console (?:down|offline|error)|service (?:down|degraded)|"
    r"platform health|cache (?:full|clear)|log(?:s)? (?:error|fail)"
    r")\b",
    re.IGNORECASE,
)

INCIDENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "summary", "severity", "evidence", "actions_taken",
        "verification", "next_steps", "outcome",
    ],
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 500},
        "severity": {"type": "string", "enum": ["low", "medium", "high", "unknown"]},
        "category": {
            "type": "string",
            "enum": [
                "access", "connectivity", "performance", "storage", "application",
                "endpoint", "email", "unknown",
            ],
        },
        "desired_outcome": {"type": "string", "maxLength": 300},
        "evidence": {
            "type": "array",
            "maxItems": 12,
            "items": {"type": "string", "minLength": 1, "maxLength": 400},
        },
        "actions_taken": {
            "type": "array",
            "maxItems": 12,
            "items": {"type": "string", "minLength": 1, "maxLength": 400},
        },
        "verification": {
            "type": "array",
            "maxItems": 12,
            "items": {"type": "string", "minLength": 1, "maxLength": 400},
        },
        "next_steps": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "minLength": 1, "maxLength": 400},
        },
        "outcome": {
            "type": "string",
            "enum": ["resolved", "mitigated", "needs_approval", "escalated", "blocked"],
        },
    },
}

IT_SUPPORT_PLAYBOOK = """
IT helpdesk mode — follow this workflow with permitted tools only:

1. Accept the user's IT problem as stated. Do not invent facts.
2. If a critical fact is missing (device name, error text, when it started), use action ask once. Do not ask for passwords or secrets.
3. Call classify_it_issue to record category, severity, and desired outcome.
4. Search internal docs with search_documents when a procedure might exist. Cite file names. If status is abstained, say the library does not cover it.
5. Build a short plan in your tool choices (classify → investigate → remediate if needed → verify → report). For a Windows computer, call windows_repair_plan with the symptom, then windows_repair_diagnose with one returned procedure id. Those tools cannot take a shell command. Also use check_platform_health, run_safe_diagnostic, read_approved_log, and read_device_diagnostics when they are listed.
6. Execute only listed tools. Read tools need no approval. apply_safe_remediation pauses for human approval — fill what_changes, why, system, risks, and verification_plan honestly.
7. After any change, verify with a fresh check (health, diagnostic, or operator confirmation). Never claim a fix succeeded from the remediation tool alone.
8. If unsuccessful, say what failed and the next safe action. Escalate when tools cannot proceed.
9. Call compose_incident_report, then finish with a final action whose output matches the incident schema.
10. Keep the answer understandable to a non-technical business user.

Hard limits:
- No remote shell, no password reset, no silent remote control, no invented Microsoft or endpoint credentials.
- Microsoft 365 and enrolled-device tools appear only when connected; do not pretend they are live.
- Consequential changes need human approval of the exact arguments.
""".strip()


def looks_like_it_support(goal: str) -> bool:
    if not isinstance(goal, str) or not goal.strip():
        return False
    return IT_HINT.search(goal) is not None


def playbook_for(goal: str) -> str | None:
    return IT_SUPPORT_PLAYBOOK if looks_like_it_support(goal) else None


def approval_presentation(tool: str, arguments: dict[str, Any], reason: str) -> dict[str, Any]:
    """Operator-facing fields for the approval panel."""
    args = arguments if isinstance(arguments, dict) else {}
    return {
        "call_tool": tool,
        "reason": reason,
        "what_changes": str(args.get("what_changes") or args.get("action") or tool)[:400],
        "why": str(args.get("why") or reason)[:400],
        "system": str(args.get("system") or "local platform")[:120],
        "risks": str(args.get("risks") or "May change local console state.")[:400],
        "verification_plan": str(
            args.get("verification_plan")
            or "Re-check health or diagnostics after approval."
        )[:400],
    }


def incident_from_output(output: Any) -> dict[str, Any] | None:
    if not isinstance(output, dict):
        return None
    required = ("summary", "severity", "evidence", "actions_taken", "verification", "next_steps", "outcome")
    if any(key not in output for key in required):
        return None
    return {
        "summary": str(output.get("summary") or "")[:500],
        "severity": str(output.get("severity") or "unknown"),
        "category": str(output.get("category") or "unknown"),
        "desired_outcome": str(output.get("desired_outcome") or "")[:300],
        "evidence": [str(item)[:400] for item in (output.get("evidence") or [])[:12]],
        "actions_taken": [str(item)[:400] for item in (output.get("actions_taken") or [])[:12]],
        "verification": [str(item)[:400] for item in (output.get("verification") or [])[:12]],
        "next_steps": [str(item)[:400] for item in (output.get("next_steps") or [])[:8]],
        "outcome": str(output.get("outcome") or "blocked"),
    }


__all__ = [
    "INCIDENT_OUTPUT_SCHEMA",
    "IT_SUPPORT_PLAYBOOK",
    "approval_presentation",
    "incident_from_output",
    "looks_like_it_support",
    "playbook_for",
]
