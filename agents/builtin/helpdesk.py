"""Low-risk IT helpdesk tools: health, logs, diagnostics, approved remediation.

No unrestricted shell. Every tool has a fixed purpose, validated inputs, timeouts,
and redacted outputs. Write tools require human approval and verify nothing
themselves — the agent must re-check after they run.
"""
from __future__ import annotations

import os
import shutil
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ..redaction import redact_text
from ..tools import Tool, ToolError, ToolInputError

ProbeFn = Callable[[str, float], dict[str, Any]]
RestartFn = Callable[[str], dict[str, Any]]

_CATEGORIES = (
    "access", "connectivity", "performance", "storage", "application",
    "endpoint", "email", "unknown",
)
_SEVERITIES = ("low", "medium", "high", "unknown")
_DIAGNOSTICS = ("local_disk_space", "platform_ports", "python_runtime", "temp_cache")
_REMEDIATIONS = ("clear_temp_cache", "set_maintenance_flag", "clear_maintenance_flag")

_LOG_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z"
_MAX_LOG_BYTES = 64_000
_MAX_LOG_LINES = 80


def _plain(value: str, limit: int) -> str:
    text = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
    return text[:limit]


def _http_probe(url: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — loopback only
            code = int(getattr(response, "status", 0) or 0)
            content_type = str(response.headers.get("Content-Type") or "").lower()
            body = response.read(200).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "http_status": int(exc.code),
            "detail": f"HTTP {exc.code}",
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {
            "ok": False,
            "http_status": 0,
            "detail": _plain(type(exc).__name__ + ": " + str(exc), 200),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    # Keep observations compact: HTML console pages blow the agent token budget.
    if "html" in content_type or body.lstrip().lower().startswith("<!doctype") or body.lstrip().lower().startswith("<html"):
        detail = f"HTTP {code} HTML page"
    else:
        detail = _plain(body, 120) or f"HTTP {code}"
    return {
        "ok": 200 <= code < 400,
        "http_status": code,
        "detail": detail,
        "latency_ms": int((time.monotonic() - started) * 1000),
    }


def default_service_urls() -> dict[str, str]:
    """Loopback URLs the console already uses. Overridable via HELPDESK_*_URL."""
    return {
        "qwen": os.environ.get("HELPDESK_QWEN_URL", "http://127.0.0.1:8002/health"),
        "gateway": os.environ.get("HELPDESK_GATEWAY_URL", "http://127.0.0.1:8010/health"),
        "console": os.environ.get("HELPDESK_CONSOLE_URL", "http://127.0.0.1:8080/"),
    }


def classify_it_issue_tool() -> Tool:
    def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "category": arguments["category"],
            "severity": arguments["severity"],
            "desired_outcome": _plain(arguments["desired_outcome"], 300),
            "missing_information": [
                _plain(item, 200) for item in arguments.get("missing_information") or []
            ][:6],
            "notes": _plain(arguments.get("notes") or "", 400),
        }

    return Tool(
        name="classify_it_issue",
        description=(
            "Record the IT issue class, severity, and desired outcome. "
            "Call this early. If facts are missing, list them in missing_information "
            "and use action ask before tools that need those facts."
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["category", "severity", "desired_outcome"],
            "properties": {
                "category": {"type": "string", "enum": list(_CATEGORIES)},
                "severity": {"type": "string", "enum": list(_SEVERITIES)},
                "desired_outcome": {"type": "string", "minLength": 1, "maxLength": 300},
                "missing_information": {
                    "type": "array",
                    "maxItems": 6,
                    "items": {"type": "string", "minLength": 1, "maxLength": 200},
                },
                "notes": {"type": "string", "maxLength": 400},
            },
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["category", "severity", "desired_outcome", "missing_information", "notes"],
            "properties": {
                "category": {"type": "string"},
                "severity": {"type": "string"},
                "desired_outcome": {"type": "string"},
                "missing_information": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
        },
        handler=handler,
        timeout_seconds=5.0,
        tags=("read", "helpdesk"),
    )


def check_platform_health_tool(
    *,
    services: dict[str, str] | None = None,
    probe: ProbeFn | None = None,
    timeout_seconds: float = 3.0,
) -> Tool:
    urls = dict(services or default_service_urls())
    probe_fn = probe or _http_probe

    def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        selected = arguments.get("services") or sorted(urls)
        if not isinstance(selected, list) or not selected:
            raise ToolInputError("services must be a non-empty list of service names")
        rows = []
        all_ok = True
        for name in selected[:8]:
            if not isinstance(name, str) or name not in urls:
                raise ToolInputError(f"unknown service {name!r}; known: {sorted(urls)}")
            result = probe_fn(urls[name], timeout_seconds)
            ok = bool(result.get("ok"))
            all_ok = all_ok and ok
            rows.append({
                "service": name,
                "url": urls[name],
                "ok": ok,
                "http_status": int(result.get("http_status") or 0),
                "detail": _plain(str(result.get("detail") or ""), 200),
                "latency_ms": int(result.get("latency_ms") or 0),
            })
        return {
            "status": "healthy" if all_ok else "degraded",
            "checked_at_unix": int(time.time()),
            "services": rows,
        }

    return Tool(
        name="check_platform_health",
        description=(
            "Check configured local platform services (model, gateway, console). "
            "Read-only. Use before and after remediation to verify outcomes."
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "services": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 8,
                    "items": {"type": "string", "minLength": 1, "maxLength": 40},
                },
            },
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "checked_at_unix", "services"],
            "properties": {
                "status": {"type": "string", "enum": ["healthy", "degraded"]},
                "checked_at_unix": {"type": "integer"},
                "services": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["service", "url", "ok", "http_status", "detail", "latency_ms"],
                        "properties": {
                            "service": {"type": "string"},
                            "url": {"type": "string"},
                            "ok": {"type": "boolean"},
                            "http_status": {"type": "integer"},
                            "detail": {"type": "string"},
                            "latency_ms": {"type": "integer"},
                        },
                    },
                },
            },
        },
        handler=handler,
        timeout_seconds=20.0,
        tags=("read", "helpdesk"),
    )


def read_approved_log_tool(*, log_root: Path, allowlist: tuple[str, ...] = ("console.log", "gateway.log", "agent.log")) -> Tool:
    root = Path(log_root)
    allowed = frozenset(allowlist)

    def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        name = arguments["name"]
        if name not in allowed:
            raise ToolInputError(f"log {name!r} is not on the allowlist")
        max_lines = int(arguments.get("max_lines") or 40)
        max_lines = max(1, min(max_lines, _MAX_LOG_LINES))
        path = (root / name).resolve()
        if root.resolve() not in path.parents and path != root.resolve():
            raise ToolInputError("log path escaped the approved directory")
        if not path.is_file():
            return {
                "name": name,
                "found": False,
                "lines": [],
                "detail": "That approved log file is not present yet.",
            }
        size = path.stat().st_size
        if size > _MAX_LOG_BYTES:
            raise ToolError(f"log {name} is too large to read ({size} bytes)")
        text = redact_text(path.read_text(encoding="utf-8", errors="replace"))
        lines = [line[:400] for line in text.splitlines()[-max_lines:]]
        return {"name": name, "found": True, "lines": lines, "detail": f"Last {len(lines)} lines, secrets redacted."}

    return Tool(
        name="read_approved_log",
        description=(
            "Read the tail of an allowlisted diagnostic log. Secrets are redacted. "
            "Cannot open arbitrary paths."
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "pattern": _LOG_NAME},
                "max_lines": {"type": "integer", "minimum": 1, "maximum": _MAX_LOG_LINES},
            },
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "found", "lines", "detail"],
            "properties": {
                "name": {"type": "string"},
                "found": {"type": "boolean"},
                "lines": {"type": "array", "maxItems": _MAX_LOG_LINES, "items": {"type": "string"}},
                "detail": {"type": "string"},
            },
        },
        handler=handler,
        timeout_seconds=10.0,
        tags=("read", "helpdesk"),
    )


def run_safe_diagnostic_tool(*, cache_dir: Path | None = None) -> Tool:
    cache = Path(cache_dir) if cache_dir is not None else Path(os.environ.get("HELPDESK_CACHE_DIR", "/tmp/ai-helpdesk-cache"))

    def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        check = arguments["check"]
        if check == "local_disk_space":
            usage = shutil.disk_usage(str(Path.cwd()))
            free_gb = round(usage.free / (1024 ** 3), 2)
            total_gb = round(usage.total / (1024 ** 3), 2)
            ok = free_gb >= 1.0
            return {
                "check": check,
                "ok": ok,
                "summary": f"{free_gb} GiB free of {total_gb} GiB on the console host.",
                "evidence": {
                    "free_bytes": int(usage.free),
                    "total_bytes": int(usage.total),
                    "free_gib": free_gb,
                },
            }
        if check == "platform_ports":
            ports = {"qwen": 8002, "gateway": 8010, "console": 8080}
            rows = {}
            for name, port in ports.items():
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                try:
                    rows[name] = sock.connect_ex(("127.0.0.1", port)) == 0
                except OSError:
                    rows[name] = False
                finally:
                    sock.close()
            ok = any(rows.values())
            return {
                "check": check,
                "ok": ok,
                "summary": "Listening on loopback: " + ", ".join(
                    f"{name}={'yes' if open_ else 'no'}" for name, open_ in rows.items()
                ),
                "evidence": rows,
            }
        if check == "python_runtime":
            import sys

            return {
                "check": check,
                "ok": True,
                "summary": f"Python {sys.version.split()[0]} on {sys.platform}.",
                "evidence": {"version": sys.version.split()[0], "platform": sys.platform},
            }
        if check == "temp_cache":
            exists = cache.is_dir()
            files = sorted(p.name for p in cache.glob("*") if p.is_file())[:20] if exists else []
            return {
                "check": check,
                "ok": True,
                "summary": (
                    f"Helpdesk cache at {cache} has {len(files)} file(s)."
                    if exists else f"Helpdesk cache {cache} does not exist yet."
                ),
                "evidence": {"path": str(cache), "exists": exists, "files": files},
            }
        raise ToolInputError(f"unknown diagnostic {check!r}")

    return Tool(
        name="run_safe_diagnostic",
        description=(
            "Run one allowlisted local diagnostic: local_disk_space, platform_ports, "
            "python_runtime, or temp_cache. No shell and no remote control."
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["check"],
            "properties": {"check": {"type": "string", "enum": list(_DIAGNOSTICS)}},
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["check", "ok", "summary", "evidence"],
            "properties": {
                "check": {"type": "string"},
                "ok": {"type": "boolean"},
                "summary": {"type": "string"},
                "evidence": {"type": "object"},
            },
        },
        handler=handler,
        timeout_seconds=10.0,
        tags=("read", "helpdesk"),
    )


def apply_safe_remediation_tool(
    *,
    cache_dir: Path | None = None,
    flag_path: Path | None = None,
    restart_handler: RestartFn | None = None,
) -> Tool:
    cache = Path(cache_dir) if cache_dir is not None else Path(
        os.environ.get("HELPDESK_CACHE_DIR", "/tmp/ai-helpdesk-cache")
    )
    flag = Path(flag_path) if flag_path is not None else Path(
        os.environ.get("HELPDESK_MAINTENANCE_FLAG", "/tmp/ai-helpdesk-maintenance.flag")
    )

    def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        action = arguments["action"]
        if action == "clear_temp_cache":
            removed = 0
            if cache.is_dir():
                for path in cache.iterdir():
                    if path.is_file():
                        path.unlink()
                        removed += 1
            cache.mkdir(parents=True, exist_ok=True)
            return {
                "action": action,
                "applied": True,
                "detail": f"Cleared {removed} file(s) from the helpdesk temp cache.",
                "system": "local helpdesk cache",
                "needs_verification": True,
            }
        if action == "set_maintenance_flag":
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("maintenance=1\n", encoding="utf-8")
            return {
                "action": action,
                "applied": True,
                "detail": f"Maintenance flag set at {flag}.",
                "system": "local console",
                "needs_verification": True,
            }
        if action == "clear_maintenance_flag":
            if flag.exists():
                flag.unlink()
            return {
                "action": action,
                "applied": True,
                "detail": "Maintenance flag cleared.",
                "system": "local console",
                "needs_verification": True,
            }
        if restart_handler is not None and action.startswith("restart_"):
            return restart_handler(action)
        raise ToolInputError(f"remediation {action!r} is not allowlisted")

    return Tool(
        name="apply_safe_remediation",
        description=(
            "Apply one allowlisted local change after human approval: clear_temp_cache, "
            "set_maintenance_flag, or clear_maintenance_flag. Always include what changes, why, "
            "which system, risks, and how you will verify. Never claim success until a later "
            "check confirms it."
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": [
                "action", "what_changes", "why", "system", "risks", "verification_plan",
            ],
            "properties": {
                "action": {"type": "string", "enum": list(_REMEDIATIONS)},
                "what_changes": {"type": "string", "minLength": 1, "maxLength": 400},
                "why": {"type": "string", "minLength": 1, "maxLength": 400},
                "system": {"type": "string", "minLength": 1, "maxLength": 120},
                "risks": {"type": "string", "minLength": 1, "maxLength": 400},
                "verification_plan": {"type": "string", "minLength": 1, "maxLength": 400},
            },
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["action", "applied", "detail", "system", "needs_verification"],
            "properties": {
                "action": {"type": "string"},
                "applied": {"type": "boolean"},
                "detail": {"type": "string"},
                "system": {"type": "string"},
                "needs_verification": {"type": "boolean"},
            },
        },
        handler=handler,
        idempotent=False,
        requires_approval=True,
        timeout_seconds=15.0,
        tags=("write", "helpdesk"),
    )


def compose_incident_report_tool() -> Tool:
    def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        report = {
            "summary": _plain(arguments["summary"], 500),
            "severity": arguments["severity"],
            "category": arguments.get("category") or "unknown",
            "desired_outcome": _plain(arguments.get("desired_outcome") or "", 300),
            "evidence": [_plain(item, 400) for item in arguments.get("evidence") or []][:12],
            "actions_taken": [_plain(item, 400) for item in arguments.get("actions_taken") or []][:12],
            "verification": [_plain(item, 400) for item in arguments.get("verification") or []][:12],
            "next_steps": [_plain(item, 400) for item in arguments.get("next_steps") or []][:8],
            "outcome": arguments["outcome"],
        }
        return {"report": report, "ready_for_final": True}

    return Tool(
        name="compose_incident_report",
        description=(
            "Assemble the incident report fields from evidence already collected. "
            "After this tool succeeds, send a final action whose output matches the same fields."
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "severity", "outcome"],
            "properties": {
                "summary": {"type": "string", "minLength": 1, "maxLength": 500},
                "severity": {"type": "string", "enum": list(_SEVERITIES)},
                "category": {"type": "string", "enum": list(_CATEGORIES)},
                "desired_outcome": {"type": "string", "maxLength": 300},
                "evidence": {
                    "type": "array", "maxItems": 12,
                    "items": {"type": "string", "minLength": 1, "maxLength": 400},
                },
                "actions_taken": {
                    "type": "array", "maxItems": 12,
                    "items": {"type": "string", "minLength": 1, "maxLength": 400},
                },
                "verification": {
                    "type": "array", "maxItems": 12,
                    "items": {"type": "string", "minLength": 1, "maxLength": 400},
                },
                "next_steps": {
                    "type": "array", "maxItems": 8,
                    "items": {"type": "string", "minLength": 1, "maxLength": 400},
                },
                "outcome": {
                    "type": "string",
                    "enum": ["resolved", "mitigated", "needs_approval", "escalated", "blocked"],
                },
            },
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["report", "ready_for_final"],
            "properties": {
                "report": {"type": "object"},
                "ready_for_final": {"type": "boolean"},
            },
        },
        handler=handler,
        timeout_seconds=5.0,
        tags=("read", "helpdesk"),
    )


def helpdesk_tools(
    *,
    log_root: Path | None = None,
    cache_dir: Path | None = None,
    flag_path: Path | None = None,
    services: dict[str, str] | None = None,
    probe: ProbeFn | None = None,
) -> list[Tool]:
    logs = Path(log_root) if log_root is not None else Path(
        os.environ.get("HELPDESK_LOG_DIR", "/tmp/ai-helpdesk-logs")
    )
    return [
        classify_it_issue_tool(),
        check_platform_health_tool(services=services, probe=probe),
        read_approved_log_tool(log_root=logs),
        run_safe_diagnostic_tool(cache_dir=cache_dir),
        apply_safe_remediation_tool(cache_dir=cache_dir, flag_path=flag_path),
        compose_incident_report_tool(),
    ]


__all__ = [
    "apply_safe_remediation_tool",
    "check_platform_health_tool",
    "classify_it_issue_tool",
    "compose_incident_report_tool",
    "default_service_urls",
    "helpdesk_tools",
    "read_approved_log_tool",
    "run_safe_diagnostic_tool",
]
