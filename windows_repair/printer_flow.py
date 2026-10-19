"""Printer diagnosis and one approved repair.

Restarting the Print Spooler is the only repair this workflow can execute.
It does not delete jobs, remove drivers, change ports, or install packages.
On a normal development computer the restart is refused even after approval.
"""
from __future__ import annotations

import os
from typing import Any, Callable

from integrations.approvals import ApprovalService
from integrations.errors import ApprovalRequired, PermissionDenied
from integrations.tenancy import TenantContext

from .providers import FixtureProvider, LiveWindowsProvider

_SERVICE = "Spooler"


def classify_printer(evidence: dict[str, Any]) -> dict[str, Any]:
    """Choose a failure category from evidence. Does not change the computer."""
    source = str(evidence.get("evidence_source") or "unknown")
    spooler = str(evidence.get("spooler") or "unknown")
    printers = evidence.get("printers") or []
    jobs = evidence.get("jobs") or []
    if evidence.get("ok") is False:
        category = "could_not_collect"
        action = None
    elif source == "live_windows" and not printers:
        category = "no_queue"
        action = None
    elif spooler.casefold() not in {"running", "4"}:
        category = "spooler"
        action = "print.spooler.restart"
    elif jobs:
        category = "stuck_or_pending_job"
        action = None
    else:
        category = "queue_idle"
        action = None
    return {
        "evidence_source": source,
        "mocked": source == "fixture",
        "category": category,
        "spooler": spooler,
        "printer_count": len(printers) if isinstance(printers, list) else 0,
        "job_count": len(jobs) if isinstance(jobs, list) else 0,
        "proposed_procedure": action,
        "risk": "ELEVATED_RISK" if action else "READ_ONLY",
        "problem_resolved": False,
        "note": (
            "Pending jobs are not deleted. A stopped spooler can be restarted only after approval."
            if action else
            "No automatic repair is offered for this evidence."
        ),
    }


def _admin() -> bool:
    if os.name != "nt":
        return False
    import ctypes
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def default_restart(_: dict[str, Any]) -> dict[str, Any]:
    """Refuse unless a dedicated test machine opted in. Never deletes jobs."""
    allowed = os.environ.get("WINDOWS_REPAIR_ALLOW_SERVICE_RESTART") == "1"
    if not allowed or not _admin():
        return {
            "executed": False,
            "changed_device": False,
            "status": "needs_administrator",
            "detail": (
                "This process did not restart the Print Spooler. On a dedicated Windows test "
                "machine, run an elevated console and set WINDOWS_REPAIR_ALLOW_SERVICE_RESTART=1. "
                "Do not set that on an everyday computer."
            ),
        }
    from .runner import powershell_exe, run_argv
    executable = powershell_exe()
    if executable is None:
        return {"executed": False, "changed_device": False, "status": "tool_missing", "detail": "PowerShell was not found."}
    result = run_argv(
        [executable, "-NoProfile", "-NonInteractive", "-Command", "Restart-Service -Name Spooler -Force"],
        timeout=30,
    )
    return {
        "executed": bool(result.get("ok")),
        "changed_device": bool(result.get("ok")),
        "status": "restarted" if result.get("ok") else "failed",
        "detail": str(result.get("detail") or result.get("stderr") or "Restart-Service finished.")[:300],
    }


class PrinterWorkflow:
    def __init__(
        self,
        approvals: ApprovalService | None = None,
        provider: Any | None = None,
        restarter: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.approvals = approvals or ApprovalService()
        self.provider = provider if provider is not None else LiveWindowsProvider()
        self.restarter = restarter or default_restart
        self.audit: list[dict[str, Any]] = []

    def diagnose(self, *, fixture: str | None = None) -> dict[str, Any]:
        if fixture:
            evidence = FixtureProvider().collect("print.diagnose", fixture)
        else:
            evidence = self.provider.collect("print.diagnose")
        report = classify_printer(evidence)
        report["evidence"] = {
            "spooler": evidence.get("spooler"),
            "printers": evidence.get("printers"),
            "jobs": evidence.get("jobs"),
            "detail": evidence.get("detail"),
            "status": evidence.get("status"),
        }
        self._audit("diagnose", report["category"], None)
        return report

    def request_restart(self, tenant_id: str, device_id: str, requester: str) -> dict[str, Any]:
        ctx = TenantContext.create(tenant_id, requester, ["devices:write"])
        params = {"device_id": device_id, "service": _SERVICE, "procedure_id": "print.spooler.restart"}
        item = self.approvals.request(ctx, "windows_repair", "print.spooler.restart", params, "Restart Print Spooler")
        self._audit("approval_requested", item.approval_id, requester)
        return {"approval_id": item.approval_id, "params": params, "status": item.status}

    def approve(self, tenant_id: str, approval_id: str, approver: str, *, allow: bool = True) -> dict[str, Any]:
        ctx = TenantContext.create(tenant_id, approver, ["devices:write"])
        try:
            item = self.approvals.decide(approval_id, ctx, allow)
        except (ApprovalRequired, PermissionDenied) as exc:
            self._audit("approval_rejected", approval_id, approver)
            return {"status": "approval_rejected", "detail": exc.message}
        self._audit("approval_decided", item.status, approver)
        return {"status": item.status, "approval_id": item.approval_id}

    def _collect(self, fixture: str | None) -> dict[str, Any]:
        if fixture:
            return FixtureProvider().collect("print.diagnose", fixture)
        return self.provider.collect("print.diagnose")

    def execute_restart(
        self,
        tenant_id: str,
        device_id: str,
        approval_id: str,
        operator: str,
        *,
        fixture: str | None = None,
    ) -> dict[str, Any]:
        """Re-check the approval immediately, then restart only when the restarter allows it."""
        params = {"device_id": device_id, "service": _SERVICE, "procedure_id": "print.spooler.restart"}
        operator_ctx = TenantContext.create(tenant_id, operator, ["devices:write"])
        try:
            self.approvals.consume(approval_id, operator_ctx, "windows_repair", "print.spooler.restart", params)
        except (ApprovalRequired, PermissionDenied) as exc:
            self._audit("approval_rejected", approval_id, operator)
            return {
                "executed": False,
                "changed_device": False,
                "problem_resolved": False,
                "verification": "not_run",
                "status": "approval_rejected",
                "detail": exc.message,
            }
        before = self._collect(fixture)
        action = self.restarter(params)
        after = self._collect(fixture)
        before_running = str(before.get("spooler") or "").casefold() in {"running", "4"}
        after_running = str(after.get("spooler") or "").casefold() in {"running", "4"}
        if action.get("executed") and not before_running and after_running:
            verification = "resolved"
            resolved = True
        elif not action.get("executed"):
            verification = "could_not_verify"
            resolved = False
        else:
            verification = "unresolved"
            resolved = False
        result = {
            "procedure_id": "print.spooler.restart",
            "device_id": device_id,
            "executed": bool(action.get("executed")),
            "changed_device": bool(action.get("changed_device")),
            "problem_resolved": resolved,
            "verification": verification,
            "status": action.get("status"),
            "detail": action.get("detail"),
            "before_spooler": before.get("spooler"),
            "after_spooler": after.get("spooler"),
            "evidence_source": after.get("evidence_source"),
        }
        self._audit("repair", verification, operator)
        return result

    def _audit(self, action: str, outcome: str, operator: str | None) -> None:
        self.audit.append({"action": action, "outcome": outcome, "operator": operator})
