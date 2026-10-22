"""Select and run registered Windows procedures.

Elevated and destructive runners do not change this computer. A successful
diagnostic is not reported as a repaired fault.
"""
from __future__ import annotations

import inspect
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


def _plain(value: Any, limit: int) -> str:
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())[:limit]


def _services(evidence: dict[str, Any]) -> dict[str, Any]:
    rows = evidence.get("services") if isinstance(evidence.get("services"), list) else []
    facts = []
    for row in rows[:8]:
        if isinstance(row, dict):
            facts.append(
                f"{_plain(row.get('name') or 'service', 120)} is {_plain(row.get('status') or 'unknown', 40)}."
            )
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
    events = evidence.get("events") if isinstance(evidence.get("events"), list) else []
    if not code and events:
        ids = []
        for row in events[:5]:
            if isinstance(row, dict) and row.get("id") is not None:
                ids.append(_plain(row.get("id"), 12))
        listed = ", ".join(ids) or "none"
        return _unfixed(
            "Windows Update events were read. No update was installed.",
            facts=[f"{len(events)} recent Windows Update event(s). Ids: {listed}."],
            hypotheses=["An event id is evidence. It is not a completed repair and does not authorise a reset."],
            procedure_id="win.update.inspect",
        )
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
    events = evidence.get("events") if isinstance(evidence.get("events"), list) else []
    bits = []
    for row in events[:5]:
        if not isinstance(row, dict):
            continue
        provider = _plain(row.get("provider") or "event", 40)
        event_id = _plain(row.get("id") or "", 12)
        bits.append(f"{provider} id={event_id}")
    listed = "; ".join(bits) if bits else "none"
    return _unfixed(
        "Event evidence recorded. The log was not cleared.",
        facts=[f"{len(events)} event row(s). {listed}."],
        hypotheses=["Event presence is evidence, not a root-cause proof and not approval to format a disk."],
        procedure_id="win.events.recurring",
    )


def _app(evidence: dict[str, Any]) -> dict[str, Any]:
    return _unfixed(
        "Application evidence recorded. No software was reinstalled.",
        facts=[f"{_plain(evidence.get('application') or 'unknown', 80)} fault={_plain(evidence.get('fault') or 'unspecified', 40)}."],
        hypotheses=["A crash module is a clue. It is not approval to reinstall Windows or the application."],
        procedure_id="app.crash.evidence",
    )


def _activation(evidence: dict[str, Any]) -> dict[str, Any]:
    status = _plain(evidence.get("activation_status") or "unknown", 40)
    if "redacted" in status.casefold() or "-" in status and len(status) >= 29:
        status = "redacted"
    return _unfixed(
        "Activation status recorded. No product key was read or changed.",
        facts=[f"Activation status is {status}."],
        hypotheses=["A status string is not proof the licence is valid and does not authorise a key change."],
        procedure_id="win.activation.inspect",
    )


def _usb(evidence: dict[str, Any]) -> dict[str, Any]:
    return _unfixed(
        "USB and peripheral inventory recorded. No driver was installed.",
        facts=[
            f"Device count {evidence.get('device_count')}. Problem count {evidence.get('problem_count')}.",
            f"First device {_plain(evidence.get('device_name') or 'none', 80)}.",
        ],
        hypotheses=["A missing peripheral may need physical reconnection. This check does not install a driver."],
        procedure_id="hw.usb.inspect",
    )


def _wifi(evidence: dict[str, Any]) -> dict[str, Any]:
    return _unfixed(
        "Wi-Fi reading recorded. No wireless profile or password was read.",
        facts=[
            f"Adapter {_plain(evidence.get('adapter_status') or 'unknown', 40)}.",
            f"Radio {_plain(evidence.get('radio') or 'unknown', 40)}.",
            f"SSID {_plain(evidence.get('ssid') or 'none', 64)}.",
        ],
        hypotheses=["Radio state is evidence only. It does not authorise a profile or firewall change."],
        procedure_id="net.wifi.inspect",
    )


def _proxy(evidence: dict[str, Any]) -> dict[str, Any]:
    return _unfixed(
        "Proxy and VPN state recorded. No credential was read and no proxy was changed.",
        facts=[
            f"Proxy {_plain(evidence.get('proxy') or 'unknown', 120)}.",
            f"VPN {_plain(evidence.get('vpn') or 'unknown', 20)}.",
        ],
        hypotheses=["A proxy value is evidence only. It does not authorise disabling a proxy or VPN."],
        procedure_id="net.proxy.inspect",
    )


def _tls(evidence: dict[str, Any]) -> dict[str, Any]:
    return _unfixed(
        "Certificate counts recorded. No certificate or private key was exported.",
        facts=[
            f"Certificate error label is {_plain(evidence.get('certificate_error') or 'none', 80)}.",
            f"Certificates expiring in 30 days: {evidence.get('expiring_count')}.",
        ],
        hypotheses=["A count is evidence. It does not authorise installing or deleting a certificate."],
        procedure_id="net.tls.inspect",
    )


def _browser(evidence: dict[str, Any]) -> dict[str, Any]:
    return _unfixed(
        "Browser presence recorded. The profile was not read or reset.",
        facts=[
            f"Browser {_plain(evidence.get('browser') or 'unknown', 80)}.",
            f"Error label {_plain(evidence.get('error') or 'none', 40)}.",
        ],
        hypotheses=["A browser reading is a clue. It is not approval to reset a profile."],
        procedure_id="app.browser.inspect",
    )


def _permissions(evidence: dict[str, Any]) -> dict[str, Any]:
    return _unfixed(
        "Fixed folder access recorded. ACLs were not changed.",
        facts=[
            f"Labels {_plain(evidence.get('path') or 'none', 80)}.",
            f"Access {_plain(evidence.get('access') or 'unknown', 40)}.",
        ],
        hypotheses=["An access result for a fixed folder is not approval to take ownership."],
        procedure_id="app.permissions.inspect",
    )


def _startup_reading(procedure_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return _unfixed(
        "Performance reading only. No process was stopped.",
        facts=[
            f"Last boot {_plain(evidence.get('last_boot') or 'unknown', 40)}.",
            f"Free memory kb={evidence.get('free_memory_kb')}. Total memory kb={evidence.get('total_memory_kb')}.",
            f"CPU load percent={evidence.get('cpu_load_percent')}.",
        ],
        hypotheses=["A high CPU or low memory reading is a clue, not a repair."],
        procedure_id=procedure_id,
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
    "interpret_activation": _activation,
    "interpret_startup": lambda evidence: _startup_reading("win.startup.inspect", evidence),
    "interpret_services": _services,
    "interpret_performance": lambda evidence: _startup_reading("win.performance.inspect", evidence),
    "interpret_usb": _usb,
    "interpret_wifi": _wifi,
    "interpret_proxy": _proxy,
    "interpret_tls": _tls,
    "interpret_browser": _browser,
    "interpret_permissions": _permissions,
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
    if procedure_id == "win.activation.inspect":
        return {
            "activation_status": live.get("activation_status") or "unknown",
            "license_name": live.get("license_name") or "",
        }
    if procedure_id == "hw.usb.inspect":
        devices = live.get("devices") if isinstance(live.get("devices"), list) else []
        first = devices[0] if devices and isinstance(devices[0], dict) else {}
        return {
            "device_name": first.get("name") or "none",
            "device_count": live.get("device_count"),
            "problem_count": live.get("problem_count"),
        }
    if procedure_id == "net.wifi.inspect":
        return {
            "ssid": live.get("ssid") or "",
            "radio": live.get("radio") or "unknown",
            "adapter_status": live.get("adapter_status") or "unknown",
        }
    if procedure_id == "net.proxy.inspect":
        return {
            "proxy": live.get("proxy") or "unknown",
            "vpn": live.get("vpn") or "none",
        }
    if procedure_id == "net.tls.inspect":
        return {
            "certificate_error": live.get("certificate_error") or "none",
            "expiring_count": live.get("user_my_expiring_30d"),
        }
    if procedure_id == "app.browser.inspect":
        return {
            "browser": live.get("browser") or "none",
            "error": live.get("error") or "none",
        }
    if procedure_id == "app.permissions.inspect":
        return {
            "path": live.get("path") or "",
            "access": live.get("access") or "unknown",
        }
    if procedure_id == "app.crash.evidence":
        return {
            "application": live.get("application") or "none",
            "fault": live.get("fault") or "none",
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


def _invoke_collector(collector: Any, procedure_id: str, timeout: float) -> dict[str, Any]:
    parameters = inspect.signature(collector.collect).parameters
    if "timeout" in parameters:
        result = collector.collect(procedure_id, timeout=timeout)
    else:
        result = collector.collect(procedure_id)
    if not isinstance(result, dict):
        return {
            "ok": False,
            "status": "unreadable",
            "evidence_source": "unavailable",
            "detail": "Collector returned no evidence object.",
        }
    return result


def execute(
    procedure_id: str,
    *,
    evidence: dict[str, Any] | None = None,
    fixture: str | None = None,
    approval_id: str | None = None,
    operator: str = "operator",
    provider: Any = None,
    script_timeout: float = 18,
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
    if not evidence and not fixture and proc.runner != "local_disk":
        from .providers import LIVE_PROCEDURES, LiveWindowsProvider

        if procedure_id in LIVE_PROCEDURES and (provider is not None or os.name == "nt"):
            collector = provider if provider is not None else LiveWindowsProvider()
            live_collected = _invoke_collector(collector, procedure_id, script_timeout)
            if live_collected.get("evidence_source") != "live_windows" or not live_collected.get("ok"):
                timed_out = bool(live_collected.get("timed_out"))
                return {
                    "procedure_id": proc.procedure_id,
                    "executed": False,
                    "changed_device": False,
                    "problem_resolved": False,
                    "status": "timeout" if timed_out else str(live_collected.get("status") or "unavailable"),
                    "operator": operator,
                    "mocked": False,
                    "evidence_source": str(live_collected.get("evidence_source") or "unavailable"),
                    "detail": _plain(
                        live_collected.get("detail") or "The live collector did not return evidence. No repair was run.",
                        300,
                    ),
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
