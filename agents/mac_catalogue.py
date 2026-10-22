"""Documented read-only Mac checks.

Live Mac is NOT TESTED. This module does not execute those checks: this
repository runs on Windows here, and there is no remote Mac agent binary.
Tests interpret named fixtures only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.tools import Tool, ToolInputError

LIVE_MAC = "NOT TESTED"


@dataclass(frozen=True)
class MacCheck:
    check_id: str
    name: str
    summary: str
    documented_commands: tuple[str, ...]
    limitations: str

    def public(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "summary": self.summary,
            "documented_commands": list(self.documented_commands),
            "executed": False,
            "live_mac": LIVE_MAC,
            "limitations": self.limitations,
        }


MAC_CHECKS: tuple[MacCheck, ...] = (
    MacCheck(
        check_id="mac.disk.space",
        name="Disk space",
        summary="Read free space on a Mac volume.",
        documented_commands=("df -h",),
        limitations="Not executed on this Windows host. Does not delete files.",
    ),
    MacCheck(
        check_id="mac.network.inspect",
        name="Network",
        summary="Read interface, DNS, and gateway evidence on a Mac.",
        documented_commands=("ifconfig", "scutil --dns"),
        limitations="Not executed on this Windows host. Does not change DNS, proxy, or firewall settings.",
    ),
    MacCheck(
        check_id="mac.crash.reports",
        name="Crash reports",
        summary="Count recent Mac diagnostic reports by process name.",
        documented_commands=("ls ~/Library/Logs/DiagnosticReports",),
        limitations="Not executed on this Windows host. Report files are not read or uploaded.",
    ),
)

_BY_ID = {item.check_id: item for item in MAC_CHECKS}

FIXTURES: dict[str, dict[str, Any]] = {
    "disk_low": {
        "check_id": "mac.disk.space",
        "volume": "Macintosh HD",
        "free_bytes": 1024,
        "total_bytes": 500_000_000,
    },
    "network_dns": {
        "check_id": "mac.network.inspect",
        "interface": "en0",
        "dns_ok": False,
        "gateway_ok": True,
    },
    "crash_windowserver": {
        "check_id": "mac.crash.reports",
        "process": "WindowServer",
        "exception": "EXC_BAD_ACCESS",
        "count": 2,
    },
}

_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "check_id", "status", "executed", "changed_device", "problem_resolved",
        "evidence_source", "live_mac", "detail",
    ],
    "properties": {
        "check_id": {"type": "string"},
        "status": {"type": "string", "maxLength": 40},
        "executed": {"type": "boolean", "const": False},
        "changed_device": {"type": "boolean", "const": False},
        "problem_resolved": {"type": "boolean", "const": False},
        "evidence_source": {"type": "string", "enum": ["fixture", "none"]},
        "live_mac": {"type": "string", "const": LIVE_MAC},
        "detail": {"type": "string", "maxLength": 500},
    },
}


def _plain(value: Any, limit: int) -> str:
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())[:limit]


def catalogue() -> list[dict[str, Any]]:
    return [item.public() for item in MAC_CHECKS]


def interpret(check_id: str, fixture_name: str) -> dict[str, Any]:
    """Interpret one named fixture. Does not run a command."""
    check = _BY_ID.get(check_id)
    if check is None:
        raise ToolInputError("unknown Mac check")
    payload = FIXTURES.get(fixture_name)
    if payload is None:
        raise ToolInputError("unknown Mac fixture")
    if payload.get("check_id") != check_id:
        raise ToolInputError("fixture does not match this Mac check")
    if check_id == "mac.disk.space":
        detail = (
            f"Fixture {fixture_name}: volume {_plain(payload.get('volume'), 40)} "
            f"free_bytes={payload.get('free_bytes')} total_bytes={payload.get('total_bytes')}. "
            "The Mac check was not executed."
        )
    elif check_id == "mac.network.inspect":
        detail = (
            f"Fixture {fixture_name}: interface {_plain(payload.get('interface'), 20)} "
            f"dns_ok={payload.get('dns_ok')} gateway_ok={payload.get('gateway_ok')}. "
            "The Mac check was not executed."
        )
    else:
        detail = (
            f"Fixture {fixture_name}: process {_plain(payload.get('process'), 40)} "
            f"exception {_plain(payload.get('exception'), 40)} count={payload.get('count')}. "
            "Crash report files were not read."
        )
    return {
        "check_id": check_id,
        "status": "fixture",
        "executed": False,
        "changed_device": False,
        "problem_resolved": False,
        "evidence_source": "fixture",
        "live_mac": LIVE_MAC,
        "detail": _plain(detail, 500),
    }


def _not_run(check_id: str) -> dict[str, Any]:
    return {
        "check_id": check_id if check_id in _BY_ID else "",
        "status": "not-run",
        "executed": False,
        "changed_device": False,
        "problem_resolved": False,
        "evidence_source": "none",
        "live_mac": LIVE_MAC,
        "detail": (
            "Live Mac is NOT TESTED. This host did not run the check. "
            "No remote Mac agent binary is available."
        ),
    }


def mac_tools() -> list[Tool]:
    ids = [item.check_id for item in MAC_CHECKS]

    def plan_handler(arguments: dict[str, Any]) -> dict[str, Any]:
        text = str(arguments.get("symptom") or "").casefold()
        chosen = []
        if any(token in text for token in ("disk", "storage", "space", "full")):
            chosen.append("mac.disk.space")
        if any(token in text for token in ("network", "wifi", "dns", "internet")):
            chosen.append("mac.network.inspect")
        if any(token in text for token in ("crash", "panic", "report")):
            chosen.append("mac.crash.reports")
        if not chosen:
            chosen = list(ids)
        return {
            "check_ids": chosen,
            "executed": False,
            "live_mac": LIVE_MAC,
            "note": "Catalogue only. No Mac check was executed.",
        }

    def diagnose_handler(arguments: dict[str, Any]) -> dict[str, Any]:
        check_id = str(arguments["check_id"])
        fixture_name = str(arguments.get("fixture") or "").strip()
        if check_id not in _BY_ID:
            raise ToolInputError("unknown Mac check")
        if not fixture_name:
            return _not_run(check_id)
        return interpret(check_id, fixture_name)

    return [
        Tool(
            name="mac_plan",
            description=(
                "Choose a documented read-only Mac check id from a symptom. "
                "Does not execute the check. Live Mac is NOT TESTED."
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
                "required": ["check_ids", "executed", "live_mac", "note"],
                "properties": {
                    "check_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "executed": {"type": "boolean", "const": False},
                    "live_mac": {"type": "string", "const": LIVE_MAC},
                    "note": {"type": "string"},
                },
            },
            handler=plan_handler,
            timeout_seconds=5,
            tags=("mac", "read"),
        ),
        Tool(
            name="mac_diagnose",
            description=(
                "Interpret one named Mac fixture, or report that the check did not run. "
                "There is no remote Mac agent. Live Mac is NOT TESTED. "
                "A fixture name is required for evidence. Commands are not executed."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["check_id"],
                "properties": {
                    "check_id": {"type": "string", "enum": ids},
                    "fixture": {"type": "string", "maxLength": 64},
                },
            },
            output_schema=_RESULT_SCHEMA,
            handler=diagnose_handler,
            timeout_seconds=5,
            tags=("mac", "read"),
        ),
    ]


__all__ = [
    "FIXTURES",
    "LIVE_MAC",
    "MAC_CHECKS",
    "MacCheck",
    "catalogue",
    "interpret",
    "mac_tools",
]
