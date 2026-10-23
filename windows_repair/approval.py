"""Explicit approval gate for one Windows safe fix.

The default is refusal. A diagnostic result is not an approval, and a
matching approval is the only way past this gate. Issuing an approval does
not restart a service, delete a file, or change a computer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

RESTART_FAILED_SERVICE = "win.service.restart_failed"
CLEAR_PRINTER_QUEUE = "print.queue.clear_spool"

ALLOWED_ACTION_IDS = frozenset({
    RESTART_FAILED_SERVICE,
    CLEAR_PRINTER_QUEUE,
})

# Named here so a test can show that an approval for one of these still refuses.
FORBIDDEN_ACTION_IDS = frozenset({
    "reboot",
    "format",
    "registry.wipe",
    "firewall.change",
    "uninstall",
    "driver.download",
    "driver.install",
    "file.delete",
    "microsoft365",
    "signin",
    "mail",
    "tokens",
})

REASON_MISSING = "approval_missing"
REASON_EXPIRED = "approval_expired"
REASON_DEVICE = "approval_device_mismatch"
REASON_ACTION = "approval_action_mismatch"
REASON_TARGET = "approval_target_mismatch"
REASON_BLANKET = "blanket_approval"
REASON_FORBIDDEN = "action_forbidden"
REASON_NOT_APPROVAL = "not_an_approval"

_BLANKET_NAMES = frozenset({
    "",
    "*",
    "all",
    "any",
    "every",
    "all services",
    "all queues",
    "any service",
    "any queue",
})
_FORBIDDEN_MARKERS = (
    "reboot",
    "shutdown",
    "format",
    "registry",
    "firewall",
    "uninstall",
    "driver",
    "microsoft365",
    "office365",
    "m365",
    "signin",
    "mail",
    "token",
    "delete",
)


@dataclass(frozen=True)
class Approval:
    """One device, one action id, one target, and an expiry instant.

    ``expires_at`` is exclusive: the approval is valid only while ``now`` is
    strictly earlier than ``expires_at``.
    """

    device_id: str
    action_id: str
    target: str
    expires_at: float


def issue_approval(
    *,
    device_id: str,
    action_id: str,
    target: str,
    expires_at: float,
) -> Approval:
    """Record the three names an approval must carry. This does not run the action."""
    if not isinstance(device_id, str) or not isinstance(action_id, str) or not isinstance(target, str):
        raise TypeError("device_id, action_id, and target must be strings")
    expiry = _finite_time(expires_at)
    if expiry is None:
        raise ValueError("expires_at must be a finite number")
    return Approval(
        device_id=device_id.strip(),
        action_id=action_id.strip(),
        target=target.strip(),
        expires_at=expiry,
    )


def is_forbidden_action(action_id: str) -> bool:
    """Reboot, wipe, driver, mail, and the other out-of-scope actions stay refused."""
    if not isinstance(action_id, str):
        return True
    folded = action_id.strip().casefold()
    if folded in FORBIDDEN_ACTION_IDS:
        return True
    compact = folded.replace("_", "").replace("-", "").replace(" ", "").replace(".", "")
    return any(marker in compact for marker in _FORBIDDEN_MARKERS)


def evaluate_approval(
    approval: object,
    *,
    device_id: object,
    action_id: object,
    target: object,
    now: object,
) -> dict[str, Any]:
    """Allow only an unexpired Approval for this device, action id, and target."""
    if approval is None:
        return _decision(False, REASON_MISSING, "Approval is missing.")
    if not isinstance(approval, Approval):
        return _decision(
            False,
            REASON_NOT_APPROVAL,
            "A diagnostic result is not an approval. Pass an explicit Approval.",
        )

    approved_device = _strip(approval.device_id)
    approved_action = _strip(approval.action_id)
    approved_target = _strip(approval.target)
    if (
        approved_device is None
        or approved_action is None
        or approved_target is None
        or not _single_name(approved_device)
        or not _single_name(approved_action)
        or not _single_name(approved_target)
    ):
        return _decision(
            False,
            REASON_BLANKET,
            "Blanket approval is refused. Name one device, one action, and one target.",
        )

    requested_action = _strip(action_id) if isinstance(action_id, str) else None
    if is_forbidden_action(approved_action) or requested_action is None or is_forbidden_action(requested_action):
        return _decision(
            False,
            REASON_FORBIDDEN,
            "This action stays refused even when an approval names it.",
        )
    if approved_action not in ALLOWED_ACTION_IDS or requested_action not in ALLOWED_ACTION_IDS:
        return _decision(
            False,
            REASON_FORBIDDEN,
            "Only a failed-service restart or one printer-queue clear can be approved.",
        )

    expiry = _finite_time(approval.expires_at)
    current = _finite_time(now)
    if expiry is None or current is None or current >= expiry:
        return _decision(False, REASON_EXPIRED, "Approval has expired.")

    requested_device = _strip(device_id) if isinstance(device_id, str) else None
    if requested_device is None or requested_device != approved_device:
        return _decision(False, REASON_DEVICE, "Approval is for a different device.")
    if requested_action != approved_action:
        return _decision(False, REASON_ACTION, "Approval is for a different action.")
    requested_target = _strip(target) if isinstance(target, str) else None
    if requested_target is None or requested_target != approved_target:
        return _decision(False, REASON_TARGET, "Approval is for a different target.")

    return _decision(
        True,
        None,
        "Approval matches this device, action, and target.",
        device_id=approved_device,
        action_id=approved_action,
        target=approved_target,
    )


def _strip(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip()


def _single_name(value: str) -> bool:
    if value.casefold() in _BLANKET_NAMES:
        return False
    if any(char in value for char in ",;*?\\/\n\r\t"):
        return False
    return True


def _finite_time(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _decision(
    allowed: bool,
    reason: str | None,
    detail: str,
    *,
    device_id: str | None = None,
    action_id: str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "allowed": allowed,
        "status": "approved" if allowed else "refused",
        "reason": reason,
        "detail": detail,
    }
    if allowed:
        result["device_id"] = device_id
        result["action_id"] = action_id
        result["target"] = target
    return result
