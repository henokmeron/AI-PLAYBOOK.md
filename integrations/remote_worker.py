"""Run one allowlisted job from a file or stdin. Do not contact the network.

Usage: python -m integrations.remote_worker poll-once [--jobs FILE]

The process prints one JSON result. It does not pass live=True unless the
operator adds ``--live``. Even then, the default runner stays disabled until
REMOTE_IT_WORK_LIVE=1. Tests inject a runner and must not call the default.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any, Callable, TextIO

from integrations.remote_work import (
    HEARTBEAT,
    WorkRefused,
    _scrub,
    execute,
    heartbeat_record,
)

WORKER_VERSION = "2026.10.23"


def poll_once(
    payload: dict[str, Any],
    *,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    live: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    """Claim the first approved job for this device and return one result."""
    if not isinstance(payload, dict):
        raise WorkRefused("jobs payload must be an object")
    if _surveillance(payload):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    device_id = payload.get("device_id")
    if not isinstance(device_id, str):
        raise WorkRefused("device id is not valid")
    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        raise WorkRefused("jobs must be a list")
    moment = time.time() if now is None else now
    chosen = _first_job(device_id, jobs, moment)
    if chosen is None:
        if payload.get("heartbeat") is True:
            record = heartbeat_record(
                device_id,
                payload.get("utc") if isinstance(payload.get("utc"), str) else "",
                payload.get("worker_version") if isinstance(payload.get("worker_version"), str) else "",
            )
            return {
                "device_id": device_id,
                "action": HEARTBEAT,
                "target": device_id,
                "state": "succeeded",
                "result": record,
                "error": None,
            }
        return {
            "device_id": device_id,
            "action": None,
            "target": None,
            "state": "idle",
            "result": None,
            "error": None,
        }
    job = json.loads(json.dumps(chosen))
    password = _pop_password(job)
    handler = job.get("handler_input") if isinstance(job.get("handler_input"), dict) else {}
    if password is not None:
        handler = dict(handler)
        handler["password"] = password
    try:
        result = execute(job, live=live, runner=runner, handler_input=handler, now=moment)
    except WorkRefused as exc:
        message = exc.message
        if isinstance(password, str) and password and password in message:
            message = "result was refused"
        return {
            "device_id": device_id,
            "order_id": chosen.get("id"),
            "action": chosen.get("action"),
            "target": chosen.get("target"),
            "state": "refused",
            "result": None,
            "error": message,
        }
    redact = (password,) if isinstance(password, str) else ()
    safe = _scrub(result, redact)
    executed = bool(isinstance(safe, dict) and safe.get("executed"))
    return {
        "device_id": device_id,
        "order_id": chosen.get("id"),
        "action": chosen.get("action"),
        "target": chosen.get("target"),
        "state": "succeeded" if executed else "planned",
        "result": safe,
        "error": None,
    }


def main(
    argv: list[str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = stdout or sys.stdout
    if not args or args[0] != "poll-once":
        out.write(json.dumps({
            "state": "refused",
            "error": "usage: python -m integrations.remote_worker poll-once [--jobs FILE]",
        }) + "\n")
        return 2
    live = "--live" in args
    raw = _read_payload(args, stdin)
    if raw is None:
        out.write(json.dumps({"state": "refused", "error": "jobs payload is not json"}) + "\n")
        return 1
    try:
        payload = json.loads(raw)
        result = poll_once(payload, live=live)
    except json.JSONDecodeError:
        out.write(json.dumps({"state": "refused", "error": "jobs payload is not json"}) + "\n")
        return 1
    except WorkRefused as exc:
        result = {"state": "refused", "error": exc.message}
    out.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


def _read_payload(args: list[str], stdin: TextIO | None) -> str | None:
    if "--jobs" in args:
        index = args.index("--jobs")
        if index + 1 >= len(args):
            return None
        try:
            with open(args[index + 1], encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return None
    source = stdin if stdin is not None else sys.stdin
    return source.read()


def _first_job(device_id: str, jobs: list[Any], moment: float) -> dict[str, Any] | None:
    for job in jobs:
        if not isinstance(job, dict) or job.get("device_id") != device_id:
            continue
        if job.get("state") not in {"approved", "claimed"}:
            continue
        approval = job.get("approval") if isinstance(job.get("approval"), dict) else {}
        expires = approval.get("expires_at")
        if isinstance(expires, (int, float)) and moment >= float(expires):
            continue
        return job
    return None


def _pop_password(job: dict[str, Any]) -> str | None:
    found: str | None = None
    handler = job.get("handler_input")
    if isinstance(handler, dict) and isinstance(handler.get("password"), str):
        found = handler.pop("password")
    params = job.get("params")
    if isinstance(params, dict) and isinstance(params.get("password"), str):
        found = params.pop("password")
    if isinstance(job.get("password"), str):
        found = job.pop("password")
    return found


def _surveillance(value: object) -> bool:
    banned = {"screenshot", "screen", "keystrokes", "keylog", "processes", "process_list", "clipboard"}
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.casefold() in banned:
                return True
            if key != "jobs" and _surveillance(item):
                return True
            if key == "jobs" and _surveillance(item):
                return True
        return False
    if isinstance(value, list):
        return any(_surveillance(item) for item in value)
    return False


if __name__ == "__main__":
    raise SystemExit(main())
