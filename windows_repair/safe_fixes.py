"""Two Windows safe fixes. Both refuse unless the approval gate matches.

Nothing in this module queries Windows, restarts a service, deletes a file,
reboots a computer, or opens a shell. Tests supply the service state, the
queue state, and the fake that stands in for the change. With no fake, a
matching approval still refuses.
"""
from __future__ import annotations

from typing import Any, Callable

from windows_repair.approval import (
    CLEAR_PRINTER_QUEUE,
    RESTART_FAILED_SERVICE,
    evaluate_approval,
)

LIVE_REPAIR_ENABLED = False

REASON_NOT_ONE_SERVICE = "not_one_service"
REASON_NOT_ONE_QUEUE = "not_one_queue"
REASON_STATE_MISSING = "state_missing"
REASON_MULTIPLE_SERVICES = "multiple_services"
REASON_SERVICE_MISMATCH = "service_name_mismatch"
REASON_SERVICE_RUNNING = "service_running"
REASON_NOT_AUTOMATIC = "not_automatic"
REASON_NOT_FAILED = "not_failed"
REASON_QUEUE_MISMATCH = "queue_name_mismatch"
REASON_NOT_STUCK = "queue_not_stuck"
REASON_NO_SPOOL_FILES = "no_spool_files"
REASON_OTHER_QUEUE = "other_queue"
REASON_OUTSIDE_QUEUE = "file_outside_queue"
REASON_LIVE_DISABLED = "live_execution_disabled"
REASON_EXECUTOR_FAILED = "executor_failed"
REASON_REBOOT = "reboot_refused"

_AUTOMATIC_START_TYPES = frozenset({
    "automatic",
    "auto",
    "automatic (delayed start)",
    "automatic delayed start",
    "delayed-auto",
    "delayed auto",
})
_RUNNING_STATES = frozenset({
    "running",
    "startpending",
    "start pending",
    "continuepending",
    "continue pending",
})
_FAILED_STATES = frozenset({"stopped", "failed"})
_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.- ")
_REBOOT_NAMES = frozenset({
    "reboot",
    "shutdown",
    "format",
    "restart-computer",
    "restart_computer",
    "restart computer",
})
_SPOOL_SUFFIXES = frozenset({".spl", ".shd"})
_USER_MARKERS = (
    "\\users\\",
    "\\documents\\",
    "\\desktop\\",
    "\\downloads\\",
    "\\onedrive\\",
)


def restart_failed_automatic_service(
    *,
    device_id: str,
    service_name: str,
    approval: object,
    now: float,
    service_state: dict[str, Any] | None = None,
    restarter: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Restart one named failed automatic service, or refuse.

    A running service is left running. A list of services is not restarted.
    """
    decision = _gate(
        approval,
        device_id=device_id,
        action_id=RESTART_FAILED_SERVICE,
        target=service_name,
        now=now,
    )
    if decision is not None:
        return decision
    if _reboot_requested(service_name, service_state):
        return _refused(
            REASON_REBOOT,
            "The computer was not rebooted.",
            action_id=RESTART_FAILED_SERVICE,
            device_id=device_id,
            target=service_name,
        )
    if not _one_service_name(service_name):
        return _refused(
            REASON_NOT_ONE_SERVICE,
            "Name one service. Every service was left alone.",
            action_id=RESTART_FAILED_SERVICE,
            device_id=device_id,
            target=service_name if isinstance(service_name, str) else "",
        )
    if isinstance(service_state, (list, tuple)):
        return _refused(
            REASON_MULTIPLE_SERVICES,
            "A list of services is not restarted.",
            action_id=RESTART_FAILED_SERVICE,
            device_id=device_id,
            target=service_name,
        )
    if not isinstance(service_state, dict):
        return _refused(
            REASON_STATE_MISSING,
            "No service state was supplied. The service was not restarted.",
            action_id=RESTART_FAILED_SERVICE,
            device_id=device_id,
            target=service_name,
        )
    if "services" in service_state or isinstance(service_state.get("name"), (list, tuple)):
        return _refused(
            REASON_MULTIPLE_SERVICES,
            "A list of services is not restarted.",
            action_id=RESTART_FAILED_SERVICE,
            device_id=device_id,
            target=service_name,
        )
    inspected = service_state.get("name")
    if not isinstance(inspected, str) or inspected.strip() != service_name.strip():
        return _refused(
            REASON_SERVICE_MISMATCH,
            "The inspected service is not the named target.",
            action_id=RESTART_FAILED_SERVICE,
            device_id=device_id,
            target=service_name,
        )
    status = _folded(service_state.get("status")).replace("_", " ")
    if status in _RUNNING_STATES:
        return _refused(
            REASON_SERVICE_RUNNING,
            "A running service is not stopped and is not restarted.",
            action_id=RESTART_FAILED_SERVICE,
            device_id=device_id,
            target=service_name,
        )
    start_type = _folded(service_state.get("start_type")).replace("_", " ")
    if start_type not in _AUTOMATIC_START_TYPES:
        return _refused(
            REASON_NOT_AUTOMATIC,
            "Only an automatic service can be restarted.",
            action_id=RESTART_FAILED_SERVICE,
            device_id=device_id,
            target=service_name,
        )
    if service_state.get("failed") is not True or status not in _FAILED_STATES:
        return _refused(
            REASON_NOT_FAILED,
            "The service is not a failed automatic service.",
            action_id=RESTART_FAILED_SERVICE,
            device_id=device_id,
            target=service_name,
        )
    if restarter is None or LIVE_REPAIR_ENABLED:
        return _refused(
            REASON_LIVE_DISABLED,
            "Live repair is disabled. The service was not restarted.",
            action_id=RESTART_FAILED_SERVICE,
            device_id=device_id,
            target=service_name,
        )
    outcome = restarter(service_name.strip())
    return _executor_result(
        outcome,
        success_status="restarted",
        action_id=RESTART_FAILED_SERVICE,
        device_id=device_id.strip(),
        target=service_name.strip(),
        services_touched=(service_name.strip(),),
        files_touched=(),
    )


def clear_stuck_printer_queue(
    *,
    device_id: str,
    queue_name: str,
    approval: object,
    now: float,
    queue_state: dict[str, Any] | None = None,
    deleter: Callable[[str, tuple[str, ...]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Clear spool files for one named stuck queue, or refuse.

    User documents, the spooler directory, and every other queue stay in place.
    """
    decision = _gate(
        approval,
        device_id=device_id,
        action_id=CLEAR_PRINTER_QUEUE,
        target=queue_name,
        now=now,
    )
    if decision is not None:
        return decision
    if _reboot_requested(queue_name, queue_state):
        return _refused(
            REASON_REBOOT,
            "The computer was not rebooted.",
            action_id=CLEAR_PRINTER_QUEUE,
            device_id=device_id,
            target=queue_name,
        )
    if not _one_queue_name(queue_name):
        return _refused(
            REASON_NOT_ONE_QUEUE,
            "Name one printer queue. No spool file was deleted.",
            action_id=CLEAR_PRINTER_QUEUE,
            device_id=device_id,
            target=queue_name if isinstance(queue_name, str) else "",
        )
    if not isinstance(queue_state, dict):
        return _refused(
            REASON_STATE_MISSING,
            "No queue state was supplied. No spool file was deleted.",
            action_id=CLEAR_PRINTER_QUEUE,
            device_id=device_id,
            target=queue_name,
        )
    inspected = queue_state.get("queue")
    if not isinstance(inspected, str) or inspected.strip() != queue_name.strip():
        return _refused(
            REASON_QUEUE_MISMATCH,
            "The inspected queue is not the named target.",
            action_id=CLEAR_PRINTER_QUEUE,
            device_id=device_id,
            target=queue_name,
        )
    if queue_state.get("stuck") is not True:
        return _refused(
            REASON_NOT_STUCK,
            "The queue is not stuck. No spool file was deleted.",
            action_id=CLEAR_PRINTER_QUEUE,
            device_id=device_id,
            target=queue_name,
        )
    files, problem = _spool_files(queue_name.strip(), queue_state.get("spool_files"))
    if problem is not None:
        detail = {
            REASON_NO_SPOOL_FILES: "The stuck queue has no spool files to clear.",
            REASON_OTHER_QUEUE: "Spool files for another queue were not deleted.",
            REASON_OUTSIDE_QUEUE: "Only spool files for the named queue can be cleared.",
        }[problem]
        return _refused(
            problem,
            detail,
            action_id=CLEAR_PRINTER_QUEUE,
            device_id=device_id,
            target=queue_name,
        )
    if deleter is None or LIVE_REPAIR_ENABLED:
        return _refused(
            REASON_LIVE_DISABLED,
            "Live repair is disabled. No spool file was deleted.",
            action_id=CLEAR_PRINTER_QUEUE,
            device_id=device_id,
            target=queue_name,
        )
    outcome = deleter(queue_name.strip(), files)
    return _executor_result(
        outcome,
        success_status="cleared",
        action_id=CLEAR_PRINTER_QUEUE,
        device_id=device_id.strip(),
        target=queue_name.strip(),
        services_touched=(),
        files_touched=files,
    )


def run_safe_fix(
    action_id: str,
    *,
    device_id: str,
    target: str,
    approval: object,
    now: float,
    service_state: dict[str, Any] | None = None,
    queue_state: dict[str, Any] | None = None,
    restarter: Callable[[str], dict[str, Any]] | None = None,
    deleter: Callable[[str, tuple[str, ...]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one of the two safe fixes. Every other action id is refused."""
    if action_id == RESTART_FAILED_SERVICE:
        return restart_failed_automatic_service(
            device_id=device_id,
            service_name=target,
            approval=approval,
            now=now,
            service_state=service_state,
            restarter=restarter,
        )
    if action_id == CLEAR_PRINTER_QUEUE:
        return clear_stuck_printer_queue(
            device_id=device_id,
            queue_name=target,
            approval=approval,
            now=now,
            queue_state=queue_state,
            deleter=deleter,
        )
    decision = _gate(
        approval,
        device_id=device_id,
        action_id=action_id,
        target=target,
        now=now,
    )
    if decision is not None:
        return decision
    return _refused(
        "action_forbidden",
        "This action stays refused even when an approval names it.",
        action_id=action_id if isinstance(action_id, str) else "",
        device_id=device_id if isinstance(device_id, str) else "",
        target=target if isinstance(target, str) else "",
    )


def _gate(
    approval: object,
    *,
    device_id: object,
    action_id: object,
    target: object,
    now: object,
) -> dict[str, Any] | None:
    decision = evaluate_approval(
        approval,
        device_id=device_id,
        action_id=action_id,
        target=target,
        now=now,
    )
    if decision["allowed"]:
        return None
    return _refused(
        str(decision["reason"]),
        str(decision["detail"]),
        action_id=action_id if isinstance(action_id, str) else "",
        device_id=device_id if isinstance(device_id, str) else "",
        target=target if isinstance(target, str) else "",
    )


def _spool_files(queue_name: str, records: object) -> tuple[tuple[str, ...], str | None]:
    if isinstance(records, (str, bytes)) or not isinstance(records, (list, tuple)):
        return (), REASON_OUTSIDE_QUEUE
    if not records:
        return (), REASON_NO_SPOOL_FILES
    paths: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            return (), REASON_OUTSIDE_QUEUE
        path = record.get("path")
        if not _is_one_spool_file(path):
            return (), REASON_OUTSIDE_QUEUE
        owner = record.get("queue")
        if not isinstance(owner, str) or owner.strip() != queue_name:
            return (), REASON_OTHER_QUEUE
        paths.append(path)
    return tuple(paths), None


def _is_one_spool_file(path: object) -> bool:
    if not isinstance(path, str):
        return False
    raw = path.strip()
    if not raw or any(char in raw for char in ("\n", "\r", "\0")):
        return False
    if not _absolute_windows(raw):
        return False
    folded = raw.replace("/", "\\")
    if ".." in folded.split("\\"):
        return False
    lowered = folded.casefold()
    if any(marker in lowered for marker in _USER_MARKERS):
        return False
    drive, remainder = _split_drive(folded)
    if ":" in remainder:
        return False
    parts = [part for part in remainder.split("\\") if part]
    folded_parts = [part.casefold() for part in parts]
    for index in range(len(folded_parts) - 2):
        if folded_parts[index] != "spool" or folded_parts[index + 1] != "printers":
            continue
        tail = parts[index + 2 :]
        if len(tail) != 1:
            return False
        filename = tail[0]
        if filename in {".", ".."} or filename.endswith((" ", ".")):
            return False
        suffix = filename[filename.rfind("."):].casefold() if "." in filename else ""
        if suffix not in _SPOOL_SUFFIXES:
            return False
        if filename.casefold() in {"printers", "spool"}:
            return False
        return bool(drive) or folded.startswith("\\\\")
    return False


def _absolute_windows(path: str) -> bool:
    if len(path) >= 3 and path[1] == ":" and path[2] in "\\/":
        return True
    return path.startswith("\\\\")


def _split_drive(path: str) -> tuple[str, str]:
    if len(path) >= 2 and path[1] == ":":
        return path[:2], path[2:]
    return "", path


def _one_service_name(value: object) -> bool:
    return _one_label(value, limit=256)


def _one_queue_name(value: object) -> bool:
    return _one_label(value, limit=220)


def _one_label(value: object, *, limit: int) -> bool:
    if not isinstance(value, str):
        return False
    if not 1 <= len(value) <= limit or value != value.strip() or "  " in value:
        return False
    if value in {".", ".."} or value.casefold() in _REBOOT_NAMES:
        return False
    return all(char in _NAME_CHARS for char in value)


def _reboot_requested(target: object, state: object) -> bool:
    if isinstance(target, str) and target.strip().casefold() in _REBOOT_NAMES:
        return True
    if not isinstance(state, dict):
        return False
    return any(state.get(flag) is True for flag in ("reboot", "restart_computer", "format", "registry_wipe"))


def _folded(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().casefold()


def _executor_result(
    outcome: object,
    *,
    success_status: str,
    action_id: str,
    device_id: str,
    target: str,
    services_touched: tuple[str, ...],
    files_touched: tuple[str, ...],
) -> dict[str, Any]:
    if not isinstance(outcome, dict) or outcome.get("ok") is not True:
        return _refused(
            REASON_EXECUTOR_FAILED,
            "The fake executor did not report success. Nothing else was tried.",
            action_id=action_id,
            device_id=device_id,
            target=target,
        )
    return {
        "status": success_status,
        "reason": None,
        "detail": "Fake executor reported success. This computer was not changed.",
        "allowed": True,
        "executed": True,
        "changed_device": False,
        "problem_resolved": False,
        "live": False,
        "fake": True,
        "rebooted": False,
        "action_id": action_id,
        "device_id": device_id,
        "target": target,
        "services_touched": list(services_touched),
        "files_touched": list(files_touched),
    }


def _refused(
    reason: str,
    detail: str,
    *,
    action_id: str,
    device_id: str,
    target: str,
) -> dict[str, Any]:
    return {
        "status": "refused",
        "reason": reason,
        "detail": detail,
        "allowed": False,
        "executed": False,
        "changed_device": False,
        "problem_resolved": False,
        "live": False,
        "fake": False,
        "rebooted": False,
        "action_id": action_id,
        "device_id": device_id,
        "target": target,
        "services_touched": [],
        "files_touched": [],
    }
