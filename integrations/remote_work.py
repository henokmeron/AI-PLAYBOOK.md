"""Device-initiated IT work for a laptop the operator already enrolled.

The laptop dials out. This module does not scan the network, open a shell on
an unenrolled host, or perform DNS or HTTP. Creating an order does not approve
it, and a diagnostic result does not approve it.

States: draft -> pending_approval -> approved -> claimed -> succeeded | failed.
``refused`` is a separate terminal state. An approval is single-use, lasts 15
minutes, and is bound to the device id, action id, and target.

HTTP is intentionally unwired. ``require_operator`` can guard create and
approve, and ``_device_bearer`` only checks that a Bearer header is present.
Nothing already public maps that secret to a device id without storing a
diagnostic (``DeviceRegistry.submit``) or using the other repair enrolment.
``integrations/endpoint.py`` is not modified here. The console should call
``create_work_order``, ``approve_work_order``, ``poll_jobs``, and
``complete_job``. Enrolled liveness uses ``post_heartbeat`` and does not need
a second approval. Do not invent a token for these calls.

Live OS changes run only when the order is approved, the caller passes
``live=True``, and a runner is injected or ``REMOTE_IT_WORK_LIVE=1``. Download
and install stay plans. Passwords are a handler input and are not stored.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any, Callable
from urllib.parse import urlsplit

APPROVAL_TTL_SECONDS = 15 * 60
LIVE_ENV = "REMOTE_IT_WORK_LIVE"
HEARTBEAT = "monitor.heartbeat"
PLAN_ONLY = frozenset({"change.download", "change.install"})

ACTIONS = frozenset({
    HEARTBEAT,
    "repair.service.restart",
    "repair.printer.clear_queue",
    "setup.onboard.local_user",
    "setup.offboard.local_user",
    "change.download",
    "change.install",
    "change.delete",
})

ACTION_PARAMS = {
    HEARTBEAT: frozenset(),
    "repair.service.restart": frozenset({"start_type", "status"}),
    "repair.printer.clear_queue": frozenset({"path"}),
    "setup.onboard.local_user": frozenset(),
    "setup.offboard.local_user": frozenset({"mode", "admin_count"}),
    "change.download": frozenset({"allowlist", "staging_directory", "destination", "sha256"}),
    "change.install": frozenset({"source", "sha256", "staging_directory"}),
    "change.delete": frozenset(),
}

INSTALL_SOURCES = frozenset({"windows-update", "pnputil", "staged-file"})
CONSOLE_FUNCTIONS = (
    "create_work_order",
    "approve_work_order",
    "poll_jobs",
    "complete_job",
)

_DEVICE_ID = re.compile(r"[0-9a-f]{32}\Z")
_OPERATOR = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_ACTION_NAME = re.compile(r"[a-z][a-z0-9._]{0,63}\Z")
_SERVICE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z")
_QUEUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}\Z")
_USER = re.compile(r"[A-Za-z][A-Za-z0-9._-]{0,20}\Z")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}\Z")
_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\Z")

_SECRET_PARTS = ("password", "secret", "token", "serial")
_SURVEILLANCE = frozenset({
    "screenshot", "screen", "keystrokes", "keylog", "processes", "process_list", "clipboard",
})
_REBOOT_NAMES = frozenset({"reboot", "shutdown", "restart", "restart-all", "all"})
_QUEUE_DENY = frozenset({"all", "*", "every", "printers"})
_PROTECTED_PREFIXES = (
    ("windows", "system32"),
    ("windows", "syswow64"),
    ("program files",),
    ("program files (x86)",),
)
_SPOOL_TAIL = ("windows", "system32", "spool", "printers")
_CLEAR_QUEUE_ARGV = [
    "powershell.exe",
    "-NoProfile",
    "-NonInteractive",
    "-Command",
    "Get-PrintJob -PrinterName $env:REMOTE_IT_QUEUE | Remove-PrintJob",
]
_CREATE_USER_ARGV = [
    "powershell.exe",
    "-NoProfile",
    "-NonInteractive",
    "-Command",
    "$in = [Console]::In.ReadToEnd() | ConvertFrom-Json; "
    "$sec = ConvertTo-SecureString $in.password -AsPlainText -Force; "
    "New-LocalUser -Name $in.username -Password $sec | Out-Null",
]

_DEFAULT_RUNNER_CALLS = 0


class WorkRefused(Exception):
    """The order, approval, or handler refused the work."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class WorkStore:
    """In-memory orders and an append-only audit. Tests inject this store."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.time
        self._lock = threading.Lock()
        self.orders: dict[str, dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []
        self.heartbeats: list[dict[str, Any]] = []
        self.enrolled: set[str] = set()

    def now(self) -> float:
        return float(self._clock())


def default_runner_invocations() -> int:
    return _DEFAULT_RUNNER_CALLS


def register_enrolled_device(store: WorkStore, device_id: str) -> None:
    """Record that enrolment already happened. This does not approve work."""
    if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id):
        raise WorkRefused("device id is not valid")
    with store._lock:
        store.enrolled.add(device_id)


def create_work_order(
    store: WorkStore,
    *,
    device_id: str,
    action: str,
    target: str,
    operator_id: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a draft and leave it pending. Never approves the order."""
    with store._lock:
        _require_device(store, device_id)
        if not isinstance(operator_id, str) or not _OPERATOR.fullmatch(operator_id):
            raise WorkRefused("operator id is not acceptable")
        incoming = params if params is not None else {}
        if not isinstance(incoming, dict):
            raise WorkRefused("parameters are not acceptable")
        stored_target = _display_target(target)
        if _contains_secret_key(incoming) or _target_has_secret(target):
            order = _blank_order(
                device_id=device_id,
                action=_safe_action(action),
                target="[redacted]" if _target_has_secret(target) else stored_target,
                operator_id=operator_id,
                params={},
                state="refused",
                error="a secret was refused and was not stored",
                now=store.now(),
            )
            _commit(store, order)
            return _public(order)
        safe_action = _safe_action(action)
        raw_target = target if isinstance(target, str) else ""
        problem = None if safe_action in ACTIONS else "action is not allowlisted"
        stored_params: dict[str, Any] = {}
        if problem is None:
            problem = _policy_error(safe_action, raw_target, incoming)
        if problem is None:
            raw_target, stored_params = _canonicalize(safe_action, raw_target, incoming)
            problem = _policy_error(safe_action, raw_target, stored_params)
        state = "refused" if problem else "draft"
        order = _blank_order(
            device_id=device_id,
            action=safe_action,
            target=raw_target if problem is None else stored_target,
            operator_id=operator_id,
            params=stored_params if problem is None else {},
            state=state,
            error=problem,
            now=store.now(),
        )
        _commit(store, order)
        if problem is None:
            order["state"] = "pending_approval"
            _audit(store, order, operator_id=operator_id, error=None)
        return _public(order)


def approve_work_order(store: WorkStore, order_id: str, operator_id: str) -> dict[str, Any]:
    """Bind one unused approval to this device, action, and target."""
    with store._lock:
        order = _must_order(store, order_id)
        if order["state"] == "refused":
            raise WorkRefused("a refused order is terminal")
        if order["state"] != "pending_approval":
            raise WorkRefused("only a pending order can be approved")
        if not isinstance(operator_id, str) or not _OPERATOR.fullmatch(operator_id):
            raise WorkRefused("operator id is not acceptable")
        now = store.now()
        order["approval"] = {
            "device_id": order["device_id"],
            "action": order["action"],
            "target": order["target"],
            "params_digest": order["params_digest"],
            "operator_id": operator_id,
            "approved_at": now,
            "expires_at": now + APPROVAL_TTL_SECONDS,
            "used": False,
        }
        order["state"] = "approved"
        order["error"] = None
        _audit(store, order, operator_id=operator_id, error=None)
        return _public(order)


def poll_jobs(store: WorkStore, device_id: str) -> list[dict[str, Any]]:
    """Approved, unexpired jobs for this device id and no other device."""
    with store._lock:
        _require_device(store, device_id)
        now = store.now()
        found = []
        for order in store.orders.values():
            if order["device_id"] != device_id or order["state"] != "approved":
                continue
            if _binding_error(order, now) is not None:
                continue
            found.append(_public(order))
        found.sort(key=lambda item: item["id"])
        return found


def claim_job(store: WorkStore, device_id: str, order_id: str) -> dict[str, Any]:
    """Move one approved job to claimed and consume its approval."""
    with store._lock:
        _require_device(store, device_id)
        order = _must_order(store, order_id)
        if order["device_id"] != device_id:
            raise WorkRefused("job belongs to another device")
        if order["state"] in {"succeeded", "failed"}:
            raise WorkRefused("a second result is refused")
        if order["state"] == "refused":
            raise WorkRefused("a refused order is terminal")
        if order["state"] == "claimed" or (order.get("approval") or {}).get("used"):
            raise WorkRefused("approval is already used")
        if order["state"] != "approved":
            raise WorkRefused("only an approved order can be claimed")
        problem = _binding_error(order, store.now())
        if problem is not None:
            if problem == "approval expired":
                order["state"] = "refused"
                order["error"] = problem
                _audit(store, order, operator_id="", error=problem)
            raise WorkRefused(problem)
        order["approval"]["used"] = True
        order["state"] = "claimed"
        order["error"] = None
        _audit(store, order, operator_id=order["approval"]["operator_id"], error=None)
        return _public(order)


def complete_job(
    store: WorkStore,
    device_id: str,
    order_id: str,
    *,
    outcome: str,
    error: str | None = None,
    result: dict[str, Any] | None = None,
    redact: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Record one result. A second complete call is refused."""
    with store._lock:
        _require_device(store, device_id)
        order = _must_order(store, order_id)
        if order["device_id"] != device_id:
            raise WorkRefused("job belongs to another device")
        if order["state"] in {"succeeded", "failed"}:
            raise WorkRefused("a second result is refused")
        if order["state"] == "refused":
            raise WorkRefused("a refused order is terminal")
        if order["state"] != "claimed":
            raise WorkRefused("job is not claimed")
        if outcome not in {"succeeded", "failed"}:
            raise WorkRefused("outcome must be succeeded or failed")
        clean_error = _scrub(error, redact)
        if clean_error is not None and not isinstance(clean_error, str):
            clean_error = "result was refused"
        if isinstance(clean_error, str) and len(clean_error) > 200:
            clean_error = "result was refused"
        order["state"] = outcome
        order["error"] = clean_error
        order["result"] = _scrub(result, redact) if isinstance(result, dict) else None
        _audit(store, order, operator_id=(order.get("approval") or {}).get("operator_id", ""), error=clean_error)
        return _public(order)


def post_heartbeat(store: WorkStore, payload: dict[str, Any]) -> dict[str, Any]:
    """Liveness from an enrolled device. Enrolment is the only approval."""
    if not isinstance(payload, dict):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    extra = set(payload) - {"device_id", "utc", "worker_version"}
    if extra or _contains_surveillance(payload):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    device_id = payload.get("device_id")
    utc = payload.get("utc")
    version = payload.get("worker_version")
    if not isinstance(device_id, str) or not isinstance(utc, str) or not isinstance(version, str):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    record = _heartbeat_fields(device_id, utc, version)
    with store._lock:
        _require_device(store, device_id)
        store.heartbeats.append(dict(record))
        _audit(
            store,
            {
                "device_id": device_id,
                "action": HEARTBEAT,
                "target": device_id,
                "state": "succeeded",
                "error": None,
            },
            operator_id="",
            error=None,
        )
        return record


def execute(
    order: dict[str, Any],
    *,
    live: bool = False,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    handler_input: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Return a plan unless the order is approved and ``live`` is true.

    Download and install never call a runner. The default live runner is used
    only when ``runner`` is omitted, ``live`` is true, and ``REMOTE_IT_WORK_LIVE``
    is ``1``.
    """
    if not isinstance(order, dict):
        raise WorkRefused("work order is not valid")
    action = order.get("action")
    target = order.get("target") if isinstance(order.get("target"), str) else ""
    params = order.get("params") if isinstance(order.get("params"), dict) else {}
    if _contains_secret_key(params) or _contains_surveillance(order):
        raise WorkRefused("a secret was refused and was not stored")
    problem = _policy_error(action if isinstance(action, str) else "", target, params)
    if problem is not None:
        raise WorkRefused(problem)
    approval = order.get("approval")
    if isinstance(approval, dict) and approval.get("target") != target:
        if action == "change.delete":
            raise WorkRefused("path does not match the approved target")
        raise WorkRefused("approval is bound to a different target")
    supplied = handler_input if isinstance(handler_input, dict) else {}
    if _contains_surveillance(supplied):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    if action == "change.install" and live:
        offered = supplied.get("sha256")
        approved_pin = str(params.get("sha256", "")).lower()
        if not isinstance(offered, str) or offered.lower() != approved_pin:
            raise WorkRefused("staged file sha256 does not match the approved pin")
    plan = _plan_for(order, supplied)
    if action in PLAN_ONLY or action == HEARTBEAT:
        plan["executed"] = False
        return plan
    moment = time.time() if now is None else now
    if not live or not _execution_authorized(order, moment):
        plan["executed"] = False
        return plan
    active = runner
    if active is None:
        if os.environ.get(LIVE_ENV) != "1":
            raise WorkRefused("live execution is disabled")
        active = default_live_runner
    request = _runner_request(order, supplied, plan)
    active(request)
    plan["executed"] = True
    return plan


def execute_work_order(
    store: WorkStore,
    order_id: str,
    *,
    live: bool = False,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    handler_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with store._lock:
        order = _must_order(store, order_id)
        snapshot = json.loads(json.dumps(order))
        moment = store.now()
    return execute(snapshot, live=live, runner=runner, handler_input=handler_input, now=moment)


def snapshot(store: WorkStore) -> dict[str, Any]:
    """Full stored state, for tests that assert secrets were not written."""
    with store._lock:
        return json.loads(json.dumps({
            "orders": store.orders,
            "audit": store.audit,
            "heartbeats": store.heartbeats,
        }, default=str))


def service_facts_from_text(query_text: str, config_text: str) -> dict[str, str]:
    """Read start type and state from ``sc.exe qc`` and ``sc.exe query`` text."""
    if re.search(r"\bAUTO_START\b", config_text):
        start_type = "automatic"
    elif re.search(r"\bDEMAND_START\b", config_text):
        start_type = "manual"
    elif re.search(r"\bDISABLED\b", config_text):
        start_type = "disabled"
    else:
        start_type = "other"
    if re.search(r"\bRUNNING\b", query_text):
        status = "running"
    elif re.search(r"\bSTOPPED\b", query_text):
        status = "stopped"
    else:
        status = "other"
    return {"start_type": start_type, "status": status}


def default_live_runner(request: dict[str, Any]) -> dict[str, Any]:
    """Perform one allowlisted operation. Tests must not call this."""
    global _DEFAULT_RUNNER_CALLS
    _DEFAULT_RUNNER_CALLS += 1
    if os.environ.get(LIVE_ENV) != "1":
        raise WorkRefused("live execution is disabled")
    op = request.get("op")
    if op in {"download", "install", "heartbeat"}:
        raise WorkRefused("this action is plan only")
    if op == "start_service":
        return _live_start_service(request)
    if op == "clear_queue":
        return _live_clear_queue(request)
    if op == "delete_spool_file":
        return _live_delete_spool(request)
    if op == "create_local_user":
        return _live_create_user(request)
    if op == "disable_local_user":
        return _live_offboard(request, delete=False)
    if op == "remove_local_user":
        return _live_offboard(request, delete=True)
    if op == "delete_file":
        return _live_delete_file(request)
    raise WorkRefused("action is not allowlisted")


def _live_start_service(request: dict[str, Any]) -> dict[str, Any]:
    name = request.get("target")
    problem = _service_error(
        name if isinstance(name, str) else "",
        {"start_type": "automatic", "status": "stopped"},
    )
    if problem is not None or not isinstance(name, str):
        raise WorkRefused(problem or "service name is not acceptable")
    query = _capture(["sc.exe", "query", name])
    config = _capture(["sc.exe", "qc", name])
    facts = service_facts_from_text(query, config)
    if facts["start_type"] != "automatic" or facts["status"] != "stopped":
        raise WorkRefused("service must be a stopped automatic service")
    argv = request.get("argv")
    if argv != ["sc.exe", "start", name]:
        raise WorkRefused("service command does not match the approved target")
    _capture(argv)
    return {"ok": True}


def _live_clear_queue(request: dict[str, Any]) -> dict[str, Any]:
    queue = request.get("queue")
    if _printer_error(queue if isinstance(queue, str) else "", {}) is not None:
        raise WorkRefused("queue name is not acceptable")
    if request.get("argv") != _CLEAR_QUEUE_ARGV:
        raise WorkRefused("queue command does not match the approved target")
    _capture(_CLEAR_QUEUE_ARGV, env={**os.environ, "REMOTE_IT_QUEUE": str(queue)})
    return {"ok": True}


def _live_delete_spool(request: dict[str, Any]) -> dict[str, Any]:
    queue = request.get("queue")
    path = request.get("path")
    if not isinstance(queue, str) or not isinstance(path, str):
        raise WorkRefused("queue path is outside that queue spool")
    if _spool_file_error(queue, path) is not None:
        raise WorkRefused("queue path is outside that queue spool")
    Path(path).unlink()
    return {"ok": True}


def _live_create_user(request: dict[str, Any]) -> dict[str, Any]:
    username = request.get("username")
    password = request.get("password")
    if _user_error(username if isinstance(username, str) else "") is not None:
        raise WorkRefused("local user name is not acceptable")
    if not isinstance(password, str) or password == "" or any(ch in password for ch in "\r\n\x00"):
        raise WorkRefused("local user password is not acceptable")
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    _capture(_CREATE_USER_ARGV, stdin=payload)
    return {"ok": True}


def _live_offboard(request: dict[str, Any], *, delete: bool) -> dict[str, Any]:
    username = request.get("username")
    count = request.get("admin_count")
    if _offboard_error(username if isinstance(username, str) else "", {"mode": "remove" if delete else "disable", "admin_count": count}) is not None:
        raise WorkRefused("refusing to change the only remaining admin")
    flag = "/delete" if delete else "/active:no"
    argv = ["net", "user", username, flag]
    if request.get("argv") != argv:
        raise WorkRefused("offboard command does not match the approved target")
    _capture([str(part) for part in argv])
    return {"ok": True}


def _live_delete_file(request: dict[str, Any]) -> dict[str, Any]:
    path = request.get("path")
    if not isinstance(path, str) or _delete_error(path) is not None:
        raise WorkRefused("path is under a protected directory")
    if request.get("argv") != ["delete-file", path]:
        raise WorkRefused("path does not match the approved target")
    Path(path).unlink()
    return {"ok": True}


def _capture(argv: list[str], *, stdin: bytes | None = None, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        argv,
        input=stdin,
        capture_output=True,
        check=False,
        shell=False,
        env=env,
    )
    if completed.returncode != 0:
        raise WorkRefused("live command failed")
    return completed.stdout.decode("utf-8", errors="replace")


def _require_device(store: WorkStore, device_id: str) -> None:
    if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id):
        raise WorkRefused("device id is not valid")
    if device_id not in store.enrolled:
        raise WorkRefused("device is not enrolled")


def _must_order(store: WorkStore, order_id: str) -> dict[str, Any]:
    order = store.orders.get(order_id)
    if order is None:
        raise WorkRefused("work order was not found")
    return order


def _blank_order(
    *,
    device_id: str,
    action: str,
    target: str,
    operator_id: str,
    params: dict[str, Any],
    state: str,
    error: str | None,
    now: float,
) -> dict[str, Any]:
    clean = _scrub(params)
    return {
        "id": uuid.uuid4().hex,
        "device_id": device_id,
        "action": action,
        "target": target,
        "params": clean,
        "params_digest": _digest(clean),
        "state": state,
        "operator_id": operator_id,
        "error": error,
        "approval": None,
        "result": None,
        "created_at": now,
    }


def _commit(store: WorkStore, order: dict[str, Any]) -> None:
    store.orders[order["id"]] = order
    _audit(store, order, operator_id=order["operator_id"], error=order["error"])


def _audit(store: WorkStore, order: dict[str, Any], *, operator_id: str, error: str | None) -> None:
    store.audit.append({
        "time": _iso(store.now()),
        "device_id": order["device_id"],
        "action": order["action"],
        "target": order["target"],
        "state": order["state"],
        "operator_id": operator_id,
        "error": error,
    })


def _public(order: dict[str, Any]) -> dict[str, Any]:
    approval = order.get("approval")
    visible = None
    if isinstance(approval, dict):
        visible = {
            "device_id": approval["device_id"],
            "action": approval["action"],
            "target": approval["target"],
            "params_digest": approval["params_digest"],
            "expires_at": approval["expires_at"],
            "used": approval["used"],
        }
    return {
        "id": order["id"],
        "device_id": order["device_id"],
        "action": order["action"],
        "target": order["target"],
        "params": _scrub(order.get("params") or {}),
        "params_digest": order["params_digest"],
        "state": order["state"],
        "operator_id": order["operator_id"],
        "error": order["error"],
        "approval": visible,
        "result": _scrub(order.get("result")),
    }


def _binding_error(order: dict[str, Any], now: float) -> str | None:
    approval = order.get("approval")
    if not isinstance(approval, dict):
        return "approval is required"
    if approval.get("used"):
        return "approval is already used"
    expires = approval.get("expires_at")
    if not isinstance(expires, (int, float)) or now >= float(expires):
        return "approval expired"
    if approval.get("device_id") != order.get("device_id"):
        return "approval is bound to a different device"
    if approval.get("action") != order.get("action"):
        return "approval is bound to a different action"
    if approval.get("target") != order.get("target"):
        return "approval is bound to a different target"
    if approval.get("params_digest") != _digest(order.get("params") or {}):
        return "approval is bound to different parameters"
    return None


def _execution_authorized(order: dict[str, Any], now: float) -> bool:
    state = order.get("state")
    approval = order.get("approval")
    if state not in {"approved", "claimed"} or not isinstance(approval, dict):
        return False
    if state == "approved" and approval.get("used"):
        return False
    if state == "claimed" and not approval.get("used"):
        return False
    clone = dict(order)
    unlocked = dict(approval)
    unlocked["used"] = False
    clone["approval"] = unlocked
    return _binding_error(clone, now) is None


def _plan_for(order: dict[str, Any], handler_input: dict[str, Any]) -> dict[str, Any]:
    action = order["action"]
    target = order["target"]
    params = order["params"]
    if action == HEARTBEAT:
        utc = handler_input.get("utc")
        version = handler_input.get("worker_version")
        if not isinstance(utc, str) or not isinstance(version, str):
            raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
        record = _heartbeat_fields(order["device_id"], utc, version)
        return {"op": "heartbeat", **record, "executed": False}
    if action == "repair.service.restart":
        return {"op": "start_service", "argv": ["sc.exe", "start", target], "target": target, "executed": False}
    if action == "repair.printer.clear_queue":
        path = params.get("path")
        if isinstance(path, str):
            return {
                "op": "delete_spool_file",
                "argv": ["delete-spool-file", path],
                "queue": target,
                "path": path,
                "executed": False,
            }
        return {
            "op": "clear_queue",
            "argv": list(_CLEAR_QUEUE_ARGV),
            "queue": target,
            "spool_dir": str(_queue_spool(target)),
            "executed": False,
        }
    if action == "setup.onboard.local_user":
        return {
            "op": "create_local_user",
            "argv": ["net", "user", target, "/add"],
            "username": target,
            "password": "<redacted>",
            "executed": False,
        }
    if action == "setup.offboard.local_user":
        delete = params.get("mode") == "remove"
        flag = "/delete" if delete else "/active:no"
        return {
            "op": "remove_local_user" if delete else "disable_local_user",
            "argv": ["net", "user", target, flag],
            "username": target,
            "admin_count": params.get("admin_count"),
            "executed": False,
        }
    if action == "change.download":
        return {
            "op": "download",
            "operation": "plan https download into staging with a sha256 pin",
            "url": target,
            "host": urlsplit(target).hostname,
            "destination": params.get("destination"),
            "sha256": str(params.get("sha256", "")).lower(),
            "network": False,
            "executed": False,
        }
    if action == "change.install":
        return {
            "op": "install",
            "argv": _install_argv(str(params.get("source")), target),
            "source": params.get("source"),
            "staged_path": target,
            "sha256": str(params.get("sha256", "")).lower(),
            "invoke": False,
            "executed": False,
        }
    if action == "change.delete":
        return {"op": "delete_file", "argv": ["delete-file", target], "path": target, "executed": False}
    raise WorkRefused("action is not allowlisted")


def _runner_request(order: dict[str, Any], handler_input: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    request = {
        "op": plan["op"],
        "argv": list(plan.get("argv") or []),
        "target": order["target"],
    }
    if plan["op"] in {"clear_queue", "delete_spool_file"}:
        request["queue"] = order["target"]
        if plan["op"] == "delete_spool_file":
            request["path"] = plan["path"]
    if plan["op"] == "create_local_user":
        password = handler_input.get("password")
        if not isinstance(password, str) or password == "":
            raise WorkRefused("local user password is not acceptable")
        request["username"] = order["target"]
        request["password"] = password
    if plan["op"] in {"disable_local_user", "remove_local_user"}:
        request["username"] = order["target"]
        request["admin_count"] = order["params"].get("admin_count")
    if plan["op"] == "delete_file":
        request["path"] = order["target"]
    return request


def _install_argv(source: str, path: str) -> list[str]:
    if source == "pnputil":
        return ["pnputil.exe", "/add-driver", path, "/install"]
    if source == "windows-update":
        return ["dism.exe", "/Online", "/Add-Package", "/PackagePath:" + path]
    return ["staged-file", "verify-sha256", path]


def _policy_error(action: str, target: str, params: dict[str, Any]) -> str | None:
    if action not in ACTIONS:
        return "action is not allowlisted"
    if params.get("restart_all") is True or params.get("all") is True:
        return "reboot and restart-all are refused"
    if action == "repair.service.restart" and (target in {"*", "all"} or target.casefold() in _REBOOT_NAMES):
        return "reboot and restart-all are refused"
    if not _params_allowed(action, params):
        return "parameter is not allowed"
    if action == HEARTBEAT:
        return None if target == "" or _DEVICE_ID.fullmatch(target) else "device id is not valid"
    if action == "repair.service.restart":
        return _service_error(target, params)
    if action == "repair.printer.clear_queue":
        return _printer_error(target, params)
    if action == "setup.onboard.local_user":
        return _user_error(target)
    if action == "setup.offboard.local_user":
        return _offboard_error(target, params)
    if action == "change.download":
        return _download_error(target, params)
    if action == "change.install":
        return _install_error(target, params)
    if action == "change.delete":
        return _delete_error(target)
    return "action is not allowlisted"


def _service_error(target: str, params: dict[str, Any]) -> str | None:
    if not isinstance(target, str) or target in {"*", "all"} or target.casefold() in _REBOOT_NAMES:
        return "reboot and restart-all are refused"
    if params.get("restart_all") is True or params.get("all") is True:
        return "reboot and restart-all are refused"
    if not _SERVICE.fullmatch(target):
        return "service name is not acceptable"
    if params.get("start_type") != "automatic":
        return "service must be automatic"
    if params.get("status") != "stopped":
        return "service must not be running"
    return None


def _printer_error(target: str, params: dict[str, Any]) -> str | None:
    if not isinstance(target, str) or target.casefold() in _QUEUE_DENY or not _QUEUE.fullmatch(target):
        return "queue name is not acceptable"
    path = params.get("path")
    if path is None:
        return None
    if not isinstance(path, str):
        return "queue path is outside that queue spool"
    return _spool_file_error(target, path)


def _spool_file_error(queue: str, path: str) -> str | None:
    candidate = _windows_path(path)
    if candidate is None:
        return "queue path is outside that queue spool"
    if candidate.suffix.casefold() not in {".spl", ".shd"}:
        return "queue path is outside that queue spool"
    expected = _queue_spool(queue)
    if [part.casefold() for part in candidate.parts[:-1]] != [part.casefold() for part in expected.parts]:
        return "queue path is outside that queue spool"
    return None


def _queue_spool(queue: str) -> PureWindowsPath:
    return PureWindowsPath(r"C:\Windows\System32\spool\PRINTERS") / queue


def _user_error(target: str) -> str | None:
    if not isinstance(target, str) or target.strip() == "" or not _USER.fullmatch(target):
        return "local user name is blank or not acceptable"
    return None


def _offboard_error(target: str, params: dict[str, Any]) -> str | None:
    if not isinstance(target, str) or target.strip() == "" or not _USER.fullmatch(target):
        return "local user name is blank or not acceptable"
    if params.get("mode") not in {"disable", "remove"}:
        return "offboard mode must be disable or remove"
    count = params.get("admin_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 2:
        return "refusing to change the only remaining admin"
    return None


def _download_error(target: str, params: dict[str, Any]) -> str | None:
    if not isinstance(target, str) or _target_has_secret(target):
        return "download URL must be https"
    parsed = urlsplit(target)
    if parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname:
        return "download URL must be https"
    host = parsed.hostname
    if not _HOST.fullmatch(host):
        return "download host is not on the allowlist"
    allow = params.get("allowlist")
    if not isinstance(allow, list) or not allow or not all(isinstance(item, str) and _HOST.fullmatch(item) for item in allow):
        return "download host is not on the allowlist"
    if "*" in "".join(allow) or host.casefold() not in {item.casefold() for item in allow}:
        return "download host is not on the allowlist"
    pin = params.get("sha256")
    if not isinstance(pin, str) or not _SHA256.fullmatch(pin):
        return "download requires a sha256 pin"
    staging = params.get("staging_directory")
    destination = params.get("destination")
    if not isinstance(staging, str) or not isinstance(destination, str):
        return "download destination is outside the staging directory"
    if not _inside_staging(staging, destination):
        return "download destination is outside the staging directory"
    return None


def _install_error(target: str, params: dict[str, Any]) -> str | None:
    if params.get("source") not in INSTALL_SOURCES:
        return "install source is not allowlisted"
    pin = params.get("sha256")
    if not isinstance(pin, str) or not _SHA256.fullmatch(pin):
        return "staged file sha256 does not match the approved pin"
    staging = params.get("staging_directory")
    if not isinstance(target, str) or not isinstance(staging, str) or not _inside_staging(staging, target):
        return "staged file is outside the staging directory"
    return None


def _delete_error(target: str) -> str | None:
    if not isinstance(target, str):
        return "path does not match the approved target"
    if "*" in target or "?" in target:
        return "path contains a glob"
    path = _windows_path(target)
    if path is None:
        return "path does not match the approved target"
    tail = _tail(path)
    if not tail:
        return "path is a drive root"
    for prefix in _PROTECTED_PREFIXES:
        if tuple(tail[:len(prefix)]) == prefix:
            return "path is under a protected directory"
    if tail == ["users"] or (len(tail) == 2 and tail[0] == "users"):
        return "path is a user profile directory"
    return None


def _inside_staging(staging: str, destination: str) -> bool:
    parent = _windows_path(staging)
    child = _windows_path(destination)
    if parent is None or child is None:
        return False
    parent_tail = _tail(parent)
    child_tail = _tail(child)
    if not parent_tail or _protected(parent_tail) or parent_tail == ["users"] or (len(parent_tail) == 2 and parent_tail[0] == "users"):
        return False
    if len(child_tail) <= len(parent_tail):
        return False
    return child_tail[:len(parent_tail)] == parent_tail


def _protected(tail: list[str]) -> bool:
    return any(tuple(tail[:len(prefix)]) == prefix for prefix in _PROTECTED_PREFIXES)


def _windows_path(value: str) -> PureWindowsPath | None:
    if not isinstance(value, str) or value == "" or len(value) > 512:
        return None
    if any(ord(ch) < 32 or ch in '*?"<>|' for ch in value):
        return None
    if value.startswith("\\\\") or value.startswith("//"):
        return None
    path = PureWindowsPath(value)
    if path.drive == "" or not path.is_absolute():
        return None
    if any(part in {"", ".", ".."} for part in path.parts[1:]):
        return None
    return path


def _tail(path: PureWindowsPath) -> list[str]:
    parts = list(path.parts)
    if parts and (parts[0] == path.anchor or parts[0].endswith("\\") or parts[0].endswith("/")):
        parts = parts[1:]
    return [part.casefold() for part in parts]


def _canonicalize(action: str, target: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    copied = {key: params[key] for key in params}
    if action in {"change.download", "change.install"}:
        pin = copied.get("sha256")
        if isinstance(pin, str):
            copied["sha256"] = pin.lower()
        for key in ("staging_directory", "destination"):
            value = copied.get(key)
            if isinstance(value, str):
                path = _windows_path(value)
                if path is not None:
                    copied[key] = str(path)
        allow = copied.get("allowlist")
        if isinstance(allow, list):
            copied["allowlist"] = [item.casefold() if isinstance(item, str) else item for item in allow]
    if action == "repair.printer.clear_queue" and isinstance(copied.get("path"), str):
        path = _windows_path(copied["path"])
        if path is not None:
            copied["path"] = str(path)
    if action in {"change.delete", "change.install"}:
        path = _windows_path(target)
        if path is not None:
            target = str(path)
    return target, copied


def heartbeat_record(device_id: str, utc: str, worker_version: str) -> dict[str, str]:
    """Liveness only: device id, UTC time, and worker version."""
    if (
        not isinstance(device_id, str)
        or not isinstance(utc, str)
        or not isinstance(worker_version, str)
        or not _DEVICE_ID.fullmatch(device_id)
        or not _UTC.fullmatch(utc)
        or not _VERSION.fullmatch(worker_version)
    ):
        raise WorkRefused("heartbeat accepts only device id, UTC time, and worker version")
    return {"device_id": device_id, "utc": utc, "worker_version": worker_version}


def _heartbeat_fields(device_id: str, utc: str, version: str) -> dict[str, str]:
    return heartbeat_record(device_id, utc, version)


def _display_target(target: object) -> str:
    if not isinstance(target, str) or len(target) > 512 or _target_has_secret(target):
        return ""
    return target


def _target_has_secret(target: object) -> bool:
    if not isinstance(target, str) or "://" not in target:
        return False
    parsed = urlsplit(target)
    return bool(parsed.username or parsed.password)


def _safe_action(action: object) -> str:
    if isinstance(action, str) and _ACTION_NAME.fullmatch(action):
        return action
    return "rejected"


def _keep_params(action: str, params: dict[str, Any]) -> dict[str, Any]:
    if action not in ACTION_PARAMS or not _params_allowed(action, params):
        return {}
    return {key: params[key] for key in params}


def _params_allowed(action: str, params: dict[str, Any]) -> bool:
    allowed = ACTION_PARAMS.get(action)
    if allowed is None:
        return False
    return set(params).issubset(allowed)


def _key_is_secret(key: object) -> bool:
    if not isinstance(key, str):
        return True
    folded = key.casefold().replace("-", "_")
    return any(part in folded for part in _SECRET_PARTS)


def _contains_secret_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(_key_is_secret(key) or _contains_secret_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def _contains_surveillance(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.casefold() in _SURVEILLANCE:
                return True
            if _contains_surveillance(item):
                return True
    if isinstance(value, list):
        return any(_contains_surveillance(item) for item in value)
    return False


def _scrub(value: object, redact: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            if _key_is_secret(key) or (isinstance(key, str) and key.casefold() in _SURVEILLANCE):
                continue
            clean[str(key)] = _scrub(item, redact)
        return clean
    if isinstance(value, list):
        return [_scrub(item, redact) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in redact:
            if isinstance(secret, str) and secret and secret in redacted:
                redacted = redacted.replace(secret, "<redacted>")
        return redacted
    return value


def _digest(params: object) -> str:
    raw = json.dumps(_scrub(params), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _iso(moment: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(moment))
