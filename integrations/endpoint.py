"""Authorised, outbound-only computer check-in.

A device the operator enrolled can submit one fixed diagnostic: operating
system, disk space, memory, boot time, and the registered read-only checks.
Hardware identity is manufacturer, model, BIOS, CPU, and available memory.
Further read-only checks report pending reboot, failed automatic services,
printer queue depth, storage health, problem devices, and a recent error count.
This module does not accept a command, a path, a screen capture, or a
credential. The server stores a hash of the device secret and cannot use
that hash to drive the computer.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import stat
import string
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agents.schema import ValidationError, validate

from windows_repair.health_checks import HEALTH_PROCEDURE_IDS

from .catalog import Catalog, ConnectorSpec, Effect, OperationSpec
from .errors import AuthenticationError, InvalidRequest, RateLimited
from .state_guard import StatePermissionError, assert_private, restrict_private

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}\Z")
_DEVICE_ID = re.compile(r"[0-9a-f]{32}\Z")
_MAX_BYTES = 1 << 60
_CODE_TTL = 600
_MIN_REPORT_GAP = 15.0
_ENROL_WINDOW_SECONDS = 15 * 60
_ENROL_MAX_FAILURES = 20
_FAMILIES = ("windows", "linux", "darwin", "other")
# Fifteen checks at this summary length, plus hardware identity, stay inside
# the 4096-byte console body. Keep equal to windows_repair.health_checks.HEALTH_SUMMARY_LIMIT.
CHECK_SUMMARY_LIMIT = 100
_CHECK_PROCEDURES = (
    "win.storage.space",
    "win.services.inspect",
    "win.update.inspect",
    "hw.devices.inventory",
    "print.diagnose",
    "net.diagnose",
    "win.events.recurring",
    "win.startup.inspect",
    "hw.identity.inspect",
    *HEALTH_PROCEDURE_IDS,
)
_CHECK_SOURCES = ("live_windows", "unavailable")
_MAX_CHECKS = len(_CHECK_PROCEDURES)
_STALE_SECONDS = 86400
_FUTURE_SKEW_SECONDS = 120
_CHECK_SKEW_SECONDS = 300
FIXTURE_LABEL = "not-the-second-endpoint"
_DEV_ENDPOINT_NAME = "banya-family-pl"
_CODE_ALPHABET = string.ascii_letters + string.digits

_NONE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "detail"],
    "properties": {
        "status": {"type": "string", "const": "none"},
        "detail": {"type": "string", "maxLength": 300},
    },
}
_HARDWARE_FIELDS = (
    "status", "manufacturer", "model", "bios", "cpu",
    "memory_available_bytes", "memory_total_bytes",
)
_HARDWARE = {
    "type": "object",
    "additionalProperties": False,
    "required": list(_HARDWARE_FIELDS),
    "properties": {
        "status": {
            "type": "string",
            "enum": ["collected", "unavailable", "unsupported", "permission-denied"],
        },
        "manufacturer": {"type": "string", "maxLength": 48},
        "model": {"type": "string", "maxLength": 48},
        "bios": {"type": "string", "maxLength": 48},
        "cpu": {"type": "string", "maxLength": 64},
        "memory_available_bytes": {"type": ["integer", "null"], "minimum": 0, "maximum": _MAX_BYTES},
        "memory_total_bytes": {"type": ["integer", "null"], "minimum": 0, "maximum": _MAX_BYTES},
    },
}
_REPORT = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status", "device_id", "display_name", "os_family", "os_version",
        "disk_free_bytes", "disk_total_bytes", "memory_total_bytes",
        "boot_time_unix", "collected_at_unix",
    ],
    "properties": {
        "status": {"type": "string", "const": "ok"},
        "device_id": {"type": "string", "minLength": 32, "maxLength": 32},
        "display_name": {"type": "string", "minLength": 1, "maxLength": 40},
        "os_family": {"type": "string", "enum": list(_FAMILIES)},
        "os_version": {"type": "string", "minLength": 1, "maxLength": 80},
        "disk_free_bytes": {"type": "integer", "minimum": 0, "maximum": _MAX_BYTES},
        "disk_total_bytes": {"type": "integer", "minimum": 1, "maximum": _MAX_BYTES},
        "memory_total_bytes": {"type": "integer", "minimum": 1, "maximum": _MAX_BYTES},
        "boot_time_unix": {"type": "integer", "minimum": 0, "maximum": _MAX_BYTES},
        "collected_at_unix": {"type": "integer", "minimum": 0, "maximum": _MAX_BYTES},
        "hardware": _HARDWARE,
    },
}
_READ_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"device_id": {"type": "string", "minLength": 32, "maxLength": 32}},
}
_READ_OUTPUT = {"type": "object", "anyOf": [_NONE, _REPORT]}

ENDPOINT = ConnectorSpec(
    connector_id="endpoint",
    version="0.1.0",
    service="Enrolled computer",
    summary="Read-only check-in from a computer the operator installed a worker on.",
    auth="device_secret",
    operations=(
        OperationSpec(
            name="read_diagnostics",
            summary="Read the latest operating-system, disk, memory, and boot-time report.",
            effect=Effect.READ,
            scope="device:read",
            input_schema=_READ_INPUT,
            output_schema=_READ_OUTPUT,
            provider_permissions=("outbound check-in",),
            tool_name="read_device_diagnostics",
            requires_approval=False,
            idempotent=True,
            evidence="mock-tested",
        ),
    ),
)


def assert_safe_state_path(value: Path) -> Path:
    """Device state stays off the git tree and off the shared model volume."""
    if not value.is_absolute():
        raise InvalidRequest("endpoint state file must be an absolute path")
    # Reject link leaves before resolve(); resolve() would follow them and hide the attack.
    if value.is_symlink() or value.parent.is_symlink():
        raise InvalidRequest("endpoint state file must be a regular path")
    resolved = value.resolve()
    if resolved.is_symlink():
        raise InvalidRequest("endpoint state file must be a regular path")
    repo = Path(__file__).resolve().parents[1]
    forbidden = [repo]
    if os.name == "posix":
        forbidden.append(Path("/workspace"))
    for root in forbidden:
        if resolved == root or root in resolved.parents:
            raise InvalidRequest("endpoint state file must stay off the source tree and the shared volume")
    return resolved


def permissions_are_private(mode: int) -> bool:
    return not (mode & (stat.S_IRWXG | stat.S_IRWXO))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _plain(value: str, limit: int) -> str:
    text = _CONTROL.sub(" ", value).strip()
    text = " ".join(text.split())
    return text[:limit]


def _new_enrolment_code() -> str:
    """24 letters or digits. A leading hyphen is parsed as a command flag."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(24))


def endpoint_label(display_name: str) -> str:
    """Label a fixture or this development PC so it cannot be the second endpoint."""
    folded = " ".join(str(display_name).split()).casefold().rstrip(".")
    if (
        folded == FIXTURE_LABEL
        or folded == _DEV_ENDPOINT_NAME
        or folded.startswith(_DEV_ENDPOINT_NAME + ".")
    ):
        return FIXTURE_LABEL
    return ""


def _check_by_id(report: dict[str, Any] | None, procedure_id: str) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {"status": "not_reported", "summary": ""}
    checks = report.get("checks")
    if not isinstance(checks, list):
        return {"status": "not_reported", "summary": ""}
    for item in checks:
        if isinstance(item, dict) and item.get("procedure_id") == procedure_id:
            source = item.get("evidence_source")
            summary = item.get("summary") if isinstance(item.get("summary"), str) else ""
            return {
                "status": "reported" if source == "live_windows" else "unavailable",
                "summary": summary,
                "ok": bool(item.get("ok")),
            }
    return {"status": "not_reported", "summary": ""}


def diagnostic_sections(report: dict[str, Any] | None) -> dict[str, Any]:
    """OS, disk, network, hardware identity, installed software, and the extra read-only checks."""
    software = _check_by_id(report, "app.browser.inspect")
    if software["status"] == "not_reported":
        software = {
            "status": "not_collected",
            "summary": "Installed software is not part of this check-in.",
        }
    sections: dict[str, Any] = {
        "os": None,
        "disk": None,
        "network": _check_by_id(report, "net.diagnose"),
        "installed_software": software,
        "hardware": _check_by_id(report, "hw.identity.inspect"),
        "read_only_health": {
            procedure_id: _check_by_id(report, procedure_id)
            for procedure_id in HEALTH_PROCEDURE_IDS
        },
        "repair_authority": False,
        "execution": "proposal_only",
    }
    if isinstance(report, dict) and report.get("status") == "ok":
        sections["os"] = {
            "family": report.get("os_family"),
            "version": report.get("os_version"),
        }
        sections["disk"] = {
            "free_bytes": report.get("disk_free_bytes"),
            "total_bytes": report.get("disk_total_bytes"),
            "volumes": _check_by_id(report, "win.storage.space"),
        }
    return sections


def second_endpoint_status(devices: list[dict[str, Any]]) -> str:
    """Say NOT ENROLLED until a non-fixture device has stored a report.

    A fixture label, the name not-the-second-endpoint, and BANYA-FAMILY-PL are
    skipped. A counts_as_second_endpoint flag is not evidence. This does not
    pass the acceptance gate.
    """
    reported = 0
    for device in devices:
        if not isinstance(device, dict):
            continue
        name = str(device.get("display_name") or "")
        if device.get("fixture_label") == FIXTURE_LABEL or endpoint_label(name) == FIXTURE_LABEL:
            continue
        report = device.get("report")
        if not isinstance(report, dict) or report.get("status") != "ok":
            continue
        reported += 1
    if reported == 0:
        return "NOT ENROLLED"
    return f"REPORTED {reported}"


def _check_report_values(report: dict[str, Any]) -> None:
    if report["disk_free_bytes"] > report["disk_total_bytes"]:
        raise InvalidRequest("disk free space cannot exceed disk size")
    if report["boot_time_unix"] > report["collected_at_unix"] + 60:
        raise InvalidRequest("boot time is after the report was collected")


def _hardware_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return _plain(value, limit)


def _clean_hardware(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise InvalidRequest("diagnostic does not match the allowed report")
    if set(raw) - set(_HARDWARE_FIELDS):
        raise InvalidRequest("diagnostic contains a field this connector does not accept")
    return {
        "status": raw.get("status"),
        "manufacturer": _hardware_text(raw.get("manufacturer"), 48),
        "model": _hardware_text(raw.get("model"), 48),
        "bios": _hardware_text(raw.get("bios"), 48),
        "cpu": _hardware_text(raw.get("cpu"), 64),
        "memory_available_bytes": raw.get("memory_available_bytes"),
        "memory_total_bytes": raw.get("memory_total_bytes"),
    }


def _agree_hardware(hardware: dict[str, Any] | None, checks: list[dict[str, Any]] | None) -> None:
    """A collected identity is complete and live. Any other reading is not ok."""
    identity = None
    for item in checks or []:
        if item.get("procedure_id") == "hw.identity.inspect":
            identity = item
    if hardware and hardware.get("status") == "collected":
        if any(not str(hardware.get(key) or "").strip() for key in ("manufacturer", "model", "bios", "cpu")):
            raise InvalidRequest("hardware identity is incomplete")
        available = hardware.get("memory_available_bytes")
        total = hardware.get("memory_total_bytes")
        if isinstance(available, bool) or not isinstance(available, int):
            raise InvalidRequest("hardware memory is missing")
        if isinstance(total, bool) or not isinstance(total, int) or total < 1:
            raise InvalidRequest("hardware memory is missing")
        if available < 0 or available > total:
            raise InvalidRequest("available memory cannot exceed installed memory")
        if identity is None or not identity.get("ok") or identity.get("evidence_source") != "live_windows":
            raise InvalidRequest("complete hardware identity was not reported as a live check")
    if identity and identity.get("ok") and (not hardware or hardware.get("status") != "collected"):
        raise InvalidRequest("a successful hardware check needs a complete identity")


def normalise_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fixed diagnostic fields. Anything else is rejected."""
    if not isinstance(payload, dict):
        raise InvalidRequest("diagnostic must be an object")
    cleaned = {
        "status": "ok",
        "device_id": payload.get("device_id", ""),
        "display_name": payload.get("display_name", ""),
        "os_family": payload.get("os_family", ""),
        "os_version": _plain(str(payload.get("os_version", "")), 80) or "unknown",
        "disk_free_bytes": payload.get("disk_free_bytes"),
        "disk_total_bytes": payload.get("disk_total_bytes"),
        "memory_total_bytes": payload.get("memory_total_bytes"),
        "boot_time_unix": payload.get("boot_time_unix"),
        "collected_at_unix": payload.get("collected_at_unix"),
    }
    if "hardware" in payload:
        cleaned["hardware"] = _clean_hardware(payload.get("hardware"))
    allowed = set(_REPORT["properties"])
    checks = payload.get("checks", None)
    extra = set(payload) - allowed - {"status", "checks"}
    if extra:
        raise InvalidRequest("diagnostic contains a field this connector does not accept")
    try:
        validate(cleaned, _REPORT)
    except ValidationError as exc:
        raise InvalidRequest("diagnostic does not match the allowed report") from exc
    _check_report_values(cleaned)
    if checks is not None:
        cleaned["checks"] = normalise_checks(checks, int(cleaned["collected_at_unix"]))
    _agree_hardware(cleaned.get("hardware"), cleaned.get("checks"))
    return cleaned


def normalise_checks(checks: Any, collected_at: int) -> list[dict[str, Any]]:
    """Keep a bounded read-only diagnostic list. Fixtures and commands are rejected."""
    if not isinstance(checks, list) or len(checks) > _MAX_CHECKS:
        raise InvalidRequest("diagnostic checks are not in the allowed list")
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for item in checks:
        if not isinstance(item, dict):
            raise InvalidRequest("diagnostic checks are not in the allowed list")
        unknown = set(item) - {"procedure_id", "evidence_source", "ok", "collected_at_unix", "summary"}
        if unknown:
            raise InvalidRequest("diagnostic checks contain a field this connector does not accept")
        procedure_id = item.get("procedure_id")
        source = item.get("evidence_source")
        if procedure_id not in _CHECK_PROCEDURES or procedure_id in seen:
            raise InvalidRequest("diagnostic check is not a registered read-only procedure")
        if source not in _CHECK_SOURCES:
            raise InvalidRequest("diagnostic check evidence source is not accepted")
        if not isinstance(item.get("ok"), bool):
            raise InvalidRequest("diagnostic check success flag is missing")
        if source != "live_windows" and item["ok"]:
            raise InvalidRequest("an unavailable check cannot be reported as successful")
        try:
            stamp = int(item.get("collected_at_unix"))
        except (TypeError, ValueError) as exc:
            raise InvalidRequest("diagnostic check time is not valid") from exc
        if abs(stamp - collected_at) > _CHECK_SKEW_SECONDS:
            raise InvalidRequest("diagnostic check time does not match the report")
        summary = _plain(str(item.get("summary", "")), CHECK_SUMMARY_LIMIT)
        if not summary:
            raise InvalidRequest("diagnostic check summary is missing")
        seen.add(procedure_id)
        cleaned.append({
            "procedure_id": procedure_id,
            "evidence_source": source,
            "ok": item["ok"],
            "collected_at_unix": stamp,
            "summary": summary,
        })
    return cleaned


def collect_local_diagnostics(clock: Callable[[], float] = time.time) -> dict[str, Any]:
    """Facts from this computer. No process list, files, screen, or secrets."""
    family = {"windows": "windows", "linux": "linux", "darwin": "darwin"}.get(
        platform.system().lower(), "other",
    )
    anchor = Path.home().anchor or os.sep
    usage = shutil.disk_usage(anchor)
    now = int(clock())
    uptime = _uptime_seconds()
    report = {
        "os_family": family,
        "os_version": _plain(platform.version() or platform.release() or "unknown", 80) or "unknown",
        "disk_free_bytes": int(usage.free),
        "disk_total_bytes": int(usage.total),
        "memory_total_bytes": _memory_total(),
        "boot_time_unix": max(0, now - uptime),
        "collected_at_unix": now,
    }
    return report


def _memory_total() -> int:
    system = platform.system().lower()
    if system == "linux":
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
        raise InvalidRequest("could not read memory size")
    if system == "windows":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        lookup = ctypes.windll.kernel32.GlobalMemoryStatusEx
        lookup.argtypes = [ctypes.POINTER(MemoryStatus)]
        lookup.restype = ctypes.c_int
        if not lookup(ctypes.byref(status)):
            raise InvalidRequest("could not read memory size")
        return int(status.ullTotalPhys)
    raise InvalidRequest("memory size is not collected on this operating system")


def _uptime_seconds() -> int:
    system = platform.system().lower()
    if system == "linux":
        return int(float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0]))
    if system == "windows":
        import ctypes
        get_tick = ctypes.windll.kernel32.GetTickCount64
        get_tick.restype = ctypes.c_ulonglong
        return int(get_tick() // 1000)
    raise InvalidRequest("boot time is not collected on this operating system")


@dataclass
class _Code:
    tenant_id: str
    code_hash: str
    expires_at: float
    used: bool = False


@dataclass
class _Device:
    tenant_id: str
    device_id: str
    display_name: str
    secret_hash: str
    status: str
    created_at: float
    last_report_at: float = 0.0
    report: dict[str, Any] | None = None
    fixture_label: str = ""


class DeviceRegistry:
    """Enrolment codes and device records for one process."""

    def __init__(
        self,
        path: Path | None = None,
        clock: Callable[[], float] = time.time,
        *,
        enforce_permissions: bool | None = None,
    ) -> None:
        self.path = assert_safe_state_path(path) if path is not None else None
        self._clock = clock
        self._enforce = (os.name == "posix") if enforce_permissions is None else enforce_permissions
        self._lock = threading.Lock()
        self._codes: list[_Code] = []
        self._devices: dict[str, _Device] = {}
        self._enrol_failures: list[float] = []
        if self.path is not None and self.path.is_file():
            self._load()

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "DeviceRegistry":
        source = os.environ if environ is None else environ
        raw = source.get("ENDPOINT_STATE_FILE", "").strip()
        if not raw:
            return cls()
        return cls(Path(raw))

    def _prune_enrol_failures(self, now: float) -> None:
        window_start = now - _ENROL_WINDOW_SECONDS
        self._enrol_failures = [stamp for stamp in self._enrol_failures if stamp >= window_start]

    def _register_enrol_failure(self) -> None:
        now = self._clock()
        self._prune_enrol_failures(now)
        self._enrol_failures.append(now)

    def create_enrolment(self, tenant_id: str) -> dict[str, Any]:
        code = _new_enrolment_code()
        with self._lock:
            self._codes.append(_Code(tenant_id, _digest(code), self._clock() + _CODE_TTL))
            self._save()
        from integrations.endpoint_worker import operator_commands

        return {
            "enrolment_code": code,
            "expires_in_seconds": _CODE_TTL,
            "remote_control": False,
            **operator_commands(code),
        }

    def enrol(self, code: str, display_name: str, device_secret: str) -> str:
        if not isinstance(code, str) or len(code) < 16 or len(code) > 80:
            with self._lock:
                self._register_enrol_failure()
            raise AuthenticationError("enrolment code is not valid")
        if not isinstance(display_name, str) or not _NAME.fullmatch(display_name.strip()):
            raise InvalidRequest("display name must be 1 to 40 letters, numbers, spaces, dots, or dashes")
        if not isinstance(device_secret, str) or len(device_secret) < 32 or len(device_secret) > 200:
            raise InvalidRequest("device secret is not acceptable")
        name = display_name.strip()
        digest = _digest(code)
        now = self._clock()
        with self._lock:
            self._prune_enrol_failures(now)
            if len(self._enrol_failures) >= _ENROL_MAX_FAILURES:
                raise RateLimited(
                    "too many failed enrolment attempts; try again later",
                    retry_after=_ENROL_WINDOW_SECONDS,
                )
            match = next((item for item in self._codes if secrets.compare_digest(item.code_hash, digest)), None)
            if match is None or match.used or match.expires_at < now:
                self._register_enrol_failure()
                raise AuthenticationError("enrolment code is not valid")
            match.used = True
            self._enrol_failures.clear()
            device_id = uuid.uuid4().hex
            self._devices[device_id] = _Device(
                tenant_id=match.tenant_id,
                device_id=device_id,
                display_name=name,
                secret_hash=_digest(device_secret),
                status="enrolled",
                created_at=now,
                fixture_label=endpoint_label(name),
            )
            self._save()
        return device_id

    def submit(self, device_secret: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(device_secret, str) or len(device_secret) < 32:
            raise AuthenticationError("device secret was rejected")
        digest = _digest(device_secret)
        with self._lock:
            device = next(
                (item for item in self._devices.values() if secrets.compare_digest(item.secret_hash, digest)),
                None,
            )
            if device is None or device.status != "enrolled":
                raise AuthenticationError("device secret was rejected")
            now = self._clock()
            if device.last_report_at and now - device.last_report_at < _MIN_REPORT_GAP:
                raise RateLimited("a diagnostic was accepted recently", retry_after=_MIN_REPORT_GAP)
            incoming = dict(payload)
            incoming["device_id"] = device.device_id
            incoming["display_name"] = device.display_name
            report = normalise_report(incoming)
            device.report = report
            device.last_report_at = now
            self._save()
        return {"status": "stored", "device_id": device.device_id, "remote_control": False}

    def revoke(self, tenant_id: str, device_id: str) -> None:
        if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id):
            raise InvalidRequest("device id is not valid")
        with self._lock:
            device = self._devices.get(device_id)
            if device is None or device.tenant_id != tenant_id:
                raise AuthenticationError("device was not found for this customer")
            device.status = "revoked"
            self._save()

    def public_devices(self, tenant_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = [item for item in self._devices.values() if item.tenant_id == tenant_id]
        rows.sort(key=lambda item: item.created_at)
        now = self._clock()
        return [_public_device(item, now) for item in rows]

    def public_report(self, tenant_id: str, device_id: str | None) -> dict[str, Any]:
        with self._lock:
            rows = [
                item for item in self._devices.values()
                if item.tenant_id == tenant_id and item.status == "enrolled" and item.report is not None
            ]
            if device_id:
                rows = [item for item in rows if item.device_id == device_id]
        if not rows:
            return {
                "status": "none",
                "detail": "No diagnostic has been received from an enrolled computer.",
            }
        newest = max(rows, key=lambda item: item.last_report_at)
        assert newest.report is not None
        report = dict(newest.report)
        report["repair_authority"] = False
        report["collection_scope"] = "computer_running_the_worker"
        stamp = report.get("collected_at_unix")
        collected = stamp if isinstance(stamp, int) and not isinstance(stamp, bool) else None
        report.update(evidence_timing(collected, self._clock(), has_report=True))
        return report

    def fleet_snapshot(self) -> dict[str, Any]:
        """Counts for the Director. Does not include secrets or report bodies."""
        with self._lock:
            enrolled = [item for item in self._devices.values() if item.status == "enrolled"]
            revoked = sum(1 for item in self._devices.values() if item.status == "revoked")
            newest = max((item.last_report_at for item in enrolled), default=0.0)
            latest = max(enrolled, key=lambda item: item.last_report_at) if newest else None
            checks = list((latest.report or {}).get("checks") or []) if latest and latest.report else []
            has_report = bool(latest and latest.report)
            raw_stamp = (latest.report or {}).get("collected_at_unix") if latest and latest.report else None
            now = self._clock()
        failed = sum(1 for item in checks if not item.get("ok"))
        failed_procedures = [
            str(item.get("procedure_id"))
            for item in checks
            if isinstance(item, dict) and not item.get("ok") and item.get("procedure_id")
        ]
        if checks:
            coverage = "registered"
        elif has_report:
            coverage = "basic"
        else:
            coverage = "none"
        collected = raw_stamp if isinstance(raw_stamp, int) and not isinstance(raw_stamp, bool) else None
        timing = evidence_timing(collected, now, has_report=has_report)
        return {
            "enrolled": len(enrolled),
            "revoked": revoked,
            "last_report_at": newest,
            "repair_authority": False,
            "check_count": len(checks),
            "failed_checks": failed,
            "failed_procedures": failed_procedures[:_MAX_CHECKS],
            "coverage": coverage,
            **timing,
        }

    def enrolled_count(self, tenant_id: str) -> int:
        with self._lock:
            return sum(
                1 for item in self._devices.values()
                if item.tenant_id == tenant_id and item.status == "enrolled"
            )

    def _save(self) -> None:
        if self.path is None:
            return
        payload = {
            "version": 1,
            "codes": [
                {
                    "tenant_id": item.tenant_id,
                    "code_hash": item.code_hash,
                    "expires_at": item.expires_at,
                    "used": item.used,
                }
                for item in self._codes
            ],
            "devices": [
                {
                    "tenant_id": item.tenant_id,
                    "device_id": item.device_id,
                    "display_name": item.display_name,
                    "secret_hash": item.secret_hash,
                    "status": item.status,
                    "created_at": item.created_at,
                    "last_report_at": item.last_report_at,
                    "report": item.report,
                    "fixture_label": item.fixture_label,
                }
                for item in self._devices.values()
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600 if self._enforce else 0o600
        descriptor = os.open(temporary, flags, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        if self._enforce:
            os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)
        if os.name == "nt" or self._enforce:
            try:
                restrict_private(self.path)
            except StatePermissionError as exc:
                raise AuthenticationError("endpoint state file permissions could not be enforced") from exc
        self._mirror_volume_backup()

    def _mirror_volume_backup(self) -> None:
        """Checksum the device list when a volume directory was configured.

        A volume error must not undo the local save and must not block enrolment.
        The Microsoft token and the gateway key are not part of this file.
        """
        if self.path is None:
            return
        try:
            from ops.platform_state import mirror_endpoint_from_env

            mirror_endpoint_from_env(self.path)
        except Exception:
            return

    def _load(self) -> None:
        assert self.path is not None
        info = self.path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise AuthenticationError("endpoint state file is not a regular file")
        if os.name == "nt":
            try:
                assert_private(self.path)
            except StatePermissionError as exc:
                raise AuthenticationError("endpoint state file permissions are too open") from exc
        elif self._enforce and not permissions_are_private(info.st_mode):
            raise AuthenticationError("endpoint state file permissions are too open")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("version") != 1:
            raise AuthenticationError("endpoint state file is not usable")
        self._codes = []
        for item in raw.get("codes") or []:
            if not isinstance(item, dict):
                continue
            self._codes.append(_Code(
                str(item.get("tenant_id", "")),
                str(item.get("code_hash", "")),
                float(item.get("expires_at", 0)),
                bool(item.get("used", False)),
            ))
        self._devices = {}
        for item in raw.get("devices") or []:
            if not isinstance(item, dict):
                continue
            report = item.get("report")
            if report is not None:
                try:
                    report = normalise_report(report)
                except InvalidRequest as exc:
                    raise AuthenticationError("endpoint state file is not usable") from exc
            display_name = str(item["display_name"])
            label = str(item.get("fixture_label") or "")
            if label != FIXTURE_LABEL:
                label = ""
            forced = endpoint_label(display_name)
            if forced:
                label = forced
            device = _Device(
                tenant_id=str(item["tenant_id"]),
                device_id=str(item["device_id"]),
                display_name=display_name,
                secret_hash=str(item["secret_hash"]),
                status=str(item.get("status", "revoked")),
                created_at=float(item.get("created_at", 0)),
                last_report_at=float(item.get("last_report_at", 0)),
                report=report,
                fixture_label=label,
            )
            if device.status not in {"enrolled", "revoked"}:
                device.status = "revoked"
            self._devices[device.device_id] = device


def evidence_timing(collected_at: int | None, now: float, *, has_report: bool) -> dict[str, Any]:
    """Age of a stored diagnostic. Missing or old evidence is stale, never fresh."""
    if not has_report or collected_at is None:
        return {
            "evidence_collected_at": collected_at if has_report else None,
            "evidence_age_seconds": None,
            "evidence_stale": bool(has_report),
        }
    age = int(now - collected_at)
    return {
        "evidence_collected_at": collected_at,
        "evidence_age_seconds": age,
        "evidence_stale": age > _STALE_SECONDS or age < -_FUTURE_SKEW_SECONDS,
    }


def _public_device(item: _Device, now: float) -> dict[str, Any]:
    checks = list((item.report or {}).get("checks") or []) if item.report else []
    if item.report is None:
        coverage = "none"
    elif checks:
        coverage = "registered"
    else:
        coverage = "basic"
    raw_stamp = item.report.get("collected_at_unix") if item.report else None
    collected = raw_stamp if isinstance(raw_stamp, int) and not isinstance(raw_stamp, bool) else None
    timing = evidence_timing(collected, now, has_report=item.report is not None)
    report = None
    if item.report is not None:
        report = {
            **dict(item.report),
            "repair_authority": False,
            "collection_scope": "computer_running_the_worker",
            **timing,
        }
    return {
        "device_id": item.device_id,
        "display_name": item.display_name,
        "status": item.status,
        "remote_control": False,
        "repair_authority": False,
        "last_report_at": item.last_report_at,
        "diagnostic_coverage": coverage,
        "counts_as_second_endpoint": False,
        "fixture_label": item.fixture_label,
        "diagnostics": diagnostic_sections(item.report),
        **timing,
        "report": report,
    }


class EndpointService:
    """Catalog adapter. The model can read a stored report and nothing else."""

    def __init__(self, registry: DeviceRegistry, tenant_id: str = "local-console") -> None:
        self.registry = registry
        self.tenant_id = tenant_id

    def apply(self, catalog: Catalog) -> None:
        record = catalog.connection(self.tenant_id, ENDPOINT.connector_id)
        count = self.registry.enrolled_count(self.tenant_id)
        if count:
            record.connected = True
            record.account = None
            record.granted_scopes = frozenset({"device:read"})
            record.detail = (
                f"{count} enrolled computer(s). The agent can read the latest check-in. "
                "It cannot view the screen or run a repair."
            )
            return
        record.connected = False
        record.account = None
        record.granted_scopes = frozenset()
        record.detail = (
            "No computer is enrolled. Check-in is mock-tested in unit tests and has not "
            "run on the Pod. Remote control is not available."
        )

    def perform(self, connector_id: str, operation: str, params: dict[str, Any]) -> Any:
        if connector_id != ENDPOINT.connector_id or operation != "read_diagnostics":
            raise AuthenticationError("That device operation is not enabled. No command was sent.")
        device_id = params.get("device_id")
        if device_id is not None and not isinstance(device_id, str):
            raise InvalidRequest("device id is not valid")
        return self.registry.public_report(self.tenant_id, device_id)
