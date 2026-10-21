"""Worker that runs on a computer the operator chose to enrol.

It opens an outbound connection to a loopback console, sends the fixed
diagnostic, and keeps the device secret in a local file. It has no command
channel and will not post to a public address.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from integrations.endpoint import _CHECK_PROCEDURES, assert_safe_state_path, collect_local_diagnostics
from integrations.errors import InvalidRequest
from integrations.state_guard import StatePermissionError, assert_private, restrict_private

_DIAGNOSTIC_KEYS = (
    "os_family", "os_version", "disk_free_bytes", "disk_total_bytes",
    "memory_total_bytes", "boot_time_unix", "collected_at_unix",
)


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


def console_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "http"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port is None
    ):
        raise InvalidRequest("the worker only talks to http://127.0.0.1 or http://localhost with a port")
    if parsed.path not in {"", "/"}:
        raise InvalidRequest("pass the console origin, not a path")
    return f"http://{parsed.hostname}:{parsed.port}"


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _RefuseRedirects)


def _post(origin: str, path: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        origin + path,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with _opener().open(request, timeout=10) as response:
            raw = response.read(8192)
    except urllib.error.HTTPError as exc:
        exc.read(500)
        raise InvalidRequest(f"console refused the check-in ({exc.code})") from exc
    except urllib.error.URLError as exc:
        raise InvalidRequest("console could not be reached") from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidRequest("console returned an unreadable response") from exc
    if not isinstance(parsed, dict):
        raise InvalidRequest("console returned an unreadable response")
    return parsed


def write_secret_file(path: Path, value: str) -> None:
    safe = assert_safe_state_path(path)
    safe.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(safe, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(value)
    try:
        restrict_private(safe)
    except StatePermissionError as exc:
        try:
            safe.unlink()
        except OSError:
            pass
        raise InvalidRequest("device secret file could not be made private") from exc


def read_secret_file(path: Path) -> str:
    safe = assert_safe_state_path(path)
    try:
        assert_private(safe)
    except StatePermissionError as exc:
        raise InvalidRequest("device secret file is not private") from exc
    value = safe.read_text(encoding="utf-8").strip()
    if len(value) < 32:
        raise InvalidRequest("device secret file is not usable")
    return value


def enrol(origin: str, code: str, display_name: str, secret_path: Path) -> str:
    """Create a device secret locally and exchange a one-time code for a device id."""
    target = console_origin(origin)
    secret = secrets.token_urlsafe(32)
    result = _post(target, "/api/devices/enroll", {
        "code": code,
        "display_name": display_name,
        "device_secret": secret,
    })
    device_id = result.get("device_id")
    if not isinstance(device_id, str) or len(device_id) != 32:
        raise InvalidRequest("console did not return a device id")
    write_secret_file(secret_path, secret)
    return device_id


def _clip(value: object, limit: int = 80) -> str:
    text = " ".join(str(value).split())
    return text[:limit]


def summarise_live_check(procedure_id: str, raw: dict, collected_at: int) -> dict:
    """Turn one collector result into the fields the console will store."""
    source = raw.get("evidence_source")
    ok = bool(raw.get("ok")) and source == "live_windows"
    if not ok:
        source = "unavailable"
    parts = [procedure_id]
    for key in ("spooler", "present_count", "gateway_ok", "dns_localhost_ok", "detail", "status"):
        if key in raw and raw[key] not in (None, ""):
            parts.append(f"{key}={_clip(raw[key], 40)}")
    for key in ("disks", "services", "events", "problems", "printers", "addresses"):
        rows = raw.get(key)
        if isinstance(rows, list):
            parts.append(f"{key}={len(rows)}")
    return {
        "procedure_id": procedure_id,
        "evidence_source": source,
        "ok": ok,
        "collected_at_unix": collected_at,
        "summary": _clip("; ".join(parts), 240),
    }


def collect_registered_checks(collect=None, clock=None) -> list[dict]:
    """Read-only registered procedures. A missing collector is reported as unavailable."""
    from time import time

    now = int((clock or time)())
    if collect is None and os.name == "nt":
        from windows_repair.providers import LiveWindowsProvider

        collector = LiveWindowsProvider().collect
    else:
        collector = collect
    checks = []
    for procedure_id in _CHECK_PROCEDURES:
        if collector is None:
            raw = {"ok": False, "evidence_source": "unavailable", "detail": "no live collector on this operating system"}
        else:
            try:
                raw = collector(procedure_id)
            except Exception as exc:  # noqa: BLE001 — one failed check must not hide the others
                raw = {"ok": False, "evidence_source": "unavailable", "detail": type(exc).__name__}
        if not isinstance(raw, dict):
            raw = {"ok": False, "evidence_source": "unavailable", "detail": "unreadable collector result"}
        checks.append(summarise_live_check(procedure_id, raw, now))
    return checks


def submit_report(origin: str, secret_path: Path, collect=None) -> dict:
    target = console_origin(origin)
    secret = read_secret_file(secret_path)
    diagnostic = collect_local_diagnostics()
    body = {key: diagnostic[key] for key in _DIAGNOSTIC_KEYS}
    body["checks"] = collect_registered_checks(collect, clock=lambda: diagnostic["collected_at_unix"])
    return _post(target, "/api/devices/report", body, {"Authorization": f"Bearer {secret}"})


def remove_secret(secret_path: Path) -> None:
    """Delete the local device secret. This does not revoke the server record."""
    safe = assert_safe_state_path(secret_path)
    if safe.is_file():
        safe.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a read-only computer check-in to the local console.")
    parser.add_argument("action", choices=("enrol", "report", "remove"))
    parser.add_argument("--console", default="")
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--code", default="")
    parser.add_argument("--name", default="Office PC")
    args = parser.parse_args(argv)
    try:
        if args.action == "enrol":
            if not args.console:
                print("ERROR: --console is required", file=sys.stderr)
                return 2
            if not args.code:
                print("ERROR: an enrolment code is required", file=sys.stderr)
                return 2
            device_id = enrol(args.console, args.code, args.name, Path(args.token_file))
            print(f"enrolled device {device_id}")
            print("the device secret was saved and is not printed")
            return 0
        if args.action == "remove":
            remove_secret(Path(args.token_file))
            print("local device secret deleted; revoke the device in the console if it should stop checking in")
            return 0
        if not args.console:
            print("ERROR: --console is required", file=sys.stderr)
            return 2
        result = submit_report(args.console, Path(args.token_file))
        print(f"stored diagnostic for {result.get('device_id', 'unknown device')}")
        return 0
    except InvalidRequest as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
