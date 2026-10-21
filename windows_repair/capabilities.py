"""What this repository can actually do on each platform.

A row is not a device agent. macOS, Android, and iOS have no agent, collector,
or package here. Web control is the existing loopback console, not control of
other browsers or phones. A Windows diagnostic is not cross-platform support.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalogue import PROCEDURES
from .providers import LIVE_PROCEDURES
from .runner import SCRIPTS

_LIVE_RAN_ON_THIS_PC = frozenset({
    "win.storage.space",
    "print.diagnose",
    "net.diagnose",
    "win.services.inspect",
    "hw.devices.inventory",
})
_DENIED_RUNNERS = frozenset({"propose_only", "deny_driver_install", "deny_destructive"})

SHARED_PROTOCOL = (
    "A future device agent would enrol with a device secret, accept only a signed "
    "job whose body matches the issued record, and run one registered read-only "
    "collector. The payload cannot change the procedure, add an approval, or set "
    "the lifecycle. No shell command is accepted. That is a contract note. Agents "
    "for macOS, Android, and iOS are not implemented in this repository."
)


@dataclass(frozen=True)
class Capability:
    operation: str
    platform: str
    privilege: str
    risk: str
    approval: str
    timeout_seconds: int | None
    supported_versions: str
    test_coverage: str
    status: str
    notes: str

    def public(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "platform": self.platform,
            "privilege": self.privilege,
            "risk": self.risk,
            "approval": self.approval,
            "timeout_seconds": self.timeout_seconds,
            "supported_versions": self.supported_versions,
            "test_coverage": self.test_coverage,
            "status": self.status,
            "notes": self.notes,
        }


def _windows_row(procedure_id: str) -> Capability:
    procedure = PROCEDURES[procedure_id]
    script_id = LIVE_PROCEDURES.get(procedure_id)
    live = script_id is not None and script_id in SCRIPTS
    if procedure.runner in _DENIED_RUNNERS or procedure.risk != "READ_ONLY":
        status = "BLOCKED" if procedure_id == "print.spooler.restart" else "NOT IMPLEMENTED"
        coverage = "Catalogue and refusal tests. The change is not executed on this computer."
        notes = procedure.limitations
        timeout = None
    elif live and procedure_id in _LIVE_RAN_ON_THIS_PC:
        status = "PARTIAL"
        coverage = (
            "windows_repair.tests.test_live_diagnostics ran this read-only collector "
            "on the development PC. That is not a customer endpoint."
        )
        notes = "Diagnostic only. problem_resolved stays false. No repair authority."
        timeout = 20
    elif live:
        status = "NOT VERIFIED"
        coverage = "The PowerShell script is registered. This pass did not execute this collector."
        notes = "Diagnostic only. A registered script is not evidence that it was run."
        timeout = 20
    else:
        status = "PARTIAL"
        coverage = "Interpreter tests use supplied evidence or fixtures. No live collector is registered."
        notes = procedure.limitations
        timeout = None
    return Capability(
        operation=procedure_id,
        platform="windows",
        privilege="administrator" if procedure.requires_admin else "current-user",
        risk=procedure.risk,
        approval="required" if procedure.requires_approval else "none",
        timeout_seconds=timeout,
        supported_versions=", ".join(procedure.windows_versions),
        test_coverage=coverage,
        status=status,
        notes=notes,
    )


def _platform_rows() -> tuple[Capability, ...]:
    return (
        Capability(
            operation="device-agent",
            platform="darwin",
            privilege="not-applicable",
            risk="READ_ONLY",
            approval="none",
            timeout_seconds=None,
            supported_versions="none",
            test_coverage="No macOS test exists.",
            status="NOT IMPLEMENTED",
            notes="No macOS agent, collector, package, or device-management API is in this repository. " + SHARED_PROTOCOL,
        ),
        Capability(
            operation="device-agent",
            platform="android",
            privilege="not-applicable",
            risk="READ_ONLY",
            approval="none",
            timeout_seconds=None,
            supported_versions="none",
            test_coverage="No Android test exists.",
            status="BLOCKED",
            notes=(
                "No Android agent is in this repository. An ordinary application cannot manage "
                "every Android device. " + SHARED_PROTOCOL
            ),
        ),
        Capability(
            operation="device-agent",
            platform="ios",
            privilege="not-applicable",
            risk="READ_ONLY",
            approval="none",
            timeout_seconds=None,
            supported_versions="none",
            test_coverage="No iPhone or iPad test exists.",
            status="BLOCKED",
            notes=(
                "No iOS agent is in this repository. An ordinary application cannot manage "
                "every iPhone or iPad. " + SHARED_PROTOCOL
            ),
        ),
        Capability(
            operation="loopback-console",
            platform="web",
            privilege="operator-session",
            risk="READ_ONLY",
            approval="csrf-and-role",
            timeout_seconds=None,
            supported_versions="browser that can reach 127.0.0.1",
            test_coverage="web.test_auth and web.test_server exercise the loopback console with a fake gateway.",
            status="PARTIAL",
            notes=(
                "Web control means the existing console bound to loopback. It does not control "
                "other browsers, phones, or remote desktops. The model gateway behind it was not "
                "called in this pass."
            ),
        ),
    )


def registry() -> tuple[Capability, ...]:
    windows = tuple(_windows_row(procedure_id) for procedure_id in PROCEDURES)
    return windows + _platform_rows()


def by_platform(platform: str) -> tuple[Capability, ...]:
    return tuple(item for item in registry() if item.platform == platform)
