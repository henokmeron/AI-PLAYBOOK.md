"""Read-only Windows device health, and a driver-install decision.

The report does not accept a command, a path, a credential, or a URL.
Serial numbers are not read. A synthetic fixture is never a live success.
Missing name, class, problem code, driver version, driver provider, or
driver date is unavailable, unsupported, or permission-denied, and is not ok.

propose_driver_install and install_driver do not download a driver and do
not start pnputil, Windows Update, or any other installer. The default
decision is refused. An arbitrary URL is refused even when an approval
object is present. When approval names the device id, the action id, and
the exact device target, and the source is windows-update or pnputil,
install_driver returns a plan record and does not shell out.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

PROCEDURE_ID = "hw.driver.health"
INSTALL_PROCEDURE_ID = "hw.driver.install"
SYNTHETIC = "synthetic"
ALLOWED_SOURCES = ("windows-update", "pnputil")
_FIELDS = ("name", "class", "problem_code", "driver_version", "driver_provider", "driver_date")
_STATUSES = ("collected", "unavailable", "unsupported", "permission-denied")
_CLOSED = frozenset({"unavailable", "unsupported", "permission-denied"})
_MAX_DEVICES = 32
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SECRETISH = re.compile(r"(?i)(password|secret|api[_-]?key|authorization|bearer|token\s*[:=])")
_COMMANDISH = re.compile(r"(?i)(powershell|cmd(?:\.exe)?\s+/|invoke-expression|\.\./|\\\\)")
_PRODUCT_KEY = re.compile(r"\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b")
_URL = re.compile(r"(?i)([a-z][a-z0-9+.-]*://|\\\\|www\.)")
_PNP_SERIAL = re.compile(r"(?i)(usb\\|pci\\|scsi\\|swd\\|hdaudio\\|serial(?:number)?|\\vid_)")
_VERSION = re.compile(r"^\d{1,5}(?:\.\d{1,5}){1,3}$")
_CM_PROB = re.compile(r"^CM_PROB_[A-Z0-9_]{1,40}$")
_CLASS = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,39}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()\-]{0,119}$")

SYNTHETIC_COMPLETE: dict[str, Any] = {
    "fixture": SYNTHETIC,
    "status": "collected",
    "devices": [
        {
            "name": "Synthetic Audio",
            "class": "MEDIA",
            "problem_code": 28,
            "driver_version": "1.0.0.0",
            "driver_provider": "Synthetic Provider",
            "driver_date": "2020-01-01",
        }
    ],
}
SYNTHETIC_MISSING: dict[str, Any] = {
    "fixture": SYNTHETIC,
    "status": "collected",
    "devices": [{"name": "Synthetic Audio", "class": "MEDIA", "problem_code": 28}],
}
SYNTHETIC_DENIED: dict[str, Any] = {
    "fixture": SYNTHETIC,
    "status": "permission-denied",
    "devices": [
        {
            "name": "Synthetic Audio",
            "class": "MEDIA",
            "problem_code": 28,
            "driver_version": "1.0.0.0",
            "driver_provider": "Synthetic Provider",
            "driver_date": "2020-01-01",
        }
    ],
}


def _plain(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(_CONTROL.sub(" ", value).split())
    if not text or _SECRETISH.search(text) or _COMMANDISH.search(text) or _PRODUCT_KEY.search(text):
        return ""
    if _URL.search(text) or _PNP_SERIAL.search(text):
        return ""
    return text[:limit]


def _name(value: Any) -> str:
    text = _plain(value, 80)
    if not text or not re.search(r"[A-Za-z]", text):
        return ""
    return text


def _device_class(value: Any) -> str:
    text = _plain(value, 40)
    if text and _CLASS.fullmatch(text):
        return text
    return ""


def _problem(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, int):
        if 0 <= value <= 55:
            return str(value)
        return ""
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    if re.fullmatch(r"\d{1,2}", text):
        number = int(text)
        if 0 <= number <= 55:
            return str(number)
        return ""
    if _CM_PROB.fullmatch(text):
        return text
    return ""


def _version(value: Any) -> str:
    text = _plain(value, 40)
    if text and _VERSION.fullmatch(text):
        return text
    return ""


def _provider(value: Any) -> str:
    text = _plain(value, 64)
    if text and re.search(r"[A-Za-z]", text):
        return text
    return ""


def _driver_date(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or _URL.search(text) or _SECRETISH.search(text) or _COMMANDISH.search(text):
        return ""
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text) or re.match(r"^(\d{4})(\d{2})(\d{2})", text)
    if not match:
        return ""
    year, month, day = (int(match.group(index)) for index in (1, 2, 3))
    if year < 1990 or year > 2100:
        return ""
    try:
        date(year, month, day)
    except ValueError:
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


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


def _blank(status: str, fixture: str) -> dict[str, Any]:
    if status not in _CLOSED:
        status = "unavailable"
    return {
        "procedure_id": PROCEDURE_ID,
        "fixture": fixture if fixture == SYNTHETIC else "",
        "evidence_source": "unavailable",
        "ok": False,
        "status": status,
        "detail": status,
        "devices": [],
        "problem_resolved": False,
        "changed_device": False,
        "downloaded": False,
    }


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _declared_status(row: dict[str, Any], field: str) -> str:
    declared = row.get("field_status")
    if not isinstance(declared, dict):
        declared = row.get("fields") if isinstance(row.get("fields"), dict) else {}
    raw = declared.get(field)
    if raw is None and field == "class":
        raw = declared.get("device_class")
    text = str(raw or "").strip().casefold()
    if text in _CLOSED:
        return text
    return ""


def _worst(statuses: list[str]) -> str:
    if "permission-denied" in statuses:
        return "permission-denied"
    if "unsupported" in statuses:
        return "unsupported"
    return "unavailable"


def _one_device(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        row = {}
    parsed = {
        "name": _name(_first(row, "name", "Name", "FriendlyName")),
        "class": _device_class(_first(row, "class", "Class", "device_class")),
        "problem_code": _problem(_first(row, "problem_code", "ProblemCode", "Problem", "problem")),
        "driver_version": _version(_first(row, "driver_version", "DriverVersion")),
        "driver_provider": _provider(_first(row, "driver_provider", "DriverProvider", "DriverProviderName")),
        "driver_date": _driver_date(_first(row, "driver_date", "DriverDate")),
    }
    device: dict[str, Any] = {}
    gaps: list[str] = []
    for field in _FIELDS:
        forced = _declared_status(row, field)
        if forced:
            device[field] = forced
            gaps.append(forced)
        elif parsed[field]:
            device[field] = parsed[field]
        else:
            device[field] = "unavailable"
            gaps.append("unavailable")
    if gaps:
        device["status"] = _worst(gaps)
        device["ok"] = False
    else:
        device["status"] = "collected"
        device["ok"] = True
    return device


def assess_device_health(payload: Any, *, fixture: str = "") -> dict[str, Any]:
    """Classify one device-health payload. Does not run a command or open a network connection."""
    if not isinstance(payload, dict):
        return _blank("unavailable", "")
    label = _label(payload, fixture)
    if label == "rejected":
        return _blank("unavailable", "")
    raw_status = str(payload.get("status") or "").strip().casefold()
    if raw_status in _CLOSED:
        return _blank(raw_status, label)
    if label == SYNTHETIC:
        return _blank("unavailable", label)
    if raw_status not in ("", "collected"):
        return _blank("unavailable", label)
    devices_in = payload.get("devices")
    if not isinstance(devices_in, list) or not devices_in or len(devices_in) > _MAX_DEVICES:
        return _blank("unavailable", label)
    devices = [_one_device(row) for row in devices_in]
    gaps = [device["status"] for device in devices if not device["ok"]]
    if gaps:
        report = _blank(_worst(gaps), label)
        report["devices"] = devices
        return report
    return {
        "procedure_id": PROCEDURE_ID,
        "fixture": "",
        "evidence_source": "supplied",
        "ok": True,
        "status": "collected",
        "detail": "",
        "devices": devices,
        "problem_resolved": False,
        "changed_device": False,
        "downloaded": False,
    }


def _script_status(raw: dict[str, Any]) -> str:
    if raw.get("status") == "tool_missing":
        return "unsupported"
    text = " ".join(str(raw.get(name) or "") for name in ("status", "detail", "stderr")).casefold()
    if any(token in text for token in ("access is denied", "unauthorized", "0x80041003", "privilege")):
        return "permission-denied"
    if any(token in text for token in ("invalid class", "not supported", "not recognized")):
        return "unsupported"
    return "unavailable"


def reading_from_result(raw: Any) -> dict[str, Any]:
    """Map one supplied result. Caller text other than the status class is not stored."""
    if not isinstance(raw, dict):
        return _blank("unavailable", "")
    if raw.get("ok") is False:
        return assess_device_health({"status": _script_status(raw)})
    if isinstance(raw.get("payload"), dict):
        return assess_device_health(raw["payload"])
    return assess_device_health(raw)


def collect_device_health(*, read: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Classify a test double. No reader means unavailable. This does not query the host."""
    if read is None or not callable(read):
        return _blank("unavailable", "")
    try:
        raw = read()
    except Exception:
        return _blank("unavailable", "")
    reading = reading_from_result(raw if isinstance(raw, dict) else {})
    reading["problem_resolved"] = False
    reading["changed_device"] = False
    reading["downloaded"] = False
    return reading


def _contains_url(value: Any, depth: int = 0) -> bool:
    if depth > 5:
        return True
    if isinstance(value, str):
        return bool(_URL.search(value))
    if isinstance(value, dict):
        return any(_contains_url(key, depth + 1) or _contains_url(item, depth + 1) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_url(item, depth + 1) for item in value)
    return False


def _source_decision(source: Any) -> tuple[str, str]:
    if isinstance(source, str) and _URL.search(source):
        return "", "arbitrary-url"
    if not isinstance(source, str):
        return "", "source-not-allowed"
    token = source.strip().casefold()
    if token in ALLOWED_SOURCES:
        return token, ""
    if token == "":
        return "", "default-refuse"
    return "", "source-not-allowed"


def _refused(reason: str, *, source: str = "", source_eligible: bool = False) -> dict[str, Any]:
    details = {
        "arbitrary-url": "An arbitrary URL is refused. Nothing was downloaded.",
        "source-not-allowed": "The only sources that may be named are windows-update and pnputil. Nothing was downloaded.",
        "default-refuse": "Driver install is refused by default. Nothing was downloaded.",
        "approval-missing": "Driver install is refused. No approval named the device.",
        "approval-incomplete": "Driver install is refused. Approval must name the device id, action id, and exact device target.",
        "device-id-mismatch": "Driver install is refused. The device id does not match.",
        "action-id-mismatch": "Driver install is refused. The action id does not match.",
        "device-target-mismatch": "Driver install is refused. The device target does not match exactly.",
        "device-target-rejected": "Driver install is refused. The device target cannot be used.",
    }
    named = source if source in ALLOWED_SOURCES else ""
    if reason == "default-refuse" and named:
        detail = (
            f"{named} may be named. Driver install stays refused until approval names "
            "the device id, action id, and the exact device target. Nothing was downloaded."
        )
    else:
        detail = details.get(reason, "Driver install is refused. Nothing was downloaded.")
    return {
        "procedure_id": INSTALL_PROCEDURE_ID,
        "status": "refused",
        "refused": True,
        "executed": False,
        "downloaded": False,
        "changed_device": False,
        "problem_resolved": False,
        "reason": reason,
        "source": named,
        "source_eligible": source_eligible,
        "allowed_sources": list(ALLOWED_SOURCES),
        "would_run": None,
        "detail": detail,
    }


def _safe_target(value: str) -> bool:
    if not _TARGET.fullmatch(value):
        return False
    if _URL.search(value) or _PNP_SERIAL.search(value) or _SECRETISH.search(value) or _COMMANDISH.search(value):
        return False
    return True


def _named(approval: dict[str, Any], key: str, expected: str | None) -> tuple[str, str]:
    value = approval.get(key)
    if not isinstance(value, str) or value == "":
        return "", "approval-incomplete"
    if expected is not None and value != expected:
        if key == "device_id":
            return "", "device-id-mismatch"
        if key == "action_id":
            return "", "action-id-mismatch"
        return "", "device-target-mismatch"
    if key == "device_target":
        if not _safe_target(value) or (expected is not None and not _safe_target(expected)):
            return "", "device-target-rejected"
    elif not _TOKEN.fullmatch(value) or (expected is not None and not _TOKEN.fullmatch(expected)):
        return "", "approval-incomplete"
    return value, ""


def _plan(source: str, named: dict[str, str]) -> dict[str, Any]:
    action = "search-driver-for-device" if source == "windows-update" else "stage-driver-for-device"
    would_run = {
        "source": source,
        "action": action,
        "device_id": named["device_id"],
        "action_id": named["action_id"],
        "device_target": named["device_target"],
        "invoked": False,
        "downloaded": False,
    }
    return {
        "procedure_id": INSTALL_PROCEDURE_ID,
        "status": "plan",
        "refused": False,
        "executed": False,
        "downloaded": False,
        "changed_device": False,
        "problem_resolved": False,
        "reason": "",
        "source": source,
        "source_eligible": True,
        "allowed_sources": list(ALLOWED_SOURCES),
        "device_id": named["device_id"],
        "action_id": named["action_id"],
        "device_target": named["device_target"],
        "would_run": would_run,
        "detail": "Plan only. No installer was started and nothing was downloaded.",
    }


def propose_driver_install(
    *,
    source: str = "",
    approval: Any = None,
    device_id: str = "",
    action_id: str = "",
    device_target: str = "",
) -> dict[str, Any]:
    """Name an allowed source, or refuse. Always refuses an install. Does not download."""
    if any(_contains_url(item) for item in (source, approval, device_id, action_id, device_target)):
        return _refused("arbitrary-url")
    canonical, reason = _source_decision(source)
    if reason:
        return _refused(reason)
    return _refused("default-refuse", source=canonical, source_eligible=True)


def install_driver(
    approval: Any = None,
    *,
    device_id: str | None = None,
    action_id: str | None = None,
    device_target: str | None = None,
) -> dict[str, Any]:
    """Return a plan, or refused. The approved branch does not shell out or download."""
    if not isinstance(approval, dict):
        return _refused("approval-missing")
    if any(_contains_url(item) for item in (approval, device_id, action_id, device_target)):
        return _refused("arbitrary-url")
    canonical, reason = _source_decision(approval.get("source"))
    if reason:
        mapped = "source-not-allowed" if reason == "default-refuse" else reason
        return _refused(mapped)
    named: dict[str, str] = {}
    for key, expected in (
        ("device_id", device_id),
        ("action_id", action_id),
        ("device_target", device_target),
    ):
        value, problem = _named(approval, key, expected)
        if problem:
            return _refused(problem)
        named[key] = value
    return _plan(canonical, named)
