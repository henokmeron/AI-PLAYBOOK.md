"""Diagnostic providers.

Live results come from registered PowerShell scripts. Fixture results are
labelled fixture and are not described as a live computer.
"""
from __future__ import annotations

import re
import time
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
    "win.activation.inspect": "activation",
    "hw.usb.inspect": "usb",
    "net.wifi.inspect": "wifi",
    "net.proxy.inspect": "proxy",
    "net.tls.inspect": "tls",
    "app.browser.inspect": "browser",
    "app.permissions.inspect": "permissions",
    "app.crash.evidence": "crashes",
    "hw.identity.inspect": "hardware_identity",
}

_KEY_SHAPE = re.compile(r"(?i)\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b")
_USERINFO = re.compile(r"(?i)[^/\s:@]+:[^/\s@]+@")
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)
_VPN_STATES = {"none", "present", "connected"}


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


def _safe_text(value: Any, limit: int = 80) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    text = _PEM.sub("[redacted]", text)
    text = _KEY_SHAPE.sub("[redacted]", text)
    text = _USERINFO.sub("", text)
    return text[:limit]


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


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
    if procedure_id == "win.activation.inspect":
        base["activation_status"] = _safe_text(body.get("activation_status") or "unknown", 40)
        base["license_name"] = _safe_text(body.get("license_name") or "", 80)
        return base
    if procedure_id == "hw.usb.inspect":
        devices = []
        for row in _rows(body.get("devices")):
            if isinstance(row, dict):
                devices.append({
                    "name": _safe_text(row.get("FriendlyName") or row.get("name") or "", 80),
                    "class": _safe_text(row.get("Class") or row.get("class") or "", 40),
                    "status": _safe_text(row.get("Status") or row.get("status") or "", 40),
                    "problem": _safe_text(row.get("Problem") or row.get("problem") or "", 40),
                })
        base["device_count"] = _count(body.get("device_count"))
        base["problem_count"] = _count(body.get("problem_count"))
        base["devices"] = devices[:12]
        return base
    if procedure_id == "net.wifi.inspect":
        signal = body.get("signal_percent")
        base["adapter_status"] = _safe_text(body.get("adapter_status") or "unknown", 40)
        base["ssid"] = _safe_text(body.get("ssid") or "", 64)
        base["radio"] = _safe_text(body.get("radio") or "unknown", 40)
        base["signal_percent"] = signal if isinstance(signal, int) and not isinstance(signal, bool) else None
        return base
    if procedure_id == "net.proxy.inspect":
        vpn = str(body.get("vpn") or "none").casefold()
        base["proxy"] = _safe_text(body.get("proxy") or "unknown", 120)
        base["vpn"] = vpn if vpn in _VPN_STATES else "unknown"
        base["winhttp"] = _safe_text(body.get("winhttp") or "unknown", 120)
        return base
    if procedure_id == "net.tls.inspect":
        ids = []
        for item in _rows(body.get("schannel_ids")):
            if isinstance(item, int) and not isinstance(item, bool):
                ids.append(item)
        base["certificate_error"] = _safe_text(body.get("certificate_error") or "none", 80)
        base["user_my_count"] = _count(body.get("user_my_count"))
        base["user_my_expired"] = _count(body.get("user_my_expired"))
        base["user_my_expiring_30d"] = _count(body.get("user_my_expiring_30d"))
        base["user_private_key_count"] = _count(body.get("user_private_key_count"))
        base["machine_root_count"] = _count(body.get("machine_root_count"))
        base["schannel_error_count"] = _count(body.get("schannel_error_count"))
        base["schannel_ids"] = ids[:8]
        return base
    if procedure_id == "app.browser.inspect":
        installed = []
        for row in _rows(body.get("installed")):
            if isinstance(row, dict):
                installed.append({
                    "name": _safe_text(row.get("name") or "", 40),
                    "version": _safe_text(row.get("version") or "", 40),
                })
        base["browser"] = _safe_text(body.get("browser") or "none", 80)
        base["default_progid"] = _safe_text(body.get("default_progid") or "unknown", 80)
        base["error"] = _safe_text(body.get("error") or "none", 40)
        base["installed"] = installed[:6]
        return base
    if procedure_id == "app.permissions.inspect":
        checks = []
        for row in _rows(body.get("checks")):
            if isinstance(row, dict):
                checks.append({
                    "label": _safe_text(row.get("label") or "", 40),
                    "exists": bool(row.get("exists")),
                    "access": _safe_text(row.get("access") or "unknown", 20),
                })
        base["path"] = _safe_text(body.get("path") or "", 80)
        base["access"] = _safe_text(body.get("access") or "unknown", 20)
        base["checks"] = checks[:6]
        return base
    if procedure_id == "app.crash.evidence":
        events = []
        for row in _rows(body.get("events")):
            if isinstance(row, dict):
                events.append({
                    "id": row.get("Id") if row.get("Id") is not None else row.get("id"),
                    "provider": _safe_text(row.get("ProviderName") or row.get("provider") or "", 80),
                    "level": _safe_text(row.get("LevelDisplayName") or row.get("level") or "", 40),
                    "time": _safe_text(row.get("TimeCreated") or row.get("time") or "", 40),
                })
        base["application"] = _safe_text(body.get("application") or "none", 80)
        base["fault"] = _safe_text(body.get("fault") or "none", 40)
        base["event_count"] = _count(body.get("event_count"))
        base["events"] = events[:8]
        return base
    if procedure_id == "hw.identity.inspect":
        from .hardware_inventory import assess_hardware_identity

        reading = assess_hardware_identity(body)
        base.update(reading)
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

    def collect(self, procedure_id: str, timeout: float = 18) -> dict[str, Any]:
        collected_at = int(time.time())
        script_id = LIVE_PROCEDURES.get(procedure_id)
        if script_id is None:
            return {
                "procedure_id": procedure_id,
                "evidence_source": "unavailable",
                "mocked": False,
                "ok": False,
                "status": "not_registered",
                "collected_at_unix": collected_at,
                "detail": "This procedure has no live read-only collector.",
            }
        raw = run_script(script_id, timeout=timeout)
        if procedure_id == "hw.identity.inspect":
            from .hardware_inventory import reading_from_script_result

            return reading_from_script_result(raw, collected_at)
        if not raw.get("ok"):
            return {
                "procedure_id": procedure_id,
                "evidence_source": raw.get("evidence_source") or "unavailable",
                "mocked": False,
                "ok": False,
                "status": raw.get("status") or "failed",
                "timed_out": bool(raw.get("timed_out")),
                "collected_at_unix": collected_at,
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
                "collected_at_unix": collected_at,
                "detail": type(exc).__name__,
            }
        evidence["ok"] = True
        evidence["status"] = "collected"
        evidence["problem_resolved"] = False
        evidence["collected_at_unix"] = collected_at
        return evidence
