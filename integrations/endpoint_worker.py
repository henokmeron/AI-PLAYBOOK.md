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

from integrations.endpoint import assert_safe_state_path, collect_local_diagnostics
from integrations.errors import InvalidRequest

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
    if os.name == "posix":
        os.chmod(safe, 0o600)


def read_secret_file(path: Path) -> str:
    safe = assert_safe_state_path(path)
    info = safe.lstat()
    if os.name == "posix" and info.st_mode & 0o077:
        raise InvalidRequest("device secret file permissions are too open")
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


def submit_report(origin: str, secret_path: Path) -> dict:
    target = console_origin(origin)
    secret = read_secret_file(secret_path)
    diagnostic = collect_local_diagnostics()
    body = {key: diagnostic[key] for key in _DIAGNOSTIC_KEYS}
    return _post(target, "/api/devices/report", body, {"Authorization": f"Bearer {secret}"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a read-only computer check-in to the local console.")
    parser.add_argument("action", choices=("enrol", "report"))
    parser.add_argument("--console", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--code", default="")
    parser.add_argument("--name", default="Office PC")
    args = parser.parse_args(argv)
    try:
        if args.action == "enrol":
            if not args.code:
                print("ERROR: an enrolment code is required", file=sys.stderr)
                return 2
            device_id = enrol(args.console, args.code, args.name, Path(args.token_file))
            print(f"enrolled device {device_id}")
            print("the device secret was saved and is not printed")
            return 0
        result = submit_report(args.console, Path(args.token_file))
        print(f"stored diagnostic for {result.get('device_id', 'unknown device')}")
        return 0
    except InvalidRequest as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
