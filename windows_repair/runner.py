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
    "activation": r"""
$ErrorActionPreference = 'Continue'
$map = @{0='Unlicensed';1='Licensed';2='OOBGrace';3='OOTGrace';4='NonGenuineGrace';5='Notification';6='ExtendedGrace'}
$row = Get-CimInstance -Query "SELECT Name, LicenseStatus FROM SoftwareLicensingProduct WHERE ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL" -ErrorAction SilentlyContinue |
  Select-Object -First 1 Name, LicenseStatus
$status = 'unknown'
$name = ''
if ($row) {
  $name = [string]$row.Name
  if ($name.Length -gt 80) { $name = $name.Substring(0, 80) }
  $code = 0
  try { $code = [int]$row.LicenseStatus } catch { $code = -1 }
  if ($map.ContainsKey($code)) { $status = $map[$code] } else { $status = 'other' }
}
@{ activation_status = $status; license_name = $name } | ConvertTo-Json -Compress
""",
    "usb": r"""
$ErrorActionPreference = 'Continue'
$classes = @('USB','Camera','MEDIA','AudioEndpoint','Image','HIDClass','Bluetooth')
$all = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $classes -contains $_.Class })
$sample = @($all | Select-Object -First 12 FriendlyName, Class, Status, Problem)
$problems = @($all | Where-Object { $_.Problem -and $_.Problem -ne 'CM_PROB_NONE' -and $_.Status -ne 'OK' })
@{ device_count = @($all).Count; problem_count = @($problems).Count; devices = $sample } | ConvertTo-Json -Compress -Depth 3
""",
    "wifi": r"""
$ErrorActionPreference = 'Continue'
$adapter = Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.NdisPhysicalMedium -eq 9 -or $_.Name -match 'Wi-Fi|WLAN|Wireless' } | Select-Object -First 1
$adapterStatus = if ($adapter) { [string]$adapter.Status } else { 'absent' }
$ssid = ''
$radio = 'unknown'
$signal = $null
try {
  foreach ($line in @(& netsh.exe wlan show interfaces)) {
    $text = [string]$line
    if ($text -match '^\s*SSID\s*:\s*(.*)$' -and $text -notmatch 'BSSID') { if (-not $ssid) { $ssid = $Matches[1].Trim() } }
    elseif ($text -match '^\s*Radio status\s*:\s*(.*)$') { $radio = $Matches[1].Trim() }
    elseif ($text -match '^\s*State\s*:\s*(.*)$' -and $radio -eq 'unknown') { $radio = $Matches[1].Trim() }
    elseif ($text -match '^\s*Signal\s*:\s*(\d+)') { $signal = [int]$Matches[1] }
  }
} catch {}
if ($ssid.Length -gt 64) { $ssid = $ssid.Substring(0, 64) }
@{ adapter_status = $adapterStatus; ssid = $ssid; radio = $radio; signal_percent = $signal } | ConvertTo-Json -Compress
""",
    "proxy": r"""
$ErrorActionPreference = 'Continue'
function Strip-UserInfo([string]$value) {
  if (-not $value) { return '' }
  $clean = [regex]::Replace($value, '(?i)[^/\s:@]+:[^/\s@]+@', '')
  if ($clean -match '(?i)password|secret|key content') { return 'redacted' }
  if ($clean.Length -gt 120) { $clean = $clean.Substring(0, 120) }
  return $clean
}
$enable = $false
$server = ''
try {
  $reg = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
  if ($null -ne $reg.ProxyEnable) { $enable = [bool]$reg.ProxyEnable }
  $server = Strip-UserInfo ([string]$reg.ProxyServer)
} catch {}
$winhttp = 'unknown'
try {
  $line = @(& netsh.exe winhttp show proxy | Where-Object { $_ -match 'Proxy Server' } | Select-Object -First 1)
  if ($line) {
    $part = ([string]$line) -replace '^.*:\s*', ''
    if ($part -match 'Direct access') { $winhttp = 'direct' } else { $winhttp = Strip-UserInfo $part.Trim() }
  }
} catch {}
$vpn = 'none'
try {
  if (Get-Command Get-VpnConnection -ErrorAction SilentlyContinue) {
    $conns = @(Get-VpnConnection -ErrorAction SilentlyContinue | Select-Object -First 5 Name, ConnectionStatus)
    $up = @($conns | Where-Object { [string]$_.ConnectionStatus -eq 'Connected' })
    if ($up.Count -gt 0) { $vpn = 'connected' } elseif ($conns.Count -gt 0) { $vpn = 'present' }
  }
} catch {}
$proxy = 'direct'
if ($enable -and $server) { $proxy = 'user-proxy:' + $server }
elseif ($enable) { $proxy = 'enabled' }
elseif ($winhttp -and $winhttp -ne 'direct' -and $winhttp -ne 'unknown' -and $winhttp -ne '') { $proxy = 'winhttp:' + $winhttp }
@{ proxy = $proxy; vpn = $vpn; winhttp = $winhttp } | ConvertTo-Json -Compress
""",
    "tls": r"""
$ErrorActionPreference = 'Continue'
function Count-Store([string]$path) {
  $items = @(Get-ChildItem -Path $path -ErrorAction SilentlyContinue)
  $now = Get-Date
  $soon = $now.AddDays(30)
  $expired = @($items | Where-Object { $_.NotAfter -and $_.NotAfter -lt $now }).Count
  $expiring = @($items | Where-Object { $_.NotAfter -and $_.NotAfter -ge $now -and $_.NotAfter -le $soon }).Count
  $withKey = @($items | Where-Object { $_.HasPrivateKey }).Count
  return @{ count = @($items).Count; expired = $expired; expiring_30d = $expiring; private_key_count = $withKey }
}
$user = Count-Store 'Cert:\CurrentUser\My'
$root = Count-Store 'Cert:\LocalMachine\Root'
$schannel = 0
$ids = @()
try {
  $events = @(Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Schannel'; Level=2; StartTime=(Get-Date).AddDays(-7)} -MaxEvents 8 -ErrorAction SilentlyContinue)
  $schannel = @($events).Count
  $ids = @($events | ForEach-Object { [int]$_.Id } | Select-Object -First 8)
} catch {}
$errorLabel = 'none'
if ($schannel -gt 0) { $errorLabel = "schannel_errors=$schannel" }
elseif ($user.expired -gt 0) { $errorLabel = "user_certs_expired=$($user.expired)" }
@{ certificate_error = $errorLabel; user_my_count = $user.count; user_my_expired = $user.expired; user_my_expiring_30d = $user.expiring_30d; user_private_key_count = $user.private_key_count; machine_root_count = $root.count; schannel_error_count = $schannel; schannel_ids = $ids } | ConvertTo-Json -Compress -Depth 3
""",
    "browser": r"""
$ErrorActionPreference = 'Continue'
$candidates = @(
  @{ name = 'Microsoft Edge'; paths = @("$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe", "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe") },
  @{ name = 'Google Chrome'; paths = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") },
  @{ name = 'Mozilla Firefox'; paths = @("$env:ProgramFiles\Mozilla Firefox\firefox.exe", "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe") }
)
$found = @()
foreach ($item in $candidates) {
  $hit = $item.paths | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
  if ($hit) {
    $ver = ''
    try { $ver = [string](Get-Item -LiteralPath $hit).VersionInfo.FileVersion } catch {}
    if ($ver.Length -gt 40) { $ver = $ver.Substring(0, 40) }
    $found += @{ name = $item.name; version = $ver }
  }
}
$default = 'unknown'
try {
  $choice = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice' -ErrorAction Stop
  $default = [string]$choice.ProgId
  if ($default.Length -gt 80) { $default = $default.Substring(0, 80) }
} catch {}
$names = if ($found.Count) { ($found | ForEach-Object { $_.name }) -join ', ' } else { 'none' }
$errorLabel = if ($found.Count -eq 0) { 'no_known_browser' } else { 'none' }
@{ browser = $names; default_progid = $default; error = $errorLabel; installed = $found } | ConvertTo-Json -Compress -Depth 3
""",
    "permissions": r"""
$ErrorActionPreference = 'Continue'
function Test-Dir([string]$label, [string]$path) {
  $exists = $false
  $access = 'missing'
  if ($path -and (Test-Path -LiteralPath $path -PathType Container)) {
    $exists = $true
    try { $null = [System.IO.Directory]::GetFileSystemEntries($path); $access = 'readable' } catch { $access = 'denied' }
  }
  return @{ label = $label; exists = $exists; access = $access }
}
$rows = @(
  (Test-Dir 'user_profile' $env:USERPROFILE),
  (Test-Dir 'temp' $env:TEMP),
  (Test-Dir 'local_appdata' $env:LOCALAPPDATA)
)
$denied = @($rows | Where-Object { $_.access -eq 'denied' }).Count
$readable = @($rows | Where-Object { $_.access -eq 'readable' }).Count
$summary = if ($denied -gt 0) { 'denied' } elseif ($readable -eq $rows.Count) { 'readable' } else { 'partial' }
@{ path = (($rows | ForEach-Object { $_.label }) -join ','); access = $summary; checks = $rows } | ConvertTo-Json -Compress -Depth 4
""",
    "crashes": r"""
$ErrorActionPreference = 'Continue'
$rows = @(Get-WinEvent -FilterHashtable @{LogName='Application'; Level=2; StartTime=(Get-Date).AddDays(-7)} -MaxEvents 8 -ErrorAction SilentlyContinue | Select-Object TimeCreated, Id, ProviderName, LevelDisplayName)
$first = $rows | Select-Object -First 1
$app = if ($first) { [string]$first.ProviderName } else { 'none' }
$fault = if ($first) { "event_id=$($first.Id)" } else { 'none' }
if ($app.Length -gt 80) { $app = $app.Substring(0, 80) }
@{ application = $app; fault = $fault; event_count = @($rows).Count; events = $rows } | ConvertTo-Json -Compress -Depth 3
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
