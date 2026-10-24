"""Run allowlisted IT work for this enrolled device.

``poll-once`` reads one jobs payload from a file or stdin and does not contact
the network:

    python -m integrations.remote_worker poll-once [--jobs FILE]

``serve`` keeps a console session until Ctrl+C. It reads the existing device
secret, posts liveness, polls approved jobs for that device only, claims one,
runs it, and posts the result:

    python -m integrations.remote_worker serve --console http://127.0.0.1:8080 --token-file <path>

The process does not pass live=True unless the operator adds ``--live``.
Even then, the default runner stays disabled until REMOTE_IT_WORK_LIVE=1.
Download, install, delete, and a heartbeat work order still finish only
through an injected runner. Service restart and printer-queue clear call
the existing safe-fix functions through that runner. Tests inject a
transport and a runner and must not call the default. This module does not
open a socket itself.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, TextIO

from integrations.remote_work import (
    HEARTBEAT,
    INJECTED_ONLY,
    LIVE_ENV,
    WorkRefused,
    _scrub,
    execute,
    heartbeat_record,
)

_POLL_USAGE = "usage: python -m integrations.remote_worker poll-once [--jobs FILE]"
_SERVE_USAGE = (
    "usage: python -m integrations.remote_worker serve "
    "--console http://127.0.0.1:8080 --token-file <path>"
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


def exchange(
    transport: Any,
    *,
    device_id: str,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    live: bool = False,
    handler_input: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Poll, claim, and complete one job. The transport is injected.

    No socket is opened here. A missing or mismatched approval returns
    ``state`` ``refused`` and does not mark the order succeeded.
    """
    if not isinstance(device_id, str):
        raise WorkRefused("device id is not valid")
    poll = getattr(transport, "poll", None)
    claim = getattr(transport, "claim", None)
    complete = getattr(transport, "complete", None)
    if not callable(poll) or not callable(claim) or not callable(complete):
        raise WorkRefused("transport is not acceptable")
    jobs = poll(device_id)
    if not isinstance(jobs, list):
        raise WorkRefused("jobs must be a list")
    if _surveillance({"jobs": jobs}) or _surveillance(handler_input):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    moment = time.time() if now is None else now
    chosen = _first_job(device_id, jobs, moment)
    if chosen is None:
        return {
            "device_id": device_id,
            "action": None,
            "target": None,
            "state": "idle",
            "result": None,
            "error": None,
        }
    order_id = chosen.get("id")
    if not isinstance(order_id, str) or not order_id:
        raise WorkRefused("work order was not found")
    try:
        claimed = claim(device_id, order_id)
    except WorkRefused as exc:
        return _exchange_refused(device_id, chosen, exc.message)
    if not isinstance(claimed, dict):
        raise WorkRefused("work order is not valid")
    password = _pop_password(claimed)
    handler = dict(handler_input) if isinstance(handler_input, dict) else {}
    nested = claimed.get("handler_input") if isinstance(claimed.get("handler_input"), dict) else {}
    for key, value in nested.items():
        handler.setdefault(key, value)
    if password is not None:
        handler["password"] = password
    try:
        result = execute(claimed, live=live, runner=runner, handler_input=handler, now=moment)
    except WorkRefused as exc:
        message = exc.message
        if isinstance(password, str) and password and password in message:
            message = "result was refused"
        return _exchange_refused(device_id, chosen, message)
    redact = (password,) if isinstance(password, str) else ()
    safe = _scrub(result, redact)
    executed = bool(isinstance(safe, dict) and safe.get("executed"))
    if not executed:
        return {
            "device_id": device_id,
            "order_id": order_id,
            "action": claimed.get("action"),
            "target": claimed.get("target"),
            "state": "planned",
            "result": safe,
            "error": None,
        }
    stored = _liveness_only(safe) if claimed.get("action") == HEARTBEAT else safe
    completed = complete(
        device_id,
        order_id,
        outcome="succeeded",
        error=None,
        result=stored if isinstance(stored, dict) else None,
        redact=redact,
    )
    if not isinstance(completed, dict):
        raise WorkRefused("work order is not valid")
    return {
        "device_id": device_id,
        "order_id": order_id,
        "action": claimed.get("action"),
        "target": claimed.get("target"),
        "state": completed.get("state"),
        "result": completed.get("result"),
        "error": completed.get("error"),
    }


def _liveness_only(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "device_id": result.get("device_id"),
        "utc": result.get("utc"),
        "worker_version": result.get("worker_version"),
    }


def _exchange_refused(device_id: str, chosen: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "order_id": chosen.get("id"),
        "action": chosen.get("action"),
        "target": chosen.get("target"),
        "state": "refused",
        "result": None,
        "error": message,
    }


class ConsoleTransport:
    """Dial the loopback console with the enrolled device secret.

    The post function is injected in tests. The default is the endpoint
    worker's existing device call. The secret is sent only as the bearer.
    """

    def __init__(self, origin: str, secret: str, post: Callable[..., dict[str, Any]] | None = None) -> None:
        if not isinstance(origin, str) or not origin or not isinstance(secret, str) or len(secret) < 32:
            raise WorkRefused("transport is not acceptable")
        self.origin = origin
        self._secret = secret
        self._headers = {"Authorization": "Bearer " + secret}
        if post is None:
            from integrations.endpoint_worker import _post as default_post

            post = default_post
        self._post = post

    def heartbeat(self, utc: str, worker_version: str) -> dict[str, Any]:
        body = self._call("/api/remote-work/heartbeat", {"utc": utc, "worker_version": worker_version})
        return _liveness_body(body)

    def poll(self, device_id: str) -> list[dict[str, Any]]:
        body = self._call("/api/remote-work/poll", {})
        jobs = body.get("jobs")
        if not isinstance(jobs, list):
            raise WorkRefused("jobs must be a list")
        own: list[dict[str, Any]] = []
        for job in jobs:
            if isinstance(job, dict) and job.get("device_id") == device_id:
                own.append(job)
        return own

    def claim(self, device_id: str, order_id: str) -> dict[str, Any]:
        body = self._call("/api/remote-work/claim", {"order_id": order_id})
        if body.get("device_id") != device_id:
            raise WorkRefused("job belongs to another device")
        return body

    def complete(
        self,
        device_id: str,
        order_id: str,
        *,
        outcome: str,
        error: str | None = None,
        result: dict[str, Any] | None = None,
        redact: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        safe = _scrub(result, redact) if isinstance(result, dict) else None
        clean_error = error
        if isinstance(clean_error, str):
            for secret in redact:
                if isinstance(secret, str) and secret and secret in clean_error:
                    clean_error = "result was refused"
                    break
        body = self._call("/api/remote-work/complete", {
            "order_id": order_id,
            "outcome": outcome,
            "error": clean_error,
            "result": safe if isinstance(safe, dict) else None,
        })
        if body.get("device_id") not in {None, device_id}:
            raise WorkRefused("job belongs to another device")
        return body

    def _call(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            body = self._post(self.origin, path, payload, self._headers)
        except Exception as exc:
            message = getattr(exc, "message", None)
            if not isinstance(message, str) or not message:
                message = "console could not be reached"
            if self._secret in message:
                message = "console refused the request"
            raise WorkRefused(message) from None
        if not isinstance(body, dict):
            raise WorkRefused("console returned an unreadable response")
        rendered = json.dumps(body, default=str)
        if self._secret in rendered:
            raise WorkRefused("console returned an unreadable response")
        return body


def session_once(
    transport: Any,
    *,
    live: bool = False,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    handler_input: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Post liveness, then claim and finish at most one job for this device.

    A job that the live switch will not run stays approved. Heartbeat liveness
    does not create or approve a work order.
    """
    moment = time.time() if now is None else now
    record = _post_liveness(transport, moment)
    device_id = record["device_id"]
    if _surveillance(handler_input):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    poll = getattr(transport, "poll", None)
    claim = getattr(transport, "claim", None)
    complete = getattr(transport, "complete", None)
    if not callable(poll) or not callable(claim) or not callable(complete):
        raise WorkRefused("transport is not acceptable")
    jobs = poll(device_id)
    if not isinstance(jobs, list):
        raise WorkRefused("jobs must be a list")
    if _surveillance({"jobs": jobs}):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    chosen, waiting = _select_job(
        device_id,
        jobs,
        moment,
        live=live,
        runner=runner,
        handler_input=handler_input,
    )
    if chosen is None:
        if waiting is None:
            return {
                "device_id": device_id,
                "action": None,
                "target": None,
                "state": "idle",
                "result": None,
                "error": None,
            }
        job, reason = waiting
        return {
            "device_id": device_id,
            "order_id": job.get("id"),
            "action": job.get("action"),
            "target": job.get("target"),
            "state": "waiting",
            "result": None,
            "error": reason,
        }
    order_id = chosen.get("id")
    if not isinstance(order_id, str) or not order_id:
        raise WorkRefused("work order was not found")
    try:
        claimed = claim(device_id, order_id)
    except WorkRefused as exc:
        return _exchange_refused(device_id, chosen, exc.message)
    if not isinstance(claimed, dict) or claimed.get("device_id") != device_id:
        raise WorkRefused("job belongs to another device")
    return _finish_claimed(
        transport,
        device_id,
        chosen,
        claimed,
        live=live,
        runner=runner,
        handler_input=handler_input,
        now=moment,
    )


def serve(
    transport: Any,
    *,
    live: bool = False,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    handler_input: dict[str, Any] | None = None,
    now: float | Callable[[], float] | None = None,
    interval: float = 5.0,
    cycles: int | None = None,
    sleep: Callable[[float], None] | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Poll until ``cycles`` is reached or the caller stops the loop.

    The console command leaves ``cycles`` unset and sleeps between passes
    until Ctrl+C. Tests pass ``cycles`` and a fake sleep.
    """
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval < 0:
        raise WorkRefused("transport is not acceptable")
    if cycles is not None and (isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 1):
        raise WorkRefused("transport is not acceptable")
    pause = time.sleep if sleep is None else sleep
    out = stdout or sys.stdout
    count = 0
    try:
        while cycles is None or count < cycles:
            moment = _moment(now)
            try:
                result = session_once(
                    transport,
                    live=live,
                    runner=runner,
                    handler_input=handler_input,
                    now=moment,
                )
            except WorkRefused as exc:
                result = {"state": "refused", "error": _hide_password(exc.message, handler_input)}
            out.write(json.dumps(result, sort_keys=True) + "\n")
            out.flush()
            count += 1
            if cycles is not None and count >= cycles:
                break
            pause(float(interval))
    except KeyboardInterrupt:
        return 0
    return 0


def _finish_claimed(
    transport: Any,
    device_id: str,
    chosen: dict[str, Any],
    claimed: dict[str, Any],
    *,
    live: bool,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None,
    handler_input: dict[str, Any] | None,
    now: float,
) -> dict[str, Any]:
    order_id = claimed.get("id") if isinstance(claimed.get("id"), str) else chosen.get("id")
    password = _pop_password(claimed)
    handler = dict(handler_input) if isinstance(handler_input, dict) else {}
    nested = claimed.get("handler_input") if isinstance(claimed.get("handler_input"), dict) else {}
    for key, value in nested.items():
        handler.setdefault(key, value)
    if claimed.get("action") == HEARTBEAT:
        handler.setdefault("utc", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)))
        handler.setdefault("worker_version", WORKER_VERSION)
    if password is not None:
        handler["password"] = password
    redact = (password,) if isinstance(password, str) else ()
    try:
        result = execute(claimed, live=live, runner=runner, handler_input=handler, now=now)
    except WorkRefused as exc:
        message = _hide_password(exc.message, handler)
        _complete_quietly(transport, device_id, order_id, outcome="failed", error=message, result=None, redact=redact)
        return _exchange_refused(device_id, chosen, message)
    safe = _scrub(result, redact)
    executed = bool(isinstance(safe, dict) and safe.get("executed"))
    if not executed:
        message = "live execution is disabled"
        _complete_quietly(transport, device_id, order_id, outcome="failed", error=message, result=None, redact=redact)
        return _exchange_refused(device_id, chosen, message)
    stored = _liveness_only(safe) if claimed.get("action") == HEARTBEAT else safe
    completed = transport.complete(
        device_id,
        order_id,
        outcome="succeeded",
        error=None,
        result=stored if isinstance(stored, dict) else None,
        redact=redact,
    )
    if not isinstance(completed, dict):
        raise WorkRefused("work order is not valid")
    return {
        "device_id": device_id,
        "order_id": order_id,
        "action": claimed.get("action"),
        "target": claimed.get("target"),
        "state": completed.get("state"),
        "result": completed.get("result"),
        "error": completed.get("error"),
    }


def _complete_quietly(
    transport: Any,
    device_id: str,
    order_id: object,
    *,
    outcome: str,
    error: str,
    result: dict[str, Any] | None,
    redact: tuple[str, ...],
) -> None:
    if not isinstance(order_id, str) or not order_id:
        return
    try:
        transport.complete(
            device_id,
            order_id,
            outcome=outcome,
            error=error,
            result=result,
            redact=redact,
        )
    except WorkRefused:
        return


def _post_liveness(transport: Any, moment: float) -> dict[str, str]:
    beat = getattr(transport, "heartbeat", None)
    if not callable(beat):
        raise WorkRefused("transport is not acceptable")
    utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(moment))
    record = beat(utc, WORKER_VERSION)
    return _liveness_body(record)


def _liveness_body(body: object) -> dict[str, str]:
    if not isinstance(body, dict):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    if set(body) - {"device_id", "utc", "worker_version"} or _surveillance(body):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    return heartbeat_record(
        body.get("device_id") if isinstance(body.get("device_id"), str) else "",
        body.get("utc") if isinstance(body.get("utc"), str) else "",
        body.get("worker_version") if isinstance(body.get("worker_version"), str) else "",
    )


def _select_job(
    device_id: str,
    jobs: list[Any],
    moment: float,
    *,
    live: bool,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None,
    handler_input: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], str] | None]:
    waiting: tuple[dict[str, Any], str] | None = None
    for job in jobs:
        if not isinstance(job, dict) or job.get("device_id") != device_id:
            continue
        if job.get("state") not in {"approved", "claimed"}:
            continue
        approval = job.get("approval") if isinstance(job.get("approval"), dict) else {}
        expires = approval.get("expires_at")
        if isinstance(expires, (int, float)) and moment >= float(expires):
            continue
        reason = _wait_reason(job, live=live, runner=runner, handler_input=handler_input)
        if reason is None:
            return job, None
        if waiting is None:
            waiting = (job, reason)
    return None, waiting


def _wait_reason(
    job: dict[str, Any],
    *,
    live: bool,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None,
    handler_input: dict[str, Any] | None,
) -> str | None:
    """Return why this approved job must stay unclaimed."""
    if not live or os.environ.get(LIVE_ENV) != "1":
        return "live execution is disabled"
    action = job.get("action")
    if action in INJECTED_ONLY and runner is None:
        return "this action is plan only"
    if action == "setup.onboard.local_user":
        password = handler_input.get("password") if isinstance(handler_input, dict) else None
        if not isinstance(password, str) or password == "":
            return "local user password is not acceptable"
    return None


def _moment(now: float | Callable[[], float] | None) -> float:
    if now is None:
        return time.time()
    if callable(now):
        return float(now())
    return float(now)


def _hide_password(message: str, handler_input: dict[str, Any] | None) -> str:
    password = handler_input.get("password") if isinstance(handler_input, dict) else None
    if isinstance(password, str) and password and password in message:
        return "result was refused"
    return message


def main(
    argv: list[str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = stdout or sys.stdout
    if not args or args[0] not in {"poll-once", "serve"}:
        out.write(json.dumps({
            "state": "refused",
            "error": _POLL_USAGE,
        }) + "\n")
        return 2
    if args[0] == "serve":
        return _serve_command(args, out)
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


def _serve_command(args: list[str], out: TextIO) -> int:
    console = _flag(args, "--console")
    token_file = _flag(args, "--token-file")
    if not console or not token_file:
        out.write(json.dumps({"state": "refused", "error": _SERVE_USAGE}) + "\n")
        return 2
    interval = 5.0
    raw_interval = _flag(args, "--interval")
    if raw_interval is not None:
        try:
            interval = float(raw_interval)
        except ValueError:
            interval = -1.0
        if interval < 1:
            out.write(json.dumps({"state": "refused", "error": _SERVE_USAGE}) + "\n")
            return 2
    try:
        from integrations.endpoint_worker import console_origin, read_secret_file
        from integrations.errors import InvalidRequest

        origin = console_origin(console)
        secret = read_secret_file(Path(token_file))
    except InvalidRequest as exc:
        message = exc.message if isinstance(exc.message, str) else "device secret file is not usable"
        out.write(json.dumps({"state": "refused", "error": message}) + "\n")
        return 1
    except Exception:
        out.write(json.dumps({"state": "refused", "error": "device secret file is not usable"}) + "\n")
        return 1
    try:
        transport = ConsoleTransport(origin, secret)
        return serve(transport, live="--live" in args, interval=interval, stdout=out)
    except WorkRefused as exc:
        message = exc.message if secret not in exc.message else "console refused the request"
        out.write(json.dumps({"state": "refused", "error": message}) + "\n")
        return 1


def _flag(args: list[str], name: str) -> str | None:
    prefix = name + "="
    for index, item in enumerate(args):
        if item.startswith(prefix):
            value = item[len(prefix):]
            return value or None
        if item == name and index + 1 < len(args) and not str(args[index + 1]).startswith("--"):
            return str(args[index + 1])
    return None


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
