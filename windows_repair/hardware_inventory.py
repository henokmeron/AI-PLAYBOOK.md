"""Read-only hardware identity for one Windows computer.

The collector does not accept a command, a path, or a credential. Serial
numbers and signed-in user names are not read. A synthetic fixture is never a
live success. Missing manufacturer, model, BIOS, CPU, or memory is
unavailable, unsupported, or permission-denied, and is not ok.
"""
from __future__ import annotations

import re
from typing import Any, Callable

PROCEDURE_ID = "hw.identity.inspect"
SYNTHETIC = "synthetic"
MANUFACTURER_LIMIT = 48
MODEL_LIMIT = 48
BIOS_VENDOR_LIMIT = 40
BIOS_VERSION_LIMIT = 40
BIOS_LIMIT = 48
CPU_LIMIT = 64
_MAX_BYTES = 1 << 60
_STATUSES = ("collected", "unavailable", "unsupported", "permission-denied")
_CLOSED = frozenset({"unavailable", "unsupported", "permission-denied"})
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SECRETISH = re.compile(r"(?i)(password|secret|api[_-]?key|authorization|bearer|token\s*[:=])")
_COMMANDISH = re.compile(r"(?i)(powershell|cmd(?:\.exe)?\s+/|invoke-expression|\.\./|\\\\)")
_PRODUCT_KEY = re.compile(r"\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b")

SYNTHETIC_COMPLETE: dict[str, Any] = {
    "fixture": SYNTHETIC,
    "status": "collected",
    "manufacturer": "Synthetic OEM",
    "model": "Synthetic Model",
    "bios_vendor": "Synthetic BIOS",
    "bios_version": "S1.0",
    "cpu": "Synthetic CPU",
    "memory_available_bytes": 4 * 1024 ** 3,
    "memory_total_bytes": 8 * 1024 ** 3,
}
SYNTHETIC_MISSING: dict[str, Any] = {
    "fixture": SYNTHETIC,
    "status": "collected",
    "manufacturer": "Synthetic OEM",
}
SYNTHETIC_DENIED: dict[str, Any] = {
    "fixture": SYNTHETIC,
    "status": "permission-denied",
    "manufacturer": "Synthetic OEM",
    "model": "Synthetic Model",
    "bios_vendor": "Synthetic BIOS",
    "bios_version": "S1.0",
    "cpu": "Synthetic CPU",
    "memory_available_bytes": 1024,
    "memory_total_bytes": 2048,
}


def _text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(_CONTROL.sub(" ", value).split())
    if not text or _SECRETISH.search(text) or _COMMANDISH.search(text) or _PRODUCT_KEY.search(text):
        return ""
    if ":\\" in text or text.startswith("/") or "://" in text:
        return ""
    return text[:limit]


def _bytes(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str) and len(value) <= 20 and value.isdigit():
        number = int(value)
    else:
        return None
    if number < 0 or number > _MAX_BYTES:
        return None
    return number


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
        "manufacturer": "",
        "model": "",
        "bios_vendor": "",
        "bios_version": "",
        "cpu": "",
        "memory_available_bytes": None,
        "memory_total_bytes": None,
        "problem_resolved": False,
    }


def join_bios(vendor: str, version: str, limit: int = BIOS_LIMIT) -> str:
    """Keep the BIOS version, then the vendor, inside the stored limit."""
    version = version[:limit]
    room = limit - len(version) - 1
    if vendor and room > 0:
        return f"{version} {vendor[:room]}"
    return version


def assess_hardware_identity(payload: Any, *, fixture: str = "") -> dict[str, Any]:
    """Classify one identity payload. Does not run a command."""
    if not isinstance(payload, dict):
        return _blank("unavailable", "")
    label = _label(payload, fixture)
    if label == "rejected":
        return _blank("unavailable", "")
    script_status = str(payload.get("status") or "").strip().casefold()
    if script_status not in _STATUSES:
        script_status = "unavailable"
    if script_status in _CLOSED:
        return _blank(script_status, label)
    manufacturer = _text(payload.get("manufacturer"), MANUFACTURER_LIMIT)
    model = _text(payload.get("model"), MODEL_LIMIT)
    bios_vendor = _text(payload.get("bios_vendor"), BIOS_VENDOR_LIMIT)
    bios_version = _text(payload.get("bios_version"), BIOS_VERSION_LIMIT)
    cpu = _text(payload.get("cpu"), CPU_LIMIT)
    available = _bytes(payload.get("memory_available_bytes"))
    total = _bytes(payload.get("memory_total_bytes"))
    complete = bool(
        manufacturer
        and model
        and bios_vendor
        and bios_version
        and cpu
        and available is not None
        and total is not None
        and total >= 1
        and available <= total
    )
    if not complete or label == SYNTHETIC:
        return _blank("unavailable", label)
    return {
        "procedure_id": PROCEDURE_ID,
        "fixture": "",
        "evidence_source": "live_windows",
        "ok": True,
        "status": "collected",
        "detail": "",
        "manufacturer": manufacturer,
        "model": model,
        "bios_vendor": bios_vendor,
        "bios_version": bios_version,
        "cpu": cpu,
        "memory_available_bytes": available,
        "memory_total_bytes": total,
        "problem_resolved": False,
    }


def stored_hardware(reading: dict[str, Any] | None) -> dict[str, Any]:
    """The bounded object the console stores. Synthetic and partial readings are not collected."""
    if not isinstance(reading, dict) or reading.get("fixture") == SYNTHETIC or not reading.get("ok"):
        status = str((reading or {}).get("status") or "")
        if status not in _CLOSED:
            status = "unavailable"
        return {
            "status": status,
            "manufacturer": "",
            "model": "",
            "bios": "",
            "cpu": "",
            "memory_available_bytes": None,
            "memory_total_bytes": None,
        }
    return {
        "status": "collected",
        "manufacturer": _text(reading.get("manufacturer"), MANUFACTURER_LIMIT),
        "model": _text(reading.get("model"), MODEL_LIMIT),
        "bios": join_bios(
            _text(reading.get("bios_vendor"), BIOS_VENDOR_LIMIT),
            _text(reading.get("bios_version"), BIOS_VERSION_LIMIT),
        ),
        "cpu": _text(reading.get("cpu"), CPU_LIMIT),
        "memory_available_bytes": reading.get("memory_available_bytes"),
        "memory_total_bytes": reading.get("memory_total_bytes"),
    }


def _script_status(raw: dict[str, Any]) -> str:
    if raw.get("status") == "tool_missing":
        return "unsupported"
    text = " ".join(
        str(raw.get(name) or "")
        for name in ("status", "detail", "stderr")
    ).casefold()
    if any(token in text for token in ("access is denied", "unauthorized", "0x80041003", "privilege")):
        return "permission-denied"
    if any(token in text for token in ("invalid class", "not supported", "not recognized")):
        return "unsupported"
    return "unavailable"


def reading_from_script_result(raw: Any, collected_at: int) -> dict[str, Any]:
    """Map one fixed-script result. The script text is not taken from the caller."""
    if not isinstance(raw, dict):
        raw = {}
    if raw.get("ok") and isinstance(raw.get("payload"), dict):
        reading = assess_hardware_identity(raw["payload"])
    else:
        reading = assess_hardware_identity({"status": _script_status(raw)})
    reading["collected_at_unix"] = int(collected_at)
    reading["mocked"] = False
    reading["problem_resolved"] = False
    return reading


def collect_hardware_identity(
    *,
    timeout: float = 18,
    read: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the registered identity script, or a test double that returns its result dict."""
    from time import time

    if read is not None and not callable(read):
        return reading_from_script_result(
            {"ok": False, "status": "failed", "evidence_source": "unavailable"},
            int(time()),
        )
    if read is None:
        from .runner import run_script

        raw = run_script("hardware_identity", timeout=timeout)
    else:
        raw = read()
    return reading_from_script_result(raw if isinstance(raw, dict) else {}, int(time()))
