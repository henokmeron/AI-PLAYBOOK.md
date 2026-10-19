"""Registered Windows diagnostic and repair procedures.

The model may select a procedure id. It cannot supply a shell command.
Documented commands are explanations for an operator. Runners below do not
invoke them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RISKS = ("READ_ONLY", "LOW_RISK", "ELEVATED_RISK", "DESTRUCTIVE_OR_HIGH_IMPACT")


@dataclass(frozen=True)
class Procedure:
    procedure_id: str
    name: str
    category: str
    windows_versions: tuple[str, ...]
    symptoms: tuple[str, ...]
    risk: str
    requires_admin: bool
    requires_approval: bool
    evidence_required: tuple[str, ...]
    documented_commands: tuple[str, ...]
    runner: str
    verification: str
    rollback: str
    limitations: str

    def public(self) -> dict[str, Any]:
        return {
            "procedure_id": self.procedure_id,
            "name": self.name,
            "category": self.category,
            "windows_versions": list(self.windows_versions),
            "symptoms": list(self.symptoms),
            "risk": self.risk,
            "requires_admin": self.requires_admin,
            "requires_approval": self.requires_approval,
            "evidence_required": list(self.evidence_required),
            "documented_commands": list(self.documented_commands),
            "verification": self.verification,
            "rollback": self.rollback,
            "limitations": self.limitations,
        }


def _p(**kwargs: Any) -> Procedure:
    versions = ("Windows 10", "Windows 11")
    item = Procedure(windows_versions=versions, **kwargs)
    if item.risk not in RISKS:
        raise ValueError(item.procedure_id)
    if item.risk == "READ_ONLY" and item.requires_approval:
        raise ValueError(item.procedure_id)
    if item.risk in {"ELEVATED_RISK", "DESTRUCTIVE_OR_HIGH_IMPACT"} and not item.requires_approval:
        raise ValueError(item.procedure_id)
    return item


PROCEDURES: dict[str, Procedure] = {
    item.procedure_id: item
    for item in (
        _p(
            procedure_id="win.storage.space",
            name="Disk space check",
            category="windows",
            symptoms=("disk full", "low storage", "slow pc"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("disk_free_bytes", "disk_total_bytes"),
            documented_commands=("Get-PSDrive -PSProvider FileSystem",),
            runner="local_disk",
            verification="Compare free space with the customer report. Do not call the fault fixed.",
            rollback="No change is made.",
            limitations="Reports one volume only. Does not delete files.",
        ),
        _p(
            procedure_id="win.update.inspect",
            name="Windows Update evidence",
            category="windows",
            symptoms=("update failed", "updates stuck"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("update_error",),
            documented_commands=("Get-WindowsUpdateLog is not run by this procedure.",),
            runner="interpret_update",
            verification="A missing error code stays UNKNOWN.",
            rollback="No change is made.",
            limitations="Does not install updates or reset Windows Update.",
        ),
        _p(
            procedure_id="win.sfc.propose",
            name="System file check proposal",
            category="windows",
            symptoms=("corrupt system files", "sfc"),
            risk="ELEVATED_RISK",
            requires_admin=True,
            requires_approval=True,
            evidence_required=("symptom",),
            documented_commands=("sfc /scannow", "DISM /Online /Cleanup-Image /RestoreHealth"),
            runner="propose_only",
            verification="Re-run a read-only check after an administrator actually runs the tool.",
            rollback="DISM and SFC are not reversible from this platform.",
            limitations="This platform does not launch sfc or DISM.",
        ),
        _p(
            procedure_id="win.events.recurring",
            name="Recurring event evidence",
            category="windows",
            symptoms=("event viewer", "crash", "bluescreen"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("events",),
            documented_commands=("Get-WinEvent -FilterHashtable @{LogName='System'; Level=2}",),
            runner="interpret_events",
            verification="Event presence is evidence, not a root-cause proof.",
            rollback="No change is made.",
            limitations="Does not read the live Event Log unless evidence is supplied.",
        ),
        _p(
            procedure_id="hw.devices.inventory",
            name="Device problem-code check",
            category="hardware",
            symptoms=("device manager", "missing device", "driver"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("devices",),
            documented_commands=("Get-PnpDevice -PresentOnly",),
            runner="interpret_devices",
            verification="Problem code 0 means no code was reported, not that hardware is healthy.",
            rollback="No change is made.",
            limitations="Does not download drivers.",
        ),
        _p(
            procedure_id="hw.driver.install",
            name="Driver install",
            category="hardware",
            symptoms=("install driver",),
            risk="ELEVATED_RISK",
            requires_admin=True,
            requires_approval=True,
            evidence_required=("device_id", "driver_source", "signature"),
            documented_commands=("pnputil /add-driver is not invoked.",),
            runner="deny_driver_install",
            verification="Not run.",
            rollback="Not run.",
            limitations="Automatic driver download and install are refused.",
        ),
        _p(
            procedure_id="print.diagnose",
            name="Printer evidence workflow",
            category="printer",
            symptoms=("printer", "print queue", "cannot print"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("connection", "queue", "jobs", "spooler"),
            documented_commands=("Get-Printer", "Get-PrintJob", "Get-Service Spooler"),
            runner="interpret_printer",
            verification="Do not clear the queue as the first step.",
            rollback="No change is made.",
            limitations="Uses supplied evidence or a named fixture. Does not talk to a physical printer.",
        ),
        _p(
            procedure_id="print.spooler.restart",
            name="Restart the Print Spooler service",
            category="printer",
            symptoms=("spooler stopped",),
            risk="ELEVATED_RISK",
            requires_admin=True,
            requires_approval=True,
            evidence_required=("spooler",),
            documented_commands=("Restart-Service -Name Spooler",),
            runner="propose_only",
            verification="Read the spooler state again. A successful command is not enough.",
            rollback="Start the service again if a restart left it stopped. Queued jobs can be lost.",
            limitations="The everyday development host does not restart this service. A dedicated test machine must set WINDOWS_REPAIR_ALLOW_SERVICE_RESTART=1 and run as administrator.",
        ),
        _p(
            procedure_id="print.jobs.clear",
            name="Clear one print queue",
            category="printer",
            symptoms=("stuck print jobs",),
            risk="ELEVATED_RISK",
            requires_admin=True,
            requires_approval=True,
            evidence_required=("queue",),
            documented_commands=("Remove-PrintJob for one named job",),
            runner="propose_only",
            verification="Customer confirms one later test page. This platform does not print it.",
            rollback="Cleared jobs cannot be restored.",
            limitations="Refused on this development host even after approval.",
        ),
        _p(
            procedure_id="net.diagnose",
            name="Network evidence workflow",
            category="network",
            symptoms=("no internet", "dns", "wifi"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("adapter", "dns_ok", "gateway_ok"),
            documented_commands=("Get-NetAdapter", "Resolve-DnsName", "Test-Connection"),
            runner="interpret_network",
            verification="A passed ping is not proof that the customer's application works.",
            rollback="No change is made.",
            limitations="Does not disable the firewall or change proxies.",
        ),
        _p(
            procedure_id="win.activation.inspect",
            name="Activation and basic configuration evidence",
            category="windows",
            symptoms=("windows activation", "not activated"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("activation_status",),
            documented_commands=("Get-CimInstance SoftwareLicensingProduct is not run unless evidence is supplied.",),
            runner="interpret_activation",
            verification="A status string is not proof the licence is valid.",
            rollback="No change is made.",
            limitations="Does not change the product key.",
        ),
        _p(
            procedure_id="win.startup.inspect",
            name="Startup and shutdown evidence",
            category="windows",
            symptoms=("slow startup", "shutdown hang"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("boot_seconds",),
            documented_commands=("Get-WinEvent for boot events is not run here.",),
            runner="interpret_startup",
            verification="A long boot time is a clue, not a completed fix.",
            rollback="No change is made.",
            limitations="Does not disable startup applications.",
        ),
        _p(
            procedure_id="win.services.inspect",
            name="Service status evidence",
            category="windows",
            symptoms=("service failed", "service stopped"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("service", "state"),
            documented_commands=("Get-Service",),
            runner="interpret_services",
            verification="Restarting a service is a separate elevated action and is not performed.",
            rollback="No change is made.",
            limitations="Does not start or stop services.",
        ),
        _p(
            procedure_id="win.performance.inspect",
            name="Basic performance evidence",
            category="windows",
            symptoms=("high cpu", "memory pressure"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("cpu_percent",),
            documented_commands=("Get-Counter is not run by this procedure.",),
            runner="interpret_performance",
            verification="A high reading is not a repair.",
            rollback="No change is made.",
            limitations="Does not kill processes.",
        ),
        _p(
            procedure_id="hw.usb.inspect",
            name="USB and peripheral evidence",
            category="hardware",
            symptoms=("usb device", "camera missing", "no audio"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("device_name",),
            documented_commands=("Get-PnpDevice",),
            runner="interpret_usb",
            verification="A missing device may need physical reconnection.",
            rollback="No change is made.",
            limitations="Does not install a driver.",
        ),
        _p(
            procedure_id="net.wifi.inspect",
            name="Wi-Fi adapter evidence",
            category="network",
            symptoms=("wifi disconnected", "wireless down"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("ssid", "radio"),
            documented_commands=("Get-NetAdapter",),
            runner="interpret_wifi",
            verification="Radio state is evidence only.",
            rollback="No change is made.",
            limitations="Does not change the wireless profile or firewall.",
        ),
        _p(
            procedure_id="net.proxy.inspect",
            name="Proxy and VPN evidence",
            category="network",
            symptoms=("proxy error", "vpn connected"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("proxy", "vpn"),
            documented_commands=("Get-ItemProperty for WinHTTP proxy is not run here.",),
            runner="interpret_proxy",
            verification="A proxy value is not changed.",
            rollback="No change is made.",
            limitations="Does not disable a proxy or VPN.",
        ),
        _p(
            procedure_id="net.tls.inspect",
            name="Certificate and TLS evidence",
            category="network",
            symptoms=("certificate error", "tls error"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("certificate_error",),
            documented_commands=(),
            runner="interpret_tls",
            verification="A certificate error is recorded. TLS is not weakened.",
            rollback="No change is made.",
            limitations="Does not install or delete certificates.",
        ),
        _p(
            procedure_id="app.browser.inspect",
            name="Browser connectivity evidence",
            category="application",
            symptoms=("browser cannot", "edge error"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("browser", "error"),
            documented_commands=(),
            runner="interpret_browser",
            verification="A browser error is not fixed by this procedure.",
            rollback="No change is made.",
            limitations="Does not reset the browser profile.",
        ),
        _p(
            procedure_id="app.permissions.inspect",
            name="Permissions and profile evidence",
            category="application",
            symptoms=("permission denied", "profile error"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("path", "access"),
            documented_commands=(),
            runner="interpret_permissions",
            verification="An access error is not fixed by changing ACLs here.",
            rollback="No change is made.",
            limitations="Does not take ownership or change permissions.",
        ),
        _p(
            procedure_id="net.firewall.disable",
            name="Disable firewall",
            category="network",
            symptoms=("firewall",),
            risk="DESTRUCTIVE_OR_HIGH_IMPACT",
            requires_admin=True,
            requires_approval=True,
            evidence_required=(),
            documented_commands=(),
            runner="deny_destructive",
            verification="Not applicable.",
            rollback="Not applicable.",
            limitations="Denied. Firewalls are not turned off by this platform.",
        ),
        _p(
            procedure_id="app.crash.evidence",
            name="Application crash evidence",
            category="application",
            symptoms=("application crash", "office", "browser"),
            risk="READ_ONLY",
            requires_admin=False,
            requires_approval=False,
            evidence_required=("application", "fault"),
            documented_commands=("Get-WinEvent -LogName Application",),
            runner="interpret_app",
            verification="A crash event does not by itself justify a reinstall.",
            rollback="No change is made.",
            limitations="Does not reinstall software.",
        ),
    )
}


def get_procedure(procedure_id: str) -> Procedure:
    item = PROCEDURES.get(procedure_id)
    if item is None:
        raise KeyError(procedure_id)
    return item


FIXTURES: dict[str, dict[str, Any]] = {
    "printer_spooler_stopped": {
        "connection": "usb",
        "queue": "Office",
        "jobs": [],
        "spooler": "Stopped",
        "driver": "HP Universal Printing",
        "printers": [{"name": "Office", "driver": "HP Universal Printing", "port": "USB001"}],
        "reachable": None,
    },
    "printer_stuck_usb": {
        "connection": "usb",
        "queue": "HP-Office",
        "jobs": [{"id": 12, "document": "invoice.pdf", "status": "error"}],
        "spooler": "running",
        "driver": "HP Universal Printing",
        "errors": ["job 12 stuck"],
        "reachable": None,
    },
    "network_dns": {
        "adapter": "Wi-Fi",
        "adapter_status": "Up",
        "ip": "192.168.1.40",
        "dhcp": True,
        "dns_ok": False,
        "gateway_ok": True,
        "vpn": False,
    },
    "driver_code_28": {
        "devices": [
            {
                "name": "USB Audio",
                "problem_code": 28,
                "driver_provider": "",
                "driver_version": "",
                "status": "Error",
            }
        ]
    },
    "update_0x80070002": {"update_error": "0x80070002"},
    "app_crash": {"application": "WINWORD.EXE", "fault": "faulting module ntdll.dll"},
    "events_disk": {"events": [{"id": 7, "source": "Disk", "count": 4}]},
}
