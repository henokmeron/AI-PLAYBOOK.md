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
import platform
import re
import secrets
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from integrations.endpoint import (
    FIXTURE_LABEL,
    _CHECK_PROCEDURES,
    assert_safe_state_path,
    collect_local_diagnostics,
)
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
# The console rejects a check-in body larger than this. Stay inside it.
CONSOLE_REPORT_LIMIT = 4096
_CONSOLE_ORIGIN = "http://127.0.0.1:8080"
_TOKEN_FILE = '"$env:LOCALAPPDATA\\AI-PLAYBOOK\\device-secret"'
_SAFE_CODE = re.compile(r"[A-Za-z0-9_-]{16,80}\Z")
_DEV_PC = "banya-family-pl"


def acceptance_role(fixture_label: str = "") -> str:
    """Say whether this invocation may be treated as the second Windows computer.

    The labelled local fixture is explicit. Every other run is still not
    recorded evidence: a loopback tunnel is also how a different physical PC
    reaches the console, so the address alone cannot prove which machine it is.
    """
    label = " ".join(fixture_label.split()).casefold()
    if not label:
        return "not-recorded-as-second-endpoint"
    if label != FIXTURE_LABEL:
        raise InvalidRequest("the only local fixture label is not-the-second-endpoint")
    return FIXTURE_LABEL


def local_hostname() -> str:
    return platform.node()


def dev_pc_enrol_blocked(hostname: str, fixture_label: str) -> bool:
    """This development PC can rehearse only with the fixture label."""
    folded = " ".join(str(hostname).split()).casefold().rstrip(".")
    if folded != _DEV_PC and not folded.startswith(_DEV_PC + "."):
        return False
    label = " ".join(str(fixture_label).split()).casefold()
    return label != FIXTURE_LABEL


def normalize_argv(argv: list[str]) -> list[str]:
    """Keep a one-time code that starts with '-' attached to --code.

    ``--code -abc`` is rejected by argparse before the console sees it.
    ``--code=-abc`` is one argument and is accepted.
    """
    fixed: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--code" and index + 1 < len(argv):
            fixed.append("--code=" + argv[index + 1])
            index += 2
            continue
        fixed.append(item)
        index += 1
    return fixed


def operator_commands(code: str) -> dict[str, Any]:
    """The two commands for the other laptop. The code is attached with '='."""
    if not isinstance(code, str) or not _SAFE_CODE.fullmatch(code):
        raise InvalidRequest("enrolment code cannot be shown safely")
    enrol = (
        "python -m integrations.endpoint_worker enrol "
        f"--console {_CONSOLE_ORIGIN} --code={code} --name=\"Office PC\" "
        f"--token-file={_TOKEN_FILE}"
    )
    report = (
        "python -m integrations.endpoint_worker report "
        f"--console {_CONSOLE_ORIGIN} --token-file={_TOKEN_FILE}"
    )
    return {"commands": {"enrol": enrol, "report": report}}


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _hardware_matches(checks: list[dict], hardware: dict | None) -> None:
    identity = next(
        (item for item in checks if isinstance(item, dict) and item.get("procedure_id") == "hw.identity.inspect"),
        None,
    )
    if hardware and hardware.get("status") == "collected" and (not identity or not identity.get("ok")):
        raise InvalidRequest("complete hardware identity was not reported as a live check")
    if identity and identity.get("ok") and (not hardware or hardware.get("status") != "collected"):
        raise InvalidRequest("a successful hardware check needs a complete identity")


def build_report_body(diagnostic: dict, checks: list[dict], hardware: dict | None = None) -> dict:
    """The check-in body. It must fit the console limit or the report is not stored."""
    body = {key: diagnostic[key] for key in _DIAGNOSTIC_KEYS}
    body["checks"] = checks
    if hardware is not None:
        body["hardware"] = hardware
    _hardware_matches(checks, hardware)
    if len(_json_bytes(body)) > CONSOLE_REPORT_LIMIT:
        raise InvalidRequest("the diagnostic report is too large for the console")
    return body


def _safe_error_detail(raw: bytes) -> str:
    """A short console message. Do not repeat a secret, token, or code."""
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    message = parsed.get("error")
    if not isinstance(message, str):
        return ""
    text = " ".join(message.split())
    if not text or len(text) > 180:
        return ""
    lowered = text.casefold()
    if any(word in lowered for word in ("secret", "token", "bearer", "password", "mac_key")):
        return ""
    return text


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
    body = _json_bytes(payload)
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
        detail = _safe_error_detail(exc.read(500))
        message = f"console refused the check-in ({exc.code})"
        if detail:
            message = f"{message}: {detail}"
        raise InvalidRequest(message) from exc
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


def _discard_secret(path: Path) -> None:
    try:
        remove_secret(path)
    except OSError:
        return


def enrol(origin: str, code: str, display_name: str, secret_path: Path) -> str:
    """Write the device secret, then exchange a one-time code for a device id.

    The code is not sent until the secret file can be stored. A refused
    enrolment deletes that file so the code can be used again only if the
    console did not accept it. An existing secret file is left unchanged.
    """
    target = console_origin(origin)
    safe = assert_safe_state_path(secret_path)
    if safe.exists():
        raise InvalidRequest("device secret file already exists; remove it before enrolling again")
    secret = secrets.token_urlsafe(32)
    write_secret_file(safe, secret)
    try:
        result = _post(target, "/api/devices/enroll", {
            "code": code,
            "display_name": display_name,
            "device_secret": secret,
        })
    except Exception:
        _discard_secret(safe)
        raise
    device_id = result.get("device_id")
    if not isinstance(device_id, str) or len(device_id) != 32:
        _discard_secret(safe)
        raise InvalidRequest("console did not return a device id")
    return device_id


def _clip(value: object, limit: int = 80) -> str:
    text = " ".join(str(value).split())
    return text[:limit]


def _identity_summary(raw: dict) -> str:
    status = _clip(raw.get("status") or "unavailable", 20)
    parts = [f"status={status}"]
    if " ".join(str(raw.get("fixture") or "").split()).casefold() == "synthetic":
        parts.append("fixture=synthetic")
    if status == "collected":
        parts.append(f"manufacturer={_clip(raw.get('manufacturer'), 32)}")
        parts.append(f"model={_clip(raw.get('model'), 32)}")
        parts.append(f"bios={_clip(raw.get('bios_version') or raw.get('bios'), 24)}")
        parts.append(f"cpu={_clip(raw.get('cpu'), 32)}")
        parts.append(f"ram_available={_clip(raw.get('memory_available_bytes'), 20)}")
        parts.append(f"ram_total={_clip(raw.get('memory_total_bytes'), 20)}")
    return _clip("; ".join(parts), 240)


def _identity_is_complete(raw: dict) -> bool:
    if str(raw.get("status") or "").strip().casefold() != "collected":
        return False
    for key in ("manufacturer", "model", "bios_vendor", "bios_version", "cpu"):
        if not str(raw.get(key) or "").strip():
            return False
    available = raw.get("memory_available_bytes")
    total = raw.get("memory_total_bytes")
    if isinstance(available, bool) or isinstance(total, bool):
        return False
    if not isinstance(available, int) or not isinstance(total, int):
        return False
    return total >= 1 and 0 <= available <= total


def summarise_live_check(procedure_id: str, raw: dict, collected_at: int) -> dict:
    """Turn one collector result into the fields the console will store."""
    source = raw.get("evidence_source")
    fixture = " ".join(str(raw.get("fixture") or "").split()).casefold()
    status = str(raw.get("status") or "").strip().casefold()
    blocked = bool(fixture) or status in {"unavailable", "unsupported", "permission-denied"}
    ok = bool(raw.get("ok")) and source == "live_windows" and not blocked
    if procedure_id == "hw.identity.inspect" and (fixture == "synthetic" or not _identity_is_complete(raw)):
        ok = False
    if not ok:
        source = "unavailable"
    if procedure_id == "hw.identity.inspect":
        summary = _identity_summary(raw)
        if not summary:
            summary = "status=unavailable"
        return {
            "procedure_id": procedure_id,
            "evidence_source": source,
            "ok": ok,
            "collected_at_unix": collected_at,
            "summary": summary,
        }
    parts = [procedure_id]
    for key in (
        "spooler", "present_count", "gateway_ok", "dns_localhost_ok", "detail", "status",
        "last_boot", "free_memory_kb", "total_memory_kb", "cpu_load_percent",
    ):
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


def _default_collector(procedure_id: str, hardware_box: dict[str, dict]) -> dict:
    """Registered collectors only. The procedure id is not a shell command."""
    if procedure_id == "hw.identity.inspect":
        from windows_repair.hardware_inventory import collect_hardware_identity

        reading = collect_hardware_identity()
        hardware_box["reading"] = reading
        return reading
    if os.name != "nt":
        return {
            "ok": False,
            "evidence_source": "unavailable",
            "detail": "no live collector on this operating system",
        }
    from windows_repair.providers import LiveWindowsProvider

    return LiveWindowsProvider().collect(procedure_id)


def submit_report(origin: str, secret_path: Path, collect=None) -> dict:
    target = console_origin(origin)
    secret = read_secret_file(secret_path)
    diagnostic = collect_local_diagnostics()
    hardware_box: dict[str, dict] = {}

    def _collect(procedure_id: str) -> dict:
        return _default_collector(procedure_id, hardware_box)

    checks = collect_registered_checks(collect or _collect, clock=lambda: diagnostic["collected_at_unix"])
    hardware = None
    if "reading" in hardware_box:
        from windows_repair.hardware_inventory import stored_hardware

        hardware = stored_hardware(hardware_box["reading"])
    body = build_report_body(diagnostic, checks, hardware)
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
    parser.add_argument("--fixture-label", default="")
    args = parser.parse_args(normalize_argv(list(argv) if argv is not None else sys.argv[1:]))
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
        role = acceptance_role(args.fixture_label)
        if args.fixture_label and args.name.strip().casefold() != FIXTURE_LABEL:
            print("ERROR: a labelled fixture must use the name not-the-second-endpoint", file=sys.stderr)
            return 2
        if args.action == "enrol":
            if dev_pc_enrol_blocked(local_hostname(), args.fixture_label):
                print(
                    "ERROR: BANYA-FAMILY-PL is this development PC. Enrolment here is not the second "
                    "Windows computer. On the other laptop, create a one-time code in IT Helpdesk, then run "
                    "python -m integrations.endpoint_worker enrol and report against http://127.0.0.1:8080.",
                    file=sys.stderr,
                )
                return 2
            if not args.console:
                print("ERROR: --console is required", file=sys.stderr)
                return 2
            if not args.code:
                print("ERROR: an enrolment code is required", file=sys.stderr)
                return 2
            device_id = enrol(args.console, args.code, args.name, Path(args.token_file))
            print(f"enrolled device {device_id}")
            print("the device secret was saved and is not printed")
            print(f"acceptance_role={role}")
            if role == FIXTURE_LABEL:
                print("this run is a local fixture and does not satisfy the second Windows endpoint gate")
            else:
                print("this computer is not recorded as the second Windows endpoint")
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
        print(f"acceptance_role={role}")
        if role == FIXTURE_LABEL:
            print("this run is a local fixture and does not satisfy the second Windows endpoint gate")
        else:
            print("this computer is not recorded as the second Windows endpoint")
        return 0
    except (InvalidRequest, RepairDenied) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
