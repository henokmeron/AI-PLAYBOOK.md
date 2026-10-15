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
    r"enrolled (?:device|computer)|diagnostics"
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
IT support mode (when the task is an IT or helpdesk problem):
- Diagnose with permitted tools only. Prefer search_documents and read_device_diagnostics when available.
- Collect evidence before proposing a fix. Cite document file names or device report fields.
- Never claim a fix worked unless a tool result or operator note verifies it.
- Consequential changes need human approval. There is no remote shell, no silent remote control, and no password reset tool.
- If the library does not cover the issue, say so and escalate or ask the operator.
- Finish with a concise incident-style answer: what failed, what you checked, what remains.
""".strip()


def looks_like_it_support(goal: str) -> bool:
    if not isinstance(goal, str) or not goal.strip():
        return False
    return IT_HINT.search(goal) is not None


def playbook_for(goal: str) -> str | None:
    return IT_SUPPORT_PLAYBOOK if looks_like_it_support(goal) else None


__all__ = [
    "INCIDENT_OUTPUT_SCHEMA",
    "IT_SUPPORT_PLAYBOOK",
    "looks_like_it_support",
    "playbook_for",
]
