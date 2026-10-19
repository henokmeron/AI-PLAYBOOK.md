"""Diagnostic providers.

Live results come from registered PowerShell scripts. Fixture results are
labelled fixture and are not described as a live computer.
"""
from __future__ import annotations

from typing import Any

from .catalogue import FIXTURES
from .runner import run_script

LIVE_PROCEDURES = {
    "win.storage.space": "storage",
    "win.services.inspect": "services",
    "win.update.inspect": "update_events",
    "hw.devices.inventory": "devices",
    "print.diagnose": "printers",
    "net.diagnose": "network",
    "win.events.recurring": "system_events",
    "win.startup.inspect": "startup",
    "win.performance.inspect": "startup",
}


def _rows(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _status_name(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, int):
        return {1: "Stopped", 4: "Running"}.get(value, str(value))
    return str(value)


def normalise_live(procedure_id: str, payload: Any) -> dict[str, Any]:
    """Turn registered-script JSON into a small evidence object."""
    body = payload if isinstance(payload, dict) else {}
    base = {"procedure_id": procedure_id, "evidence_source": "live_windows", "mocked": False}
    if procedure_id == "win.storage.space":
        disks = []
        for row in _rows(body.get("disks")):
            if isinstance(row, dict):
                disks.append({
                    "device": row.get("DeviceID"),
                    "file_system": row.get("FileSystem"),
                    "size": row.get("Size"),
                    "free": row.get("FreeSpace"),
                })
        base["disks"] = disks
        return base
    if procedure_id == "win.services.inspect":
        base["services"] = [
            {"name": row.get("Name"), "status": _status_name(row.get("Status")), "start": _status_name(row.get("StartType"))}
            for row in _rows(body.get("services")) if isinstance(row, dict)
        ]
        return base
    if procedure_id == "win.update.inspect":
        base["events"] = [
            {"id": row.get("Id"), "level": row.get("LevelDisplayName"), "time": str(row.get("TimeCreated") or "")[:40]}
            for row in _rows(body.get("events")) if isinstance(row, dict)
        ]
        return base
    if procedure_id == "hw.devices.inventory":
        base["present_count"] = body.get("present_count")
        base["problems"] = [
            {"name": row.get("FriendlyName"), "class": row.get("Class"), "status": row.get("Status"), "problem": row.get("Problem")}
            for row in _rows(body.get("problems")) if isinstance(row, dict)
        ]
        return base
    if procedure_id == "print.diagnose":
        spooler = body.get("spooler") if isinstance(body.get("spooler"), dict) else {}
        base["spooler"] = _status_name(spooler.get("Status"))
        base["printers"] = [
            {
                "name": row.get("Name"),
                "driver": row.get("DriverName"),
                "port": row.get("PortName"),
                "status": row.get("PrinterStatus"),
                "job_count": row.get("JobCount"),
            }
            for row in _rows(body.get("printers")) if isinstance(row, dict)
        ]
        base["jobs"] = [
            {"id": row.get("Id"), "printer": row.get("PrinterName"), "status": _status_name(row.get("JobStatus"))}
            for row in _rows(body.get("jobs")) if isinstance(row, dict)
        ]
        return base
    if procedure_id == "net.diagnose":
        base["addresses"] = [
            {"name": row.get("InterfaceAlias"), "ip": row.get("IPAddress"), "origin": _status_name(row.get("PrefixOrigin"))}
            for row in _rows(body.get("addresses")) if isinstance(row, dict)
        ]
        base["gateway"] = body.get("gateway")
        base["gateway_ok"] = body.get("gateway_ok")
        base["dns_localhost_ok"] = body.get("dns_localhost_ok")
        return base
    if procedure_id == "win.events.recurring":
        base["events"] = [
            {"id": row.get("Id"), "provider": row.get("ProviderName"), "level": row.get("LevelDisplayName"), "time": str(row.get("TimeCreated") or "")[:40]}
            for row in _rows(body.get("events")) if isinstance(row, dict)
        ]
        return base
    if procedure_id in {"win.startup.inspect", "win.performance.inspect"}:
        base["last_boot"] = str(body.get("last_boot") or "")[:40]
        base["free_memory_kb"] = body.get("free_memory_kb")
        base["total_memory_kb"] = body.get("total_memory_kb")
        base["cpu_load_percent"] = body.get("cpu_load_percent")
        return base
    raise KeyError(procedure_id)


class FixtureProvider:
    """Returns catalogue fixtures. evidence_source is always fixture."""

    def collect(self, procedure_id: str, fixture: str | None = None) -> dict[str, Any]:
        name = fixture or {
            "print.diagnose": "printer_stuck_usb",
            "net.diagnose": "network_dns",
            "hw.devices.inventory": "driver_code_28",
        }.get(procedure_id)
        payload = dict(FIXTURES.get(name or "", {}))
        payload["procedure_id"] = procedure_id
        payload["evidence_source"] = "fixture"
        payload["fixture"] = name
        payload["mocked"] = True
        return payload


class LiveWindowsProvider:
    """Collects one registered read-only procedure from this Windows computer."""

    def collect(self, procedure_id: str) -> dict[str, Any]:
        script_id = LIVE_PROCEDURES.get(procedure_id)
        if script_id is None:
            return {
                "procedure_id": procedure_id,
                "evidence_source": "unavailable",
                "mocked": False,
                "ok": False,
                "status": "not_registered",
                "detail": "This procedure has no live read-only collector.",
            }
        raw = run_script(script_id)
        if not raw.get("ok"):
            return {
                "procedure_id": procedure_id,
                "evidence_source": raw.get("evidence_source") or "unavailable",
                "mocked": False,
                "ok": False,
                "status": raw.get("status") or "failed",
                "timed_out": bool(raw.get("timed_out")),
                "detail": str(raw.get("detail") or raw.get("stderr") or "The live diagnostic failed.")[:300],
            }
        try:
            evidence = normalise_live(procedure_id, raw.get("payload"))
        except (KeyError, TypeError, ValueError) as exc:
            return {
                "procedure_id": procedure_id,
                "evidence_source": "unavailable",
                "mocked": False,
                "ok": False,
                "status": "unreadable",
                "detail": type(exc).__name__,
            }
        evidence["ok"] = True
        evidence["status"] = "collected"
        evidence["problem_resolved"] = False
        return evidence
