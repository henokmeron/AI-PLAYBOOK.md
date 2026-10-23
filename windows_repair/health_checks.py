"""Read-only Windows health checks for the endpoint worker.

These checks report. They do not restart a service, clear a printer queue,
download a driver, install software, reboot the computer, delete a file, or
write the registry. A synthetic fixture is not a live success. A missing data
source is unavailable, unsupported, or permission-denied, and is not ok.

``ok`` means the read succeeded. A pending reboot, a stopped automatic
service, a deep queue, an unhealthy disk, a problem device, or a non-zero
error count is a finding inside that report.
"""
from __future__ import annotations

import re
from typing import Any, Callable

HEALTH_PROCEDURE_IDS = (
    "win.reboot.pending",
    "win.services.failed",
    "print.queue.depth",
    "win.storage.health",
    "hw.devices.problems",
    "win.events.recent",
)
# Keep equal to integrations.endpoint.CHECK_SUMMARY_LIMIT. Fifteen summaries
# at this length still fit in the 4096-byte console check-in.
HEALTH_SUMMARY_LIMIT = 100
SYNTHETIC = "synthetic"
_CLOSED = frozenset({"unavailable", "unsupported", "permission-denied"})
_STORAGE_SOURCES = frozenset({"physical_disk", "storage_reliability"})
_SECTION = {
    "win.reboot.pending": "reboot",
    "win.services.failed": "services",
    "print.queue.depth": "queues",
    "win.storage.health": "storage",
    "hw.devices.problems": "devices",
    "win.events.recent": "errors",
}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SECRETISH = re.compile(
    r"(?i)(password|secret|api[_-]?key|authorization|bearer|token\s*[:=]|serialnumber|serial\s*number)"
)
_COMMANDISH = re.compile(r"(?i)(powershell|cmd(?:\.exe)?\s+/|invoke-expression|\.\./|\\\\)")
_PRODUCT_KEY = re.compile(r"\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b")
_SERVICE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,39}\Z")
_SERVICE_STATES = {
    1: "Stopped",
    2: "StartPending",
    3: "StopPending",
    4: "Running",
    5: "ContinuePending",
    6: "PausePending",
    7: "Paused",
}
_STATE_NAMES = {
    "stopped": "Stopped",
    "startpending": "StartPending",
    "stoppending": "StopPending",
    "running": "Running",
    "continuepending": "ContinuePending",
    "pausepending": "PausePending",
    "paused": "Paused",
    "failed": "Failed",
}
_SKIP = object()

FIXED_SCRIPT = r"""
$ErrorActionPreference = 'Continue'
function Classify([string]$message) {
  $text = $message.ToLowerInvariant()
  if ($text -match 'access is denied|unauthorized|0x80041003|privilege') { return 'permission-denied' }
  if ($text -match 'not recognized|invalid class|not supported') { return 'unsupported' }
  return 'unavailable'
}
function Clip([string]$value, [int]$limit) {
  if (-not $value) { return '' }
  $clean = ([regex]::Replace($value, '[\x00-\x1f\x7f]', ' ')).Trim()
  if ($clean.Length -gt $limit) { return $clean.Substring(0, $limit) }
  return $clean
}

$rebootStatus = 'collected'
$pending = $false
$sources = 0
$denied = $false
foreach ($path in @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending',
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
)) {
  try {
    if (Test-Path -LiteralPath $path) { $pending = $true }
    $sources += 1
  } catch {
    if ((Classify $_.Exception.Message) -eq 'permission-denied') { $denied = $true }
  }
}
try {
  $item = Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name 'PendingFileRenameOperations' -ErrorAction Stop
  $sources += 1
  if ($item.PendingFileRenameOperations) { $pending = $true }
} catch {
  $message = [string]$_.Exception.Message
  $id = [string]$_.FullyQualifiedErrorId
  if ($id -match 'PropertyNotFound' -or $message -match 'does not exist') {
    $sources += 1
  } elseif ((Classify $message) -eq 'permission-denied') {
    $denied = $true
  }
}
if ($sources -lt 1) {
  $pending = $false
  if ($denied) { $rebootStatus = 'permission-denied' } else { $rebootStatus = 'unavailable' }
}

$serviceStatus = 'collected'
$failed = @()
$failedCount = 0
try {
  $all = @(Get-Service -ErrorAction Stop | Where-Object {
    ($_.StartType -eq 'Automatic' -or $_.StartType -eq 'AutomaticDelayedStart') -and $_.Status -ne 'Running'
  })
  $failedCount = @($all).Count
  foreach ($row in @($all | Select-Object -First 8)) {
    $failed += @{ name = (Clip ([string]$row.Name) 40); state = (Clip ([string]$row.Status) 20) }
  }
} catch {
  $serviceStatus = Classify $_.Exception.Message
  $failed = @()
  $failedCount = 0
}

$queueStatus = 'collected'
$printers = @()
$queueDepth = 0
try {
  if (-not (Get-Command Get-Printer -ErrorAction SilentlyContinue)) {
    $queueStatus = 'unsupported'
  } else {
    $all = @(Get-Printer -ErrorAction Stop | Select-Object Name, JobCount)
    foreach ($row in $all) {
      $depth = 0
      try { $depth = [int]$row.JobCount } catch { $depth = 0 }
      if ($depth -lt 0) { $depth = 0 }
      if ($depth -gt 100000) { $depth = 100000 }
      $queueDepth += $depth
    }
    foreach ($row in @($all | Select-Object -First 8)) {
      $depth = 0
      try { $depth = [int]$row.JobCount } catch { $depth = 0 }
      if ($depth -lt 0) { $depth = 0 }
      if ($depth -gt 100000) { $depth = 100000 }
      $printers += @{ name = (Clip ([string]$row.Name) 40); depth = $depth }
    }
  }
} catch {
  $queueStatus = Classify $_.Exception.Message
  $printers = @()
  $queueDepth = 0
}

$storageStatus = 'collected'
$disks = @()
try {
  if (-not (Get-Command Get-PhysicalDisk -ErrorAction SilentlyContinue)) {
    $storageStatus = 'unsupported'
  } else {
    $seen = 0
    $withHealth = 0
    foreach ($row in @(Get-PhysicalDisk -ErrorAction Stop | Select-Object -First 8 FriendlyName, HealthStatus, OperationalStatus)) {
      $seen += 1
      $health = Clip ([string]$row.HealthStatus) 20
      if (-not $health -or $health -eq 'Unknown') { continue }
      $withHealth += 1
      $disks += @{
        name = (Clip ([string]$row.FriendlyName) 40)
        health = $health
        operational = (Clip ([string]$row.OperationalStatus) 40)
      }
    }
    if ($seen -gt 0 -and $withHealth -eq 0) { $storageStatus = 'unavailable' }
  }
} catch {
  $storageStatus = Classify $_.Exception.Message
  $disks = @()
}

$deviceStatus = 'collected'
$problems = @()
$problemCount = 0
try {
  if (-not (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
    $deviceStatus = 'unsupported'
  } else {
    $all = @(Get-PnpDevice -ErrorAction Stop | Where-Object { $_.Problem -and $_.Problem -ne 'CM_PROB_NONE' })
    $problemCount = @($all).Count
    foreach ($row in @($all | Select-Object -First 8)) {
      $problems += @{
        name = (Clip ([string]$row.FriendlyName) 40)
        class = (Clip ([string]$row.Class) 24)
        problem = (Clip ([string]$row.Problem) 40)
      }
    }
  }
} catch {
  $deviceStatus = Classify $_.Exception.Message
  $problems = @()
  $problemCount = 0
}

$errorStatus = 'collected'
$errorCount = $null
try {
  $events = @(Get-WinEvent -FilterHashtable @{LogName='System'; Level=2; StartTime=(Get-Date).AddHours(-24)} -MaxEvents 200 -ErrorAction Stop)
  $errorCount = @($events).Count
} catch {
  $id = [string]$_.FullyQualifiedErrorId
  if ($id -match 'NoMatchingEventsFound') {
    $errorCount = 0
  } else {
    $errorStatus = Classify ([string]$_.Exception.Message)
  }
}

@{
  reboot = @{ status = $rebootStatus; pending = [bool]$pending; sources_read = $sources }
  services = @{ status = $serviceStatus; failed = $failed; failed_count = $failedCount }
  queues = @{ status = $queueStatus; printers = $printers; depth = $queueDepth }
  storage = @{ status = $storageStatus; source = 'physical_disk'; disks = $disks }
  devices = @{ status = $deviceStatus; problems = $problems; problem_count = $problemCount }
  errors = @{ status = $errorStatus; error_count = $errorCount; window_hours = 24; capped_at = 200 }
} | ConvertTo-Json -Compress -Depth 6
"""


def _clip(value: str, limit: int = HEALTH_SUMMARY_LIMIT) -> str:
    return value[:limit]


def _safe_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(_CONTROL.sub(" ", value).split())
    if not text or _SECRETISH.search(text) or _COMMANDISH.search(text) or _PRODUCT_KEY.search(text):
        return ""
    if ":\\" in text or text.startswith("/") or "://" in text or ".." in text:
        return ""
    return text[:limit]


def _label(payload: dict[str, Any], fixture: str) -> str:
    candidates = [fixture]
    if "fixture" in payload:
        body = payload.get("fixture")
        candidates.append(body if isinstance(body, str) else "rejected")
    label = ""
    for item in candidates:
        if not isinstance(item, str):
            return "rejected"
        folded = " ".join(item.split()).casefold()
        if not folded:
            continue
        if folded == SYNTHETIC:
            label = SYNTHETIC
            continue
        return "rejected"
    return label


def _blank(procedure_id: str, status: str, fixture: str) -> dict[str, Any]:
    if status not in _CLOSED:
        status = "unavailable"
    label = fixture if fixture == SYNTHETIC else ""
    parts = [f"status={status}"]
    if label:
        parts.append("fixture=synthetic")
    return {
        "procedure_id": procedure_id,
        "fixture": label,
        "evidence_source": "unavailable",
        "ok": False,
        "status": status,
        "detail": status,
        "summary": _clip("; ".join(parts)),
        "problem_resolved": False,
    }


def _success(procedure_id: str, summary: str, **extra: Any) -> dict[str, Any]:
    text = _clip(summary) or "status=collected"
    reading = {
        "procedure_id": procedure_id,
        "fixture": "",
        "evidence_source": "live_windows",
        "ok": True,
        "status": "collected",
        "detail": "",
        "summary": text,
        "problem_resolved": False,
    }
    reading.update(extra)
    return reading


def _open(procedure_id: str, payload: Any, fixture: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(payload, dict):
        return _blank(procedure_id, "unavailable", ""), None
    label = _label(payload, fixture)
    if label == "rejected":
        return _blank(procedure_id, "unavailable", ""), None
    status = str(payload.get("status") or "").strip().casefold()
    if status in _CLOSED:
        return _blank(procedure_id, status, label), None
    if status not in {"", "collected"}:
        return _blank(procedure_id, "unavailable", label), None
    if label == SYNTHETIC:
        return _blank(procedure_id, "unavailable", label), None
    return None, payload


def _present_rows(payload: dict[str, Any], *keys: str) -> list[Any] | None:
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
        return None
    return None


def _sources(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 <= value <= 20:
        return value
    if isinstance(value, list) and len(value) <= 20:
        return len(value)
    return None


def _count_at_least(supplied: Any, kept: int, *, cap: int) -> int:
    if isinstance(supplied, int) and not isinstance(supplied, bool) and kept >= cap and supplied >= kept:
        return min(supplied, 10000)
    return kept


def _assess_reboot(payload: Any, fixture: str) -> dict[str, Any]:
    procedure_id = "win.reboot.pending"
    stopped, body = _open(procedure_id, payload, fixture)
    if stopped is not None or body is None:
        return stopped or _blank(procedure_id, "unavailable", "")
    pending = body.get("pending")
    sources = _sources(body.get("sources_read"))
    if not isinstance(pending, bool) or sources is None or sources < 1:
        return _blank(procedure_id, "unavailable", "")
    return _success(
        procedure_id,
        "pending=true" if pending else "pending=false",
        pending=pending,
        sources_read=sources,
    )


def _service_name(value: Any) -> str:
    text = _safe_text(value, 40)
    if not text or not _SERVICE_NAME.fullmatch(text):
        return ""
    return text


def _service_state(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return _SERVICE_STATES.get(value, "")
    text = _safe_text(value, 20)
    if not text:
        return ""
    return _STATE_NAMES.get(text.casefold(), "")


def _is_automatic(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == 2
    text = _safe_text(value, 40).casefold().replace(" ", "")
    return text in {"automatic", "automaticdelayedstart", "auto"}


def _classify_service(row: Any) -> tuple[str, dict[str, str] | None]:
    if not isinstance(row, dict):
        return "bad", None
    name = _service_name(row.get("name") if "name" in row else row.get("Name"))
    state = _service_state(row.get("state") if "state" in row else row.get("Status"))
    if not name or not state:
        return "bad", None
    if "start" in row or "StartType" in row:
        start = row.get("start") if "start" in row else row.get("StartType")
        if not _is_automatic(start):
            return "skip", None
    if state == "Running":
        return "skip", None
    return "keep", {"name": name, "state": state}


def _assess_services(payload: Any, fixture: str) -> dict[str, Any]:
    procedure_id = "win.services.failed"
    stopped, body = _open(procedure_id, payload, fixture)
    if stopped is not None or body is None:
        return stopped or _blank(procedure_id, "unavailable", "")
    rows = _present_rows(body, "failed", "services")
    if rows is None:
        return _blank(procedure_id, "unavailable", "")
    kept: list[dict[str, str]] = []
    bad = 0
    for row in rows:
        kind, parsed = _classify_service(row)
        if kind == "bad":
            bad += 1
        elif kind == "keep" and parsed is not None:
            kept.append(parsed)
    if rows and bad == len(rows):
        return _blank(procedure_id, "unavailable", "")
    count = _count_at_least(body.get("failed_count"), len(kept), cap=8)
    shown = kept[:8]
    parts = [f"failed={count}"]
    parts.extend(f"{item['name']}={item['state']}" for item in shown[:3])
    return _success(procedure_id, "; ".join(parts), failed=shown, failed_count=count)


def _printer_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    name = _safe_text(row.get("name") if "name" in row else row.get("Name"), 40)
    depth = row.get("depth") if "depth" in row else row.get("JobCount")
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0 or depth > 100_000:
        return None
    if not name:
        return None
    return {"name": name, "depth": depth}


def _assess_queues(payload: Any, fixture: str) -> dict[str, Any]:
    procedure_id = "print.queue.depth"
    stopped, body = _open(procedure_id, payload, fixture)
    if stopped is not None or body is None:
        return stopped or _blank(procedure_id, "unavailable", "")
    rows = _present_rows(body, "printers", "queues")
    if rows is None:
        return _blank(procedure_id, "unavailable", "")
    kept: list[dict[str, Any]] = []
    bad = 0
    for row in rows:
        parsed = _printer_row(row)
        if parsed is None:
            bad += 1
        else:
            kept.append(parsed)
    if rows and bad == len(rows):
        return _blank(procedure_id, "unavailable", "")
    sample_sum = sum(int(item["depth"]) for item in kept)
    supplied = body.get("depth")
    if (
        isinstance(supplied, int)
        and not isinstance(supplied, bool)
        and supplied >= sample_sum
        and (not kept or supplied == sample_sum or len(kept) >= 8)
        and supplied <= 1_000_000
    ):
        total = supplied
    else:
        total = sample_sum
    shown = kept[:8]
    parts = [f"depth={total}"]
    parts.extend(f"{item['name']}={item['depth']}" for item in shown[:3])
    return _success(procedure_id, "; ".join(parts), depth=total, printers=shown)


def _health_text(value: Any) -> str:
    text = _safe_text(value, 20)
    if not text or text.casefold() in {"unknown", "unspecified"}:
        return ""
    if not re.fullmatch(r"[A-Za-z][A-Za-z ]{0,19}", text):
        return ""
    return text


def _assess_storage(payload: Any, fixture: str) -> dict[str, Any]:
    procedure_id = "win.storage.health"
    stopped, body = _open(procedure_id, payload, fixture)
    if stopped is not None or body is None:
        return stopped or _blank(procedure_id, "unavailable", "")
    source = str(body.get("source") or "").strip().casefold()
    if source not in _STORAGE_SOURCES:
        return _blank(procedure_id, "unavailable", "")
    rows = _present_rows(body, "disks", "volumes")
    if rows is None:
        return _blank(procedure_id, "unavailable", "")
    if not rows:
        return _success(procedure_id, "disks=0", source=source, disks=[], unhealthy=0)
    kept: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        health = _health_text(row.get("health") if "health" in row else row.get("HealthStatus"))
        if not health:
            continue
        name = _safe_text(row.get("name") or row.get("FriendlyName") or row.get("device") or "", 40) or "disk"
        item = {"name": name, "health": health}
        operational = _safe_text(row.get("operational") or row.get("OperationalStatus") or "", 40)
        if operational and operational.casefold() not in {"unknown", "unspecified"}:
            item["operational"] = operational
        kept.append(item)
    if not kept:
        return _blank(procedure_id, "unavailable", "")
    unhealthy = sum(1 for item in kept if item["health"].casefold() in {"unhealthy", "warning"})
    parts = [f"unhealthy={unhealthy}"]
    parts.extend(f"{item['name']}={item['health']}" for item in kept[:3])
    return _success(
        procedure_id,
        "; ".join(parts),
        source=source,
        disks=kept[:8],
        unhealthy=unhealthy,
    )


def _problem_code(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, int):
        if 1 <= value <= 999:
            return str(value)
        return ""
    text = _safe_text(value, 40)
    if not text or not re.fullmatch(r"[A-Za-z0-9_]{1,40}", text):
        return ""
    if text.casefold() in {"cm_prob_none", "none", "ok"}:
        return ""
    return text


def _problem_device(row: Any) -> Any:
    if not isinstance(row, dict):
        return None
    name = _safe_text(row.get("name") if "name" in row else row.get("FriendlyName"), 40)
    class_name = _safe_text(row.get("class") if "class" in row else row.get("Class"), 24)
    problem = _problem_code(row.get("problem") if "problem" in row else row.get("Problem"))
    if not name and not class_name and not problem:
        return None
    if not problem:
        return _SKIP
    return {"name": name, "class": class_name, "problem": problem}


def _assess_devices(payload: Any, fixture: str) -> dict[str, Any]:
    procedure_id = "hw.devices.problems"
    stopped, body = _open(procedure_id, payload, fixture)
    if stopped is not None or body is None:
        return stopped or _blank(procedure_id, "unavailable", "")
    rows = _present_rows(body, "problems", "devices")
    if rows is None:
        return _blank(procedure_id, "unavailable", "")
    kept: list[dict[str, str]] = []
    bad = 0
    for row in rows:
        parsed = _problem_device(row)
        if parsed is None:
            bad += 1
        elif parsed is not _SKIP:
            kept.append(parsed)
    if rows and not kept and bad == len(rows):
        return _blank(procedure_id, "unavailable", "")
    count = _count_at_least(body.get("problem_count"), len(kept), cap=8)
    parts = [f"problems={count}"]
    for item in kept[:2]:
        bits = [item["name"] or "device"]
        if item["class"]:
            bits.append(f"class={item['class']}")
        bits.append(f"problem={item['problem']}")
        parts.append(" ".join(bits))
    return _success(
        procedure_id,
        "; ".join(parts),
        problems=kept[:8],
        problem_count=count,
    )


def _assess_errors(payload: Any, fixture: str) -> dict[str, Any]:
    procedure_id = "win.events.recent"
    stopped, body = _open(procedure_id, payload, fixture)
    if stopped is not None or body is None:
        return stopped or _blank(procedure_id, "unavailable", "")
    if "error_count" not in body:
        return _blank(procedure_id, "unavailable", "")
    count = body.get("error_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > 1_000_000:
        return _blank(procedure_id, "unavailable", "")
    window = body.get("window_hours", None)
    window_out: int | None
    if window is None:
        window_out = None
    elif isinstance(window, bool) or not isinstance(window, int) or window < 1 or window > 168:
        return _blank(procedure_id, "unavailable", "")
    else:
        window_out = window
    cap = body.get("capped_at", None)
    truncated = False
    if cap is not None:
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1 or cap > 1_000_000:
            return _blank(procedure_id, "unavailable", "")
        truncated = count >= cap
    parts = [f"error_count={count}"]
    if window_out is not None:
        parts.append(f"window_hours={window_out}")
    if truncated:
        parts.append("truncated=true")
    extra: dict[str, Any] = {"error_count": count, "truncated": truncated}
    if window_out is not None:
        extra["window_hours"] = window_out
    return _success(procedure_id, "; ".join(parts), **extra)


_ASSESSORS = {
    "win.reboot.pending": _assess_reboot,
    "win.services.failed": _assess_services,
    "print.queue.depth": _assess_queues,
    "win.storage.health": _assess_storage,
    "hw.devices.problems": _assess_devices,
    "win.events.recent": _assess_errors,
}


def assess_check(procedure_id: str, payload: Any, *, fixture: str = "") -> dict[str, Any]:
    """Classify one check payload. Does not run a command."""
    assessor = _ASSESSORS.get(procedure_id)
    if assessor is None:
        return _blank(procedure_id if isinstance(procedure_id, str) else "unknown", "unavailable", "")
    return assessor(payload, fixture)


def _script_status(raw: dict[str, Any]) -> str:
    if raw.get("status") in {"tool_missing", "unsupported"}:
        return "unsupported"
    text = " ".join(str(raw.get(name) or "") for name in ("status", "detail", "stderr")).casefold()
    if any(token in text for token in ("access is denied", "unauthorized", "0x80041003", "privilege")):
        return "permission-denied"
    if any(token in text for token in ("invalid class", "not recognized", "not supported", "tool_missing")):
        return "unsupported"
    return "unavailable"


def _closed_bundle(status: str) -> dict[str, dict[str, Any]]:
    if status not in _CLOSED:
        status = "unavailable"
    return {procedure_id: _blank(procedure_id, status, "") for procedure_id in HEALTH_PROCEDURE_IDS}


def readings_from_script_result(raw: Any) -> dict[str, dict[str, Any]]:
    """Map one fixed-script result onto the six checks. Section failures stay separate."""
    if not isinstance(raw, dict):
        return _closed_bundle("unavailable")
    body = raw.get("payload") if isinstance(raw.get("payload"), dict) else None
    if raw.get("ok") and body is not None:
        fixture = body.get("fixture") if isinstance(body.get("fixture"), str) else ""
        return {
            procedure_id: assess_check(procedure_id, body.get(_SECTION[procedure_id]), fixture=fixture)
            for procedure_id in HEALTH_PROCEDURE_IDS
        }
    if any(name in raw for name in _SECTION.values()) and "ok" not in raw:
        fixture = raw.get("fixture") if isinstance(raw.get("fixture"), str) else ""
        return {
            procedure_id: assess_check(procedure_id, raw.get(_SECTION[procedure_id]), fixture=fixture)
            for procedure_id in HEALTH_PROCEDURE_IDS
        }
    return _closed_bundle(_script_status(raw))


def _run_fixed_script(timeout: float) -> dict[str, Any]:
    from .runner import parse_json_output, powershell_exe, run_argv

    executable = powershell_exe()
    if not executable:
        return {
            "ok": False,
            "status": "tool_missing",
            "evidence_source": "unavailable",
            "detail": "Windows PowerShell was not found.",
        }
    result = run_argv(
        [executable, "-NoProfile", "-NonInteractive", "-Command", FIXED_SCRIPT],
        timeout=timeout,
    )
    if result.get("ok"):
        try:
            result["payload"] = parse_json_output(str(result.get("stdout") or ""))
        except (ValueError, json.JSONDecodeError):
            result = dict(result)
            result["ok"] = False
            result["status"] = "unreadable"
            result["detail"] = "unreadable"
    return result


def collect_health_bundle(
    *,
    read: Callable[[], Any] | None = None,
    timeout: float = 18,
) -> dict[str, dict[str, Any]]:
    """Read all six checks. A test double replaces the fixed script."""
    if read is not None and not callable(read):
        return _closed_bundle("unavailable")
    try:
        raw = read() if read is not None else _run_fixed_script(timeout)
    except Exception:
        return _closed_bundle("unavailable")
    return readings_from_script_result(raw if isinstance(raw, dict) else None)


def collect_health_check(
    procedure_id: str,
    *,
    read: Callable[[], Any] | None = None,
    timeout: float = 18,
) -> dict[str, Any]:
    """Read one registered health check. Unknown ids are unavailable."""
    if procedure_id not in HEALTH_PROCEDURE_IDS:
        return _blank(str(procedure_id), "unavailable", "")
    return collect_health_bundle(read=read, timeout=timeout)[procedure_id]
