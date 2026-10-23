"""Synthetic component records for a recommendation-only compatibility catalogue.

Fields are kept when a source supplies them. Absence stays absence: the
decision function must not treat a blank as evidence of compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class Decision(str, Enum):
    """Compatibility outcomes. ``unknown`` is the fail-closed default."""

    COMPATIBLE_VERIFIED = "compatible_verified"
    COMPATIBLE_DOCUMENTED = "compatible_documented"
    LIKELY_COMPATIBLE = "likely_compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class SourceType(str, Enum):
    """Kind of evidence a record claims to be. This package never fetches it."""

    LAB_VERIFICATION = "lab_verification"
    VENDOR_DOCUMENTATION = "vendor_documentation"
    DRIVER_CATALOGUE = "driver_catalogue"


# A lab row can support compatible_verified only at or above this confidence.
VERIFIED_MIN_CONFIDENCE = 0.9
# Vendor documentation can support compatible_documented, not verified.
DOCUMENTED_MIN_CONFIDENCE = 0.75
# A driver-catalogue row can support likely_compatible and nothing stronger.
LIKELY_MIN_CONFIDENCE = 0.5
# Incompatible also needs positive evidence, not a missing row.
INCOMPATIBLE_MIN_CONFIDENCE = 0.75
# Older than this, a source is not fresh and cannot verify a match.
DEFAULT_FRESHNESS = timedelta(days=90)

ENABLED_ACTIONS = ("recommend",)
DISABLED_ACTIONS = ("install", "download", "reboot", "firmware_update")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


@dataclass(frozen=True)
class HardwareIdentity:
    """Hardware ids captured when a source published them."""

    hardware_id: str | None = None
    vendor_id: str | None = None
    device_id: str | None = None
    subsystem_id: str | None = None

    def normalised(self) -> HardwareIdentity:
        def upper(value: str | None) -> str | None:
            cleaned = _clean(value)
            return cleaned.upper() if cleaned is not None else None

        return HardwareIdentity(
            hardware_id=upper(self.hardware_id),
            vendor_id=upper(self.vendor_id),
            device_id=upper(self.device_id),
            subsystem_id=upper(self.subsystem_id),
        )


@dataclass(frozen=True)
class DriverIdentity:
    """Driver provider, version, and signer. Any of them may be absent."""

    provider: str | None = None
    version: str | None = None
    signer: str | None = None

    def normalised(self) -> DriverIdentity:
        return DriverIdentity(
            provider=_clean(self.provider),
            version=_clean(self.version),
            signer=_clean(self.signer),
        )


@dataclass(frozen=True)
class OperatingSystem:
    """OS build and architecture the record applies to."""

    build: str | None = None
    architecture: str | None = None

    def normalised(self) -> OperatingSystem:
        return OperatingSystem(build=_clean(self.build), architecture=_clean(self.architecture))


@dataclass(frozen=True)
class ComponentQuery:
    """The component a caller asks about. This is not evidence."""

    manufacturer: str | None = None
    model: str | None = None
    hardware: HardwareIdentity = HardwareIdentity()
    driver: DriverIdentity = DriverIdentity()
    operating_system: OperatingSystem = OperatingSystem()

    def __post_init__(self) -> None:
        object.__setattr__(self, "manufacturer", _clean(self.manufacturer))
        object.__setattr__(self, "model", _clean(self.model))
        object.__setattr__(self, "hardware", self.hardware.normalised())
        object.__setattr__(self, "driver", self.driver.normalised())
        object.__setattr__(self, "operating_system", self.operating_system.normalised())


@dataclass(frozen=True)
class ComponentRecord:
    """One catalogue row. ``synthetic`` must stay true in this package."""

    record_id: str
    manufacturer: str | None
    model: str | None
    hardware: HardwareIdentity
    driver: DriverIdentity
    operating_system: OperatingSystem
    source_url: str | None
    source_type: SourceType
    retrieved_at: datetime
    record_version: str
    confidence: float
    stated: Decision
    evidence_note: str
    synthetic: bool = True

    def __post_init__(self) -> None:
        record_id = _clean(self.record_id)
        if not record_id:
            raise ValueError("record_id is required")
        if not self.synthetic:
            raise ValueError("this package only accepts synthetic catalogue records")
        if not isinstance(self.source_type, SourceType):
            raise ValueError("source_type must be a SourceType")
        if not isinstance(self.stated, Decision):
            raise ValueError("stated must be a Decision")
        _aware(self.retrieved_at, "retrieved_at")
        record_version = _clean(self.record_version)
        if not record_version:
            raise ValueError("record_version is required")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("confidence must be a number from 0 to 1")
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be from 0 to 1")
        evidence_note = _clean(self.evidence_note)
        if not evidence_note:
            raise ValueError("evidence_note is required")
        object.__setattr__(self, "record_id", record_id)
        object.__setattr__(self, "record_version", record_version)
        object.__setattr__(self, "manufacturer", _clean(self.manufacturer))
        object.__setattr__(self, "model", _clean(self.model))
        object.__setattr__(self, "hardware", self.hardware.normalised())
        object.__setattr__(self, "driver", self.driver.normalised())
        object.__setattr__(self, "operating_system", self.operating_system.normalised())
        object.__setattr__(self, "source_url", _clean(self.source_url))
        object.__setattr__(self, "evidence_note", evidence_note)
        object.__setattr__(self, "confidence", float(self.confidence))


def query_from_record(record: ComponentRecord) -> ComponentQuery:
    """Copy the identity fields of a catalogue row into a query."""
    return ComponentQuery(
        manufacturer=record.manufacturer,
        model=record.model,
        hardware=record.hardware,
        driver=record.driver,
        operating_system=record.operating_system,
    )
