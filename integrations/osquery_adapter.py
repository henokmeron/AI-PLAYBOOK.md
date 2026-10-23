"""Optional osquery adapter for diagnostics.

**Founder approval: PENDING**

This module integrates osquery SQL queries into the existing diagnostics path.
Only enabled when osqueryi.exe is installed and Founder approves the dependency.
Falls back to PowerShell collectors (windows_repair/providers.py) when unavailable.

License: osquery is Apache-2.0 or GPL-2.0 (dual-licensed)
Version: 5.13.1 recommended (as of 2026-10)
Download: https://osquery.io/downloads/official/5.13.1
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def osquery_available() -> bool:
    """Check if osqueryi.exe or osqueryd is installed and in PATH.
    
    Returns False until Founder approves osquery as a dependency.
    """
    if os.environ.get("OSQUERY_APPROVED") != "true":
        return False
    
    return shutil.which("osqueryi") is not None or shutil.which("osqueryi.exe") is not None


def query(sql: str, *, timeout: float = 10) -> list[dict[str, Any]]:
    """Run osquery SQL and return JSON results.
    
    Args:
        sql: SQL query string
        timeout: Query timeout in seconds
    
    Returns:
        List of result rows as dictionaries
    
    Raises:
        RuntimeError: If osquery is not available or query fails
    """
    if not osquery_available():
        raise RuntimeError("osquery is not available or not approved by Founder")
    
    osqueryi = shutil.which("osqueryi") or shutil.which("osqueryi.exe")
    if not osqueryi:
        raise RuntimeError("osqueryi executable not found in PATH")
    
    try:
        result = subprocess.run(
            [osqueryi, "--json", sql],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"osquery timeout after {timeout}s") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"osquery failed: {exc.stderr}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("osqueryi executable not found") from exc
    
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"osquery returned invalid JSON: {result.stdout[:200]}") from exc
    
    if not isinstance(rows, list):
        raise RuntimeError(f"osquery returned non-list: {type(rows)}")
    
    return rows


_QUERY_MAP = {
    "win.storage.space": """
        SELECT device_id, type, blocks_size, blocks_available, blocks * blocks_size AS total_bytes
        FROM mounts
        WHERE device_id LIKE 'C:%'
    """,
    "win.services.inspect": """
        SELECT name, display_name, status, start_type
        FROM services
        WHERE start_type IN ('AUTO_START', 'DEMAND_START')
        ORDER BY name
    """,
    "win.update.inspect": """
        SELECT * FROM windows_update_history
        ORDER BY date DESC
        LIMIT 20
    """,
    "hw.devices.inventory": """
        SELECT name, manufacturer, class, problem
        FROM pnp_device_properties
        WHERE problem != 'None'
    """,
    "net.diagnose": """
        SELECT interface, address, mask, type
        FROM interface_addresses
        WHERE interface NOT LIKE 'Loopback%'
    """,
    "print.diagnose": """
        SELECT name, status, start_type
        FROM services
        WHERE name = 'Spooler'
    """,
}


def collect_diagnostics(procedure_id: str) -> dict[str, Any]:
    """Collect diagnostics using osquery instead of PowerShell.
    
    Args:
        procedure_id: Registered procedure ID (e.g., "win.storage.space")
    
    Returns:
        Diagnostic result matching existing schema from providers.py
    
    Raises:
        RuntimeError: If osquery is not available or query fails
        KeyError: If procedure_id has no osquery mapping
    """
    if not osquery_available():
        raise RuntimeError("osquery is not available; use PowerShell collectors as fallback")
    
    if procedure_id not in _QUERY_MAP:
        raise KeyError(f"No osquery mapping for procedure_id: {procedure_id}")
    
    sql = _QUERY_MAP[procedure_id]
    rows = query(sql)
    
    return _normalize_result(procedure_id, rows)


def _normalize_result(procedure_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Map osquery columns to existing diagnostic schema from providers.py.
    
    Keeps backward compatibility with PowerShell collector output.
    """
    base = {
        "procedure_id": procedure_id,
        "evidence_source": "osquery",
        "ok": True,
        "status": "collected",
        "collected_at_unix": int(__import__("time").time()),
    }
    
    if procedure_id == "win.storage.space":
        base["disks"] = [
            {
                "device": row.get("device_id"),
                "type": row.get("type"),
                "size": row.get("total_bytes"),
                "free": row.get("blocks_available"),
            }
            for row in rows
        ]
        base["detail"] = f"disks={len(rows)}"
        return base
    
    if procedure_id == "win.services.inspect":
        base["services"] = [
            {
                "name": row.get("name"),
                "display_name": row.get("display_name"),
                "status": row.get("status"),
                "start_type": row.get("start_type"),
            }
            for row in rows
        ]
        base["detail"] = f"services={len(rows)}"
        return base
    
    if procedure_id == "win.update.inspect":
        base["events"] = [
            {
                "id": row.get("operation"),
                "date": row.get("date"),
                "title": row.get("title"),
            }
            for row in rows
        ]
        base["detail"] = f"updates={len(rows)}"
        return base
    
    if procedure_id == "hw.devices.inventory":
        base["devices"] = [
            {
                "name": row.get("name"),
                "manufacturer": row.get("manufacturer"),
                "class": row.get("class"),
                "problem": row.get("problem"),
            }
            for row in rows
        ]
        base["present_count"] = len(rows)
        base["detail"] = f"problem_devices={len([r for r in rows if r.get('problem') != 'None'])}"
        return base
    
    if procedure_id == "net.diagnose":
        base["addresses"] = [
            {
                "interface": row.get("interface"),
                "address": row.get("address"),
                "mask": row.get("mask"),
                "type": row.get("type"),
            }
            for row in rows
        ]
        base["detail"] = f"interfaces={len(rows)}"
        return base
    
    if procedure_id == "print.diagnose":
        spooler = rows[0] if rows else {}
        base["spooler"] = spooler.get("status", "unknown")
        base["detail"] = f"spooler={base['spooler']}"
        return base
    
    base["detail"] = f"rows={len(rows)}"
    return base


def status() -> dict[str, Any]:
    """Return osquery availability and version info."""
    available = osquery_available()
    
    if not available:
        approval = os.environ.get("OSQUERY_APPROVED") == "true"
        return {
            "available": False,
            "founder_approved": approval,
            "reason": "Founder approval pending" if not approval else "osqueryi not in PATH",
            "fallback": "PowerShell collectors",
        }
    
    osqueryi = shutil.which("osqueryi") or shutil.which("osqueryi.exe")
    version = "unknown"
    
    try:
        result = subprocess.run(
            [osqueryi, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        version = result.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        pass
    
    return {
        "available": True,
        "founder_approved": True,
        "version": version,
        "executable": osqueryi,
        "supported_procedures": list(_QUERY_MAP.keys()),
    }
