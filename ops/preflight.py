"""Readiness checks for this checkout. Nothing here starts or stops a service."""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import sys
from pathlib import Path
from typing import Any, Mapping

MIN_FREE_BYTES = 1 << 30
MODEL_PORT = 8002
GATEWAY_PORT = 8010
CONSOLE_PORT = 8080


def _is_absolute_state_path(value: str) -> bool:
    """True for POSIX absolutes and Windows drive/UNC paths on any host OS."""
    if Path(value).is_absolute():
        return True
    if len(value) >= 3 and value[0].isalpha() and value[1] == ":" and value[2] in "\\/":
        return True
    return value.startswith("\\\\") or value.startswith("//")


def probe_port(port: int, timeout: float = 0.2) -> bool:
    """Return whether something is already listening. This does not bind the port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def yaml_importable() -> bool:
    try:
        import yaml  # noqa: F401
    except Exception:
        return False
    return True


def active_operator_count(path: Path) -> int | None:
    """Count enabled operators. Password hashes are not returned."""
    if not path.is_file() or path.is_symlink():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    rows = raw.get("operators") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return None
    count = 0
    for item in rows:
        if isinstance(item, dict) and item.get("operator_id") and item.get("username") and not item.get("disabled"):
            count += 1
    return count


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    if status not in {"pass", "fail", "not_configured"}:
        raise ValueError("unknown preflight status")
    return {"name": name, "status": status, "detail": detail}


def run_preflight(
    env: Mapping[str, str],
    *,
    disk_free_bytes: int,
    ports_open: Mapping[int, bool],
    yaml_ok: bool,
    operator_count: int | None,
) -> dict[str, Any]:
    """Report readiness. Secret values in ``env`` are never copied into the result."""
    checks: list[dict[str, str]] = []
    gateway = str(env.get("PLATFORM_GATEWAY_URL", "")).strip()
    if not gateway:
        checks.append(_check("gateway_url", "pass", "PLATFORM_GATEWAY_URL is unset and the loopback default applies"))
    else:
        from web.server import validate_gateway_url

        try:
            validate_gateway_url(gateway)
        except ValueError:
            checks.append(_check("gateway_url", "fail", "PLATFORM_GATEWAY_URL is not a loopback http URL with a port"))
        else:
            checks.append(_check("gateway_url", "pass", "PLATFORM_GATEWAY_URL is a loopback http URL"))

    repair = str(env.get("REPAIR_DEVICE_STATE", "")).strip()
    if not repair:
        checks.append(_check("repair_state", "not_configured", "REPAIR_DEVICE_STATE is unset"))
    elif not _is_absolute_state_path(repair):
        checks.append(_check("repair_state", "fail", "REPAIR_DEVICE_STATE must be an absolute path"))
    else:
        checks.append(_check("repair_state", "pass", "REPAIR_DEVICE_STATE is an absolute path"))

    if disk_free_bytes < MIN_FREE_BYTES:
        checks.append(_check("disk", "fail", "free disk is below 1 GiB"))
    else:
        checks.append(_check("disk", "pass", "free disk is at least 1 GiB"))

    if yaml_ok:
        checks.append(_check("pyyaml", "pass", "PyYAML imports"))
    else:
        checks.append(_check(
            "pyyaml",
            "fail",
            "PyYAML does not import. Registry tests cannot be treated as validated.",
        ))

    from integrations.microsoft_oauth import client_id_source

    client_source = client_id_source(dict(env))
    if client_source:
        checks.append(_check("microsoft", "pass", f"{client_source} is present"))
    else:
        checks.append(_check(
            "microsoft",
            "not_configured",
            "MICROSOFT_CLIENT_ID is unset and MICROSOFT_CLIENT_ID_FILE is unset, unreadable, or not private",
        ))

    model_open = bool(ports_open.get(MODEL_PORT))
    gateway_open = bool(ports_open.get(GATEWAY_PORT))
    console_open = bool(ports_open.get(CONSOLE_PORT))
    checks.append(_check(
        "model",
        "pass" if model_open else "not_configured",
        "model port 8002 is listening" if model_open else "NOT CONFIGURED. The model server is not listening and was not started.",
    ))
    checks.append(_check(
        "gateway",
        "pass" if gateway_open else "not_configured",
        "gateway port 8010 is listening" if gateway_open else "NOT CONFIGURED. The gateway is not listening and was not started.",
    ))
    checks.append(_check(
        "console_port",
        "pass" if console_open else "not_configured",
        "console port 8080 is listening" if console_open else "The console port is not listening. It was not started.",
    ))

    if operator_count is None:
        checks.append(_check("operators", "fail", "operator provisioning is missing or unreadable"))
    elif operator_count < 1:
        checks.append(_check("operators", "fail", "no enabled operator is provisioned"))
    else:
        checks.append(_check("operators", "pass", "at least one enabled operator is provisioned"))

    ready = all(item["status"] == "pass" for item in checks)
    return {"ready": ready, "checks": checks}


def collect_local(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Probe this machine. This does not start a listener or a model."""
    source = env if env is not None else __import__("os").environ
    auth = str(source.get("OPERATOR_AUTH_DIR", "")).strip()
    count = active_operator_count(Path(auth) / "operators.json") if auth else None
    return run_preflight(
        source,
        disk_free_bytes=shutil.disk_usage(Path.cwd()).free,
        ports_open={
            MODEL_PORT: probe_port(MODEL_PORT),
            GATEWAY_PORT: probe_port(GATEWAY_PORT),
            CONSOLE_PORT: probe_port(CONSOLE_PORT),
        },
        yaml_ok=yaml_importable(),
        operator_count=count,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report local readiness. Does not start services.")
    parser.parse_args(argv)
    report = collect_local()
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
