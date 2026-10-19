"""Run a fixed Windows PowerShell script. The model cannot supply the command."""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

_SECRET = re.compile(r"(?i)(password|secret|api[_-]?key|authorization)\s*[:=]\s*\S+")
_MAX_OUTPUT = 32_000

SCRIPTS: dict[str, str] = {
    "storage": r"""
$ErrorActionPreference = 'Stop'
$disks = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | Select-Object DeviceID, FileSystem, @{n='Size';e={[int64]$_.Size}}, @{n='FreeSpace';e={[int64]$_.FreeSpace}})
@{ disks = $disks } | ConvertTo-Json -Compress -Depth 3
""",
    "services": r"""
$ErrorActionPreference = 'Continue'
$rows = @(Get-Service -Name Spooler, wuauserv, Winmgmt, Dhcp, Dnscache, EventLog -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType)
@{ services = $rows } | ConvertTo-Json -Compress -Depth 3
""",
    "update_events": r"""
$ErrorActionPreference = 'Continue'
$rows = @(Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WindowsUpdateClient'; StartTime=(Get-Date).AddDays(-14)} -MaxEvents 5 -ErrorAction SilentlyContinue | Select-Object TimeCreated, Id, LevelDisplayName)
@{ events = $rows } | ConvertTo-Json -Compress -Depth 3
""",
    "devices": r"""
$ErrorActionPreference = 'Continue'
$all = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue)
$bad = @($all | Where-Object { $_.Problem -and $_.Problem -ne 'CM_PROB_NONE' } | Select-Object -First 15 FriendlyName, Class, Status, Problem)
@{ present_count = @($all).Count; problems = $bad } | ConvertTo-Json -Compress -Depth 3
""",
    "printers": r"""
$ErrorActionPreference = 'Continue'
$spooler = Get-Service -Name Spooler -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType
$printers = @()
if (Get-Command Get-Printer -ErrorAction SilentlyContinue) {
  $printers = @(Get-Printer -ErrorAction SilentlyContinue | Select-Object -First 20 Name, DriverName, PortName, PrinterStatus, JobCount)
}
$jobs = @()
foreach ($printer in $printers) {
  try {
    $found = @(Get-PrintJob -PrinterName $printer.Name -ErrorAction Stop | Select-Object -First 10 Id, JobStatus, PrinterName)
    $jobs += $found
  } catch {}
}
@{ spooler = $spooler; printers = $printers; jobs = $jobs } | ConvertTo-Json -Compress -Depth 4
""",
    "network": r"""
$ErrorActionPreference = 'Continue'
$addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' } | Select-Object -First 8 InterfaceAlias, IPAddress, PrefixOrigin)
$gateway = $null
try { $gateway = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop | Sort-Object RouteMetric | Select-Object -First 1).NextHop } catch {}
$gatewayOk = $false
if ($gateway) { $gatewayOk = [bool](Test-Connection -ComputerName $gateway -Count 1 -Quiet) }
$dnsOk = $false
try { $null = Resolve-DnsName -Name 'localhost' -ErrorAction Stop; $dnsOk = $true } catch {}
@{ addresses = $addresses; gateway = $gateway; gateway_ok = $gatewayOk; dns_localhost_ok = $dnsOk } | ConvertTo-Json -Compress -Depth 3
""",
    "system_events": r"""
$ErrorActionPreference = 'Continue'
$rows = @(Get-WinEvent -FilterHashtable @{LogName='System'; Level=2; StartTime=(Get-Date).AddHours(-24)} -MaxEvents 8 -ErrorAction SilentlyContinue | Select-Object TimeCreated, Id, ProviderName, LevelDisplayName)
@{ events = $rows } | ConvertTo-Json -Compress -Depth 3
""",
    "startup": r"""
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
@{ last_boot = [string]$os.LastBootUpTime; free_memory_kb = [int64]$os.FreePhysicalMemory; total_memory_kb = [int64]$os.TotalVisibleMemorySize; cpu_load_percent = $cpu.LoadPercentage } | ConvertTo-Json -Compress
""",
}


def powershell_exe() -> str | None:
    if os.name != "nt":
        return None
    root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if os.path.isfile(candidate):
        return candidate
    return None


def redact(text: str) -> str:
    return _SECRET.sub(r"\1=[redacted]", text)[:_MAX_OUTPUT]


def run_argv(argv: list[str], *, timeout: float) -> dict[str, Any]:
    """Run an already-built argument list. No shell expansion."""
    if not argv or not argv[0]:
        return {"ok": False, "status": "tool_missing", "evidence_source": "unavailable", "detail": "No executable was configured.", "timed_out": False}
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "evidence_source": "unavailable", "detail": f"Command exceeded {timeout} seconds.", "timed_out": True}
    except FileNotFoundError:
        return {"ok": False, "status": "tool_missing", "evidence_source": "unavailable", "detail": "The diagnostic tool is not installed.", "timed_out": False}
    except OSError as exc:
        return {"ok": False, "status": "failed", "evidence_source": "unavailable", "detail": type(exc).__name__, "timed_out": False}
    stdout = redact(completed.stdout.decode("utf-8", errors="replace"))
    stderr = redact(completed.stderr.decode("utf-8", errors="replace"))
    return {
        "ok": completed.returncode == 0 and bool(stdout.strip()),
        "status": "completed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr[:1000],
        "timed_out": False,
        "evidence_source": "live_windows",
    }


def parse_json_output(text: str) -> Any:
    raw = text.strip()
    starts = [index for index in (raw.find("{"), raw.find("[")) if index >= 0]
    if not starts:
        raise ValueError("diagnostic output did not contain JSON")
    return json.loads(raw[min(starts):])


def run_script(script_id: str, *, timeout: float = 20) -> dict[str, Any]:
    if script_id not in SCRIPTS:
        raise KeyError(script_id)
    executable = powershell_exe()
    if executable is None:
        return {"ok": False, "status": "tool_missing", "evidence_source": "unavailable", "detail": "Windows PowerShell was not found.", "timed_out": False, "script_id": script_id}
    result = run_argv(
        [executable, "-NoProfile", "-NonInteractive", "-Command", SCRIPTS[script_id]],
        timeout=timeout,
    )
    result["script_id"] = script_id
    if result.get("ok"):
        try:
            result["payload"] = parse_json_output(str(result.get("stdout") or ""))
        except (ValueError, json.JSONDecodeError) as exc:
            result["ok"] = False
            result["status"] = "unreadable"
            result["detail"] = type(exc).__name__
    return result
