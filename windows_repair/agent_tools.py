"""Agent tools that can only select a registered Windows procedure."""
from __future__ import annotations

from typing import Any

from agents.tools import Tool, ToolInputError

from .engine import RepairDenied, execute, plan


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value).split())[:limit]


def windows_repair_tools() -> list[Tool]:
    def plan_handler(arguments: dict[str, Any]) -> dict[str, Any]:
        result = plan(str(arguments["symptom"]))
        return {
            "procedure_ids": [str(item) for item in result["procedure_ids"]],
            "problem_resolved": False,
            "note": _text(result["note"], 240),
        }

    def diagnose_handler(arguments: dict[str, Any]) -> dict[str, Any]:
        procedure_id = str(arguments["procedure_id"])
        try:
            result = execute(procedure_id)
        except RepairDenied as exc:
            raise ToolInputError(exc.message) from exc
        if result.get("status") in {"approval_required", "denied", "approved_not_run_on_this_host", "not_run"}:
            return {
                "procedure_id": procedure_id,
                "status": str(result["status"]),
                "problem_resolved": False,
                "detail": _text(result.get("detail") or "", 300),
            }
        return {
            "procedure_id": procedure_id,
            "status": str(result.get("status") or "diagnosed"),
            "problem_resolved": False,
            "detail": _text(result.get("detail") or "", 300),
        }

    shared_output = {
        "type": "object",
        "additionalProperties": False,
        "required": ["procedure_id", "status", "problem_resolved", "detail"],
        "properties": {
            "procedure_id": {"type": "string"},
            "status": {"type": "string"},
            "problem_resolved": {"type": "boolean", "const": False},
            "detail": {"type": "string"},
        },
    }
    return [
        Tool(
            name="windows_repair_plan",
            description=(
                "Choose registered Windows diagnostic procedure ids from a symptom. "
                "Does not run a repair and does not accept a shell command."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["symptom"],
                "properties": {"symptom": {"type": "string", "minLength": 3, "maxLength": 300}},
            },
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["procedure_ids", "problem_resolved", "note"],
                "properties": {
                    "procedure_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "problem_resolved": {"type": "boolean", "const": False},
                    "note": {"type": "string"},
                },
            },
            handler=plan_handler,
            idempotent=True,
            timeout_seconds=5,
        ),
        Tool(
            name="windows_repair_diagnose",
            description=(
                "Run one registered read-only Windows procedure, or record that an elevated "
                "procedure was not run. Never accepts a command string."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["procedure_id"],
                "properties": {
                    "procedure_id": {"type": "string", "minLength": 3, "maxLength": 64, "pattern": r"^[a-z0-9.]+$"},
                },
            },
            output_schema=shared_output,
            handler=diagnose_handler,
            idempotent=True,
            timeout_seconds=10,
        ),
    ]
