"""Select and run registered Windows procedures.

Elevated and destructive runners do not change this computer. A successful
diagnostic is not reported as a repaired fault.
"""
from __future__ import annotations

import os
import shutil
from typing import Any

from .catalogue import FIXTURES, PROCEDURES, get_procedure


class RepairDenied(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def list_procedures() -> list[dict[str, Any]]:
    return [item.public() for item in PROCEDURES.values()]


def _unfixed(detail: str, *, facts: list[str], hypotheses: list[str], procedure_id: str) -> dict[str, Any]:
    return {
        "procedure_id": procedure_id,
        "executed": True,
        "changed_device": False,
        "problem_resolved": False,
        "detail": detail,
        "facts": facts,
        "hypotheses": hypotheses,
        "mocked": True,
    }


def _local_disk() -> dict[str, Any]:
    usage = shutil.disk_usage("C:\\" if __import__("os").name == "nt" else "/")
    free_pct = (usage.free / usage.total * 100.0) if usage.total else 0.0
    return {
        "procedure_id": "win.storage.space",
        "executed": True,
        "changed_device": False,
        "problem_resolved": False,
        "mocked": False,
        "detail": f"free_bytes={usage.free} total_bytes={usage.total} free_pct={free_pct:.0f}",
        "facts": [f"Observed free space {usage.free} bytes on the anchor volume."],
        "hypotheses": ["Low free space can cause slowdowns. This check did not prove that is the customer's fault."],
    }


def _printer(evidence: dict[str, Any]) -> dict[str, Any]:
    connection = evidence.get("connection") or "unknown"
    queue = evidence.get("queue") or "unknown"
    jobs = evidence.get("jobs") or []
    spooler = evidence.get("spooler") or "unknown"
    facts = [
        f"Connection type is {connection}.",
        f"Queue is {queue}.",
        f"Pending or errored jobs: {len(jobs) if isinstance(jobs, list) else jobs}.",
        f"Print spooler state is {spooler}.",
    ]
    hypotheses: list[str] = []
    if jobs and spooler == "running":
        hypotheses.append("A stuck job is more likely than a dead spooler. Do not reset the print subsystem first.")
    elif spooler != "running":
        hypotheses.append("The spooler is not reported as running. Restarting it is an elevated action and is not performed here.")
    else:
        hypotheses.append("Evidence is too thin to choose a printer root cause.")
    if connection == "network" and evidence.get("reachable") is False:
        hypotheses.append("The printer host did not answer. Physical or network access may be required.")
    return _unfixed(
        "Printer diagnosis only. No queue was cleared.",
        facts=facts,
        hypotheses=hypotheses,
        procedure_id="print.diagnose",
    )


def _services(evidence: dict[str, Any]) -> dict[str, Any]:
    rows = evidence.get("services") if isinstance(evidence.get("services"), list) else []
    facts = []
    for row in rows[:8]:
        if isinstance(row, dict):
            facts.append(f"{row.get('name') or 'service'} is {row.get('status') or 'unknown'}.")
    if not facts:
        facts.append("No service rows were supplied.")
    return _unfixed(
        "Service status only. No service was started or stopped.",
        facts=facts,
        hypotheses=["A stopped service is a clue. Restarting it is a separate elevated action and is not performed."],
        procedure_id="win.services.inspect",
    )


def _network(evidence: dict[str, Any]) -> dict[str, Any]:
    dns_ok = evidence.get("dns_ok")
    if dns_ok is None:
        dns_ok = evidence.get("dns_localhost_ok")
    facts = [
        f"Adapter {evidence.get('adapter') or 'unknown'} is {evidence.get('adapter_status') or 'unknown'}.",
        f"DNS ok={dns_ok}. Gateway ok={evidence.get('gateway_ok')}.",
    ]
    hypotheses = []
    if dns_ok is False and evidence.get("gateway_ok") is True:
        hypotheses.append("Gateway answers and DNS does not. Name resolution is the leading hypothesis.")
    elif evidence.get("gateway_ok") is False:
        hypotheses.append("The gateway did not answer. This is not a reason to disable the firewall.")
    else:
        hypotheses.append("Supplied network evidence does not isolate one fault.")
    return _unfixed("Network diagnosis only.", facts=facts, hypotheses=hypotheses, procedure_id="net.diagnose")


def _devices(evidence: dict[str, Any]) -> dict[str, Any]:
    devices = evidence.get("devices") or []
    facts = []
    hypotheses = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        code = device.get("problem_code")
        facts.append(f"{device.get('name') or 'device'} problem_code={code}.")
        if code == 28:
            hypotheses.append(
                "Code 28 means a driver is missing. Install only a signed package from the vendor after approval. Do not download an arbitrary driver."
            )
    if not facts:
        facts.append("No device rows were supplied.")
        hypotheses.append("Device health is UNKNOWN.")
    return _unfixed("Device inventory from supplied evidence.", facts=facts, hypotheses=hypotheses, procedure_id="hw.devices.inventory")


def _update(evidence: dict[str, Any]) -> dict[str, Any]:
    code = evidence.get("update_error")
    if not code:
        return _unfixed(
            "No Windows Update error was supplied.",
            facts=["Update error code is missing."],
            hypotheses=["Cause is UNKNOWN until an error code or log excerpt is collected."],
            procedure_id="win.update.inspect",
        )
    return _unfixed(
        f"Recorded update error {code}.",
        facts=[f"Caller supplied update error {code}."],
        hypotheses=["0x80070002 often means a missing file. That is a hypothesis, not a completed repair."],
        procedure_id="win.update.inspect",
    )


def _events(evidence: dict[str, Any]) -> dict[str, Any]:
    events = evidence.get("events") or []
    facts = [f"{len(events)} event row(s) supplied."]
    hypotheses = ["Repeated disk events can mean storage trouble. They do not authorise a format or reset."]
    return _unfixed("Event evidence recorded.", facts=facts, hypotheses=hypotheses, procedure_id="win.events.recurring")


def _app(evidence: dict[str, Any]) -> dict[str, Any]:
    return _unfixed(
        "Application evidence recorded.",
        facts=[f"{evidence.get('application') or 'unknown'} fault={evidence.get('fault') or 'unspecified'}."],
        hypotheses=["A crash module is a clue. It is not approval to reinstall Windows or the application."],
        procedure_id="app.crash.evidence",
    )


def _note(procedure_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    keys = ", ".join(sorted(str(key) for key in evidence)) or "none"
    return _unfixed(
        "Evidence recorded. No change was made.",
        facts=[f"Evidence keys: {keys}."],
        hypotheses=["This reading does not prove a root cause and does not authorise a repair."],
        procedure_id=procedure_id,
    )


_RUNNERS = {
    "local_disk": lambda evidence: _local_disk(),
    "interpret_printer": _printer,
    "interpret_network": _network,
    "interpret_devices": _devices,
    "interpret_update": _update,
    "interpret_events": _events,
    "interpret_app": _app,
    "interpret_activation": lambda evidence: _note("win.activation.inspect", evidence),
    "interpret_startup": lambda evidence: _note("win.startup.inspect", evidence),
    "interpret_services": _services,
    "interpret_performance": lambda evidence: _note("win.performance.inspect", evidence),
    "interpret_usb": lambda evidence: _note("hw.usb.inspect", evidence),
    "interpret_wifi": lambda evidence: _note("net.wifi.inspect", evidence),
    "interpret_proxy": lambda evidence: _note("net.proxy.inspect", evidence),
    "interpret_tls": lambda evidence: _note("net.tls.inspect", evidence),
    "interpret_browser": lambda evidence: _note("app.browser.inspect", evidence),
    "interpret_permissions": lambda evidence: _note("app.permissions.inspect", evidence),
}


def _adapt_live(procedure_id: str, live: dict[str, Any]) -> dict[str, Any]:
    """Interpreter input. Gateway addresses are not copied into the diagnosis."""
    if procedure_id == "net.diagnose":
        addresses = live.get("addresses") if isinstance(live.get("addresses"), list) else []
        first = addresses[0] if addresses and isinstance(addresses[0], dict) else {}
        return {
            "adapter": first.get("name") or "unspecified",
            "adapter_status": "present" if addresses else "unknown",
            "dns_ok": live.get("dns_localhost_ok"),
            "gateway_ok": live.get("gateway_ok"),
        }
    if procedure_id == "hw.devices.inventory":
        problems = live.get("problems") if isinstance(live.get("problems"), list) else []
        return {
            "devices": [
                {"name": row.get("name"), "problem_code": row.get("problem")}
                for row in problems if isinstance(row, dict)
            ],
            "present_count": live.get("present_count"),
        }
    if procedure_id == "win.services.inspect":
        return {"services": live.get("services") if isinstance(live.get("services"), list) else []}
    if procedure_id == "print.diagnose":
        return {
            "connection": "local",
            "queue": "reported",
            "jobs": live.get("jobs") if isinstance(live.get("jobs"), list) else [],
            "spooler": str(live.get("spooler") or "unknown").casefold(),
        }
    return {key: value for key, value in live.items() if key not in {"gateway", "addresses"}}


def evidence_for(name: str | None, supplied: dict[str, Any] | None) -> dict[str, Any]:
    if supplied:
        return dict(supplied)
    if name and name in FIXTURES:
        return dict(FIXTURES[name])
    return {}


def plan(symptom: str, *, fixture: str | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pick registered procedures from the symptom text. Does not run repairs."""
    text = (symptom or "").casefold()
    chosen = []
    for proc in PROCEDURES.values():
        if proc.risk == "DESTRUCTIVE_OR_HIGH_IMPACT":
            continue
        if any(token in text for token in proc.symptoms):
            chosen.append(proc.procedure_id)
    if not chosen:
        chosen = ["win.storage.space"]
    payload = evidence_for(fixture, evidence)
    return {
        "symptom": symptom[:300],
        "procedure_ids": chosen,
        "evidence_source": "fixture:" + fixture if fixture and not evidence else ("caller" if evidence else "none"),
        "mocked_fixture": fixture if fixture else None,
        "approval_required": [pid for pid in chosen if PROCEDURES[pid].requires_approval],
        "problem_resolved": False,
        "note": "This plan does not mean the fault is fixed.",
        "evidence_keys": sorted(payload.keys()),
    }


def execute(
    procedure_id: str,
    *,
    evidence: dict[str, Any] | None = None,
    fixture: str | None = None,
    approval_id: str | None = None,
    operator: str = "operator",
) -> dict[str, Any]:
    try:
        proc = get_procedure(procedure_id)
    except KeyError as exc:
        raise RepairDenied("unknown procedure") from exc
    if any(token in str(evidence or "") for token in ("powershell -enc", "cmd /c", "Invoke-Expression")):
        raise RepairDenied("evidence cannot carry a command")
    if proc.risk == "DESTRUCTIVE_OR_HIGH_IMPACT" or proc.runner == "deny_destructive":
        return {
            "procedure_id": proc.procedure_id,
            "executed": False,
            "changed_device": False,
            "problem_resolved": False,
            "status": "denied",
            "operator": operator,
            "detail": "Destructive or security-weakening procedures are denied.",
        }
    if proc.runner in {"propose_only", "deny_driver_install"}:
        if proc.requires_approval and not approval_id:
            return {
                "procedure_id": proc.procedure_id,
                "executed": False,
                "changed_device": False,
                "problem_resolved": False,
                "status": "approval_required",
                "operator": operator,
                "detail": "Approval is required and none was supplied.",
            }
        return {
            "procedure_id": proc.procedure_id,
            "executed": False,
            "changed_device": False,
            "problem_resolved": False,
            "status": "approved_not_run_on_this_host" if approval_id else "not_run",
            "operator": operator,
            "approval_id": approval_id,
            "detail": "Recorded only. This development host does not apply driver, spooler, SFC, or DISM changes.",
            "mocked": True,
        }
    runner = _RUNNERS.get(proc.runner)
    if runner is None:
        raise RepairDenied("procedure has no registered runner")
    live_collected = None
    if not evidence and not fixture and os.name == "nt" and proc.runner != "local_disk":
        from .providers import LIVE_PROCEDURES, LiveWindowsProvider

        if procedure_id in LIVE_PROCEDURES:
            live_collected = LiveWindowsProvider().collect(procedure_id)
            if live_collected.get("evidence_source") != "live_windows":
                return {
                    "procedure_id": proc.procedure_id,
                    "executed": False,
                    "changed_device": False,
                    "problem_resolved": False,
                    "status": "diagnosed",
                    "operator": operator,
                    "mocked": False,
                    "evidence_source": str(live_collected.get("evidence_source") or "unavailable"),
                    "detail": "The live collector did not return evidence. No repair was run.",
                }
            evidence = _adapt_live(procedure_id, live_collected)
    result = runner(evidence_for(fixture, evidence))
    result["status"] = "diagnosed"
    result["operator"] = operator
    result["risk"] = proc.risk
    if live_collected is not None:
        result["evidence_source"] = "live_windows"
        result["mocked"] = False
        result["problem_resolved"] = False
        result["changed_device"] = False
    elif fixture:
        result["evidence_source"] = "fixture"
        result["mocked"] = True
    elif procedure_id == "win.storage.space" and not evidence:
        result["evidence_source"] = "live_windows" if os.name == "nt" else "local_api"
        result["mocked"] = False
    elif evidence:
        result["evidence_source"] = "supplied"
        result["mocked"] = True
    else:
        result["evidence_source"] = "none"
    return result
