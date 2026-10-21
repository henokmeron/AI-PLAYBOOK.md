"""Worker that runs on the enrolled computer.

Loopback consoles may use http://127.0.0.1 or http://localhost. Any other host
requires HTTPS. Certificate verification stays on. Redirects are refused.
The worker runs registered read-only collectors locally and submits the result.
It does not accept a shell command, and it does not decide that a repair worked.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
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


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
_MAX_RESPONSE_BYTES = 65536


def console_origin(value: str) -> str:
    """Loopback may use HTTP. Every other host must be HTTPS with a checked certificate."""
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower()
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.port is None
        or not host
    ):
        raise InvalidRequest("pass a console origin with a host and port, and without a user or query")
    if parsed.path not in {"", "/"}:
        raise InvalidRequest("pass the console origin, not a path")
    if parsed.scheme == "http" and host in _LOOPBACK_HOSTS:
        return f"http://{host}:{parsed.port}"
    if parsed.scheme == "https":
        return f"https://{host}:{parsed.port}"
    raise InvalidRequest(
        "remote endpoints require https with certificate validation; "
        "loopback may use http://127.0.0.1 or http://localhost"
    )


def tls_context() -> ssl.SSLContext:
    """Default trust store. Verification is required and is not switched off."""
    context = ssl.create_default_context()
    extra = os.environ.get("ENDPOINT_CA_FILE", "").strip()
    if extra:
        context.load_verify_locations(extra)
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise InvalidRequest("TLS certificate verification cannot be disabled")
    return context


def _opener() -> urllib.request.OpenerDirector:
    https = urllib.request.HTTPSHandler(context=tls_context())
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _RefuseRedirects, https)


def _post(
    origin: str,
    path: str,
    payload: dict,
    headers: dict[str, str] | None = None,
    *,
    timeout: float = 10,
    limit: int = _MAX_RESPONSE_BYTES,
) -> dict:
    body = json.dumps(payload).encode("utf-8")
    if len(body) > limit:
        raise InvalidRequest("the request is too large")
    request = urllib.request.Request(
        console_origin(origin) + path,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with _opener().open(request, timeout=timeout) as response:
            raw = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        exc.read(500)
        raise InvalidRequest(f"console refused the check-in ({exc.code})") from exc
    except ssl.SSLError as exc:
        raise InvalidRequest("the console certificate was rejected") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLError):
            raise InvalidRequest("the console certificate was rejected") from exc
        raise InvalidRequest("console could not be reached") from exc
    if len(raw) > limit:
        raise InvalidRequest("the console response is too large")
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


def write_job_credential(path: Path, credential: dict[str, str]) -> None:
    """Store the one-time device secret and MAC key. The file is private afterwards."""
    required = ("device_id", "tenant_id", "device_secret", "mac_key")
    if any(not isinstance(credential.get(name), str) or len(str(credential.get(name))) < 8 for name in required):
        raise InvalidRequest("endpoint credential is not usable")
    if len(credential["device_secret"]) < 32 or len(credential["mac_key"]) != 64:
        raise InvalidRequest("endpoint credential is not usable")
    write_secret_file(path, json.dumps({name: credential[name] for name in required}, sort_keys=True))


def read_job_credential(path: Path) -> dict[str, str]:
    raw = read_secret_file(path)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidRequest("endpoint credential is not usable") from exc
    if not isinstance(parsed, dict):
        raise InvalidRequest("endpoint credential is not usable")
    credential = {name: str(parsed.get(name) or "") for name in ("device_id", "tenant_id", "device_secret", "mac_key")}
    if len(credential["device_secret"]) < 32 or len(credential["mac_key"]) != 64 or len(credential["device_id"]) < 8:
        raise InvalidRequest("endpoint credential is not usable")
    return credential


def execute_assigned_job(
    envelope: dict[str, Any],
    *,
    device_id: str,
    tenant_id: str,
    mac_key: str,
    provider: Any,
    now: float,
) -> dict[str, Any]:
    """Verify the job, run the collector in this process, and sign the result.

    The collector's claim that a repair succeeded is discarded.
    """
    from windows_repair.device_store import _canonical, job_body, result_signing_view
    from windows_repair.engine import RepairDenied
    from windows_repair.providers import LIVE_PROCEDURES

    body = job_body(envelope)
    if body.get("device_id") != device_id or body.get("tenant_id") != tenant_id:
        raise RepairDenied("job is not for this endpoint")
    if body.get("approval_id") is not None or "lifecycle" in body:
        raise RepairDenied("device job lifecycle is not taken from the payload")
    if any(name in body for name in ("command", "shell", "argv", "script")):
        raise RepairDenied("endpoint jobs cannot carry a command")
    procedure_id = str(body.get("procedure_id") or "")
    if procedure_id not in LIVE_PROCEDURES:
        raise RepairDenied("this device job is not a read-only diagnostic")
    if now >= float(body.get("expires_at") or 0):
        raise RepairDenied("job expired")
    expected = hmac.new(bytes.fromhex(mac_key), _canonical(body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(envelope.get("device_signature") or "")):
        raise RepairDenied("job signature is invalid")
    try:
        raw = provider.collect(procedure_id)
    except Exception as exc:  # noqa: BLE001 — the worker reports the failure instead of raising a repair
        raw = {
            "evidence_source": "unavailable",
            "ok": False,
            "status": "failed",
            "detail": type(exc).__name__,
        }
    if not isinstance(raw, dict):
        raw = {"evidence_source": "unavailable", "ok": False, "status": "failed", "detail": "unreadable collector result"}
    raw = dict(raw)
    if isinstance(raw.get("collected_at_unix"), bool) or not isinstance(raw.get("collected_at_unix"), (int, float)):
        raw.pop("collected_at_unix", None)
    view = result_signing_view(raw, procedure_id)
    signed = dict(view)
    signed["result_signature"] = hmac.new(bytes.fromhex(mac_key), _canonical(view), hashlib.sha256).hexdigest()
    signed["problem_resolved"] = False
    signed["repair_authority"] = False
    return signed


def run_pending_jobs(
    origin: str,
    credential_path: Path,
    *,
    provider: Any | None = None,
    attempts: int = 3,
    timeout: float = 10,
) -> list[dict[str, Any]]:
    """Pull jobs for this device, collect locally, and submit the signed result."""
    import time

    credential = read_job_credential(credential_path)
    if provider is None:
        marker = os.environ.get("ENDPOINT_COLLECTOR_MARKER", "").strip()
        if marker:
            provider = _MarkerCollector(marker)
        elif os.name == "nt":
            from windows_repair.providers import LiveWindowsProvider

            provider = LiveWindowsProvider()
        else:
            raise InvalidRequest("no live collector is available on this operating system")
    target = console_origin(origin)
    secret = credential["device_secret"]
    headers = {"Authorization": f"Bearer {secret}"}
    _post(target, "/api/repair/device/check-in", {}, headers, timeout=timeout)
    listed = _post(target, "/api/repair/device/jobs", {}, headers, timeout=timeout)
    jobs = listed.get("jobs")
    if not isinstance(jobs, list):
        raise InvalidRequest("console returned an unreadable response")
    stored: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict) or job.get("device_id") != credential["device_id"]:
            raise InvalidRequest("console offered a job for a different device")
        if job.get("tenant_id") != credential["tenant_id"]:
            raise InvalidRequest("console offered a job for a different organisation")
        result = execute_assigned_job(
            job,
            device_id=credential["device_id"],
            tenant_id=credential["tenant_id"],
            mac_key=credential["mac_key"],
            provider=provider,
            now=time.time(),
        )
        stored.append(_submit_result(target, headers, job, result, attempts=attempts, timeout=timeout))
    return stored


def _submit_result(
    origin: str,
    headers: dict[str, str],
    job: dict[str, Any],
    result: dict[str, Any],
    *,
    attempts: int,
    timeout: float,
) -> dict[str, Any]:
    last: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            return _post(origin, "/api/repair/device/result", {"job": job, "result": result}, headers, timeout=timeout)
        except InvalidRequest as exc:
            last = exc
            if "could not be reached" not in str(exc):
                raise
    assert last is not None
    raise last


class _MarkerCollector:
    """Test collector. It records this process id and does not claim a live Windows read."""

    def __init__(self, path: str) -> None:
        self.path = path

    def collect(self, procedure_id: str) -> dict[str, Any]:
        Path(self.path).write_text(str(os.getpid()), encoding="utf-8")
        return {
            "evidence_source": "mock",
            "mocked": True,
            "ok": True,
            "status": "collected",
            "procedure_id": procedure_id,
        }


def remove_secret(secret_path: Path) -> None:
    """Delete the local device secret. This does not revoke the server record."""
    safe = assert_safe_state_path(secret_path)
    if safe.is_file():
        safe.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run read-only checks on this enrolled computer.")
    parser.add_argument("action", choices=("enrol", "report", "remove", "jobs"))
    parser.add_argument("--console", default="")
    parser.add_argument("--token-file", default="")
    parser.add_argument("--credential", default="")
    parser.add_argument("--code", default="")
    parser.add_argument("--name", default="Office PC")
    args = parser.parse_args(argv)
    from windows_repair.engine import RepairDenied
    try:
        if args.action == "jobs":
            if not args.console or not args.credential:
                print("ERROR: --console and --credential are required", file=sys.stderr)
                return 2
            results = run_pending_jobs(args.console, Path(args.credential))
            print(f"submitted {len(results)} job result(s); repair_authority is false")
            return 0
        if not args.token_file:
            print("ERROR: --token-file is required", file=sys.stderr)
            return 2
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
    except (InvalidRequest, RepairDenied) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
