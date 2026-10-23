"""Decide compatibility from catalogue records. Recommendation only.

Unknown is the result when a record is missing, stale, incomplete, or in
conflict with another record. A blank field is never read as compatible.
Install, download, reboot, and firmware update stay disabled: this module
has no procedure and does not open a source URL.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from .records import (
    DEFAULT_FRESHNESS,
    DISABLED_ACTIONS,
    DOCUMENTED_MIN_CONFIDENCE,
    ENABLED_ACTIONS,
    INCOMPATIBLE_MIN_CONFIDENCE,
    LIKELY_MIN_CONFIDENCE,
    VERIFIED_MIN_CONFIDENCE,
    ComponentQuery,
    ComponentRecord,
    Decision,
    SourceType,
)

_POSITIVE = {
    Decision.COMPATIBLE_VERIFIED,
    Decision.COMPATIBLE_DOCUMENTED,
    Decision.LIKELY_COMPATIBLE,
}
_DOCUMENTED_SOURCES = {SourceType.VENDOR_DOCUMENTATION}
_LIKELY_SOURCES = {SourceType.DRIVER_CATALOGUE, SourceType.VENDOR_DOCUMENTATION}
_INCOMPATIBLE_SOURCES = {SourceType.LAB_VERIFICATION, SourceType.VENDOR_DOCUMENTATION}


@dataclass(frozen=True)
class SourceCitation:
    """The catalogue row a decision used. The URL is a citation, not a fetch."""

    record_id: str
    record_version: str
    source_url: str | None
    source_type: str
    retrieved_at: str


@dataclass(frozen=True)
class DecisionResult:
    """A recommendation. ``procedure`` stays empty and live hardware is not claimed."""

    decision: Decision
    why: str
    source_record_ids: tuple[str, ...]
    sources: tuple[SourceCitation, ...]
    recommendation_only: bool = True
    live_machine_claim: bool = False
    procedure: str | None = None
    enabled_actions: tuple[str, ...] = ENABLED_ACTIONS
    disabled_actions: tuple[str, ...] = DISABLED_ACTIONS

    def __post_init__(self) -> None:
        if not isinstance(self.decision, Decision):
            raise ValueError("decision must be a Decision")
        if not self.why.strip():
            raise ValueError("why is required")
        if self.live_machine_claim or not self.recommendation_only or self.procedure is not None:
            raise ValueError("results stay recommendation-only and claim no live machine")
        if self.enabled_actions != ENABLED_ACTIONS:
            raise ValueError("only recommend is enabled")
        if self.disabled_actions != DISABLED_ACTIONS:
            raise ValueError("install, download, reboot, and firmware update stay disabled")


def decide(
    query: ComponentQuery,
    records: Sequence[ComponentRecord],
    *,
    now: datetime,
    freshness: timedelta = DEFAULT_FRESHNESS,
    action: str = "recommend",
) -> DecisionResult:
    """Return one decision for ``query`` using only the records passed in.

    ``now`` is required so freshness does not depend on a hidden clock.
    ``action`` other than ``recommend`` is refused before any record is read.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if freshness <= timedelta(0):
        raise ValueError("freshness window must be positive")

    requested = action.strip().casefold()
    if requested != "recommend":
        label = requested if requested in DISABLED_ACTIONS else "that action"
        return _result(
            Decision.UNSUPPORTED,
            f"{label} stays disabled. This package only returns a recommendation "
            "and has no install, download, reboot, or firmware update path.",
            (),
        )

    missing = _missing_query_fields(query)
    if missing:
        joined = ", ".join(missing)
        return _result(
            Decision.UNKNOWN,
            f"Missing {joined}. Missing evidence stays unknown and is not compatible.",
            (),
        )

    partial = [record for record in records if _core_match(query, record)]
    matched = [record for record in partial if _signer_aligns(query, record)]
    if partial and not matched:
        return _result(
            Decision.UNKNOWN,
            "Driver signer is missing or conflicts, so the matching source cannot be applied. "
            "Missing evidence stays unknown and is not verified.",
            partial,
        )
    if not matched:
        if any(_hardware_match(query, record) for record in records):
            return _result(
                Decision.UNKNOWN,
                "No source record covers this manufacturer, model, driver version, and OS build. "
                "A partial hardware match is not compatible.",
                (),
            )
        return _result(
            Decision.UNKNOWN,
            "No catalogue record matches this hardware id. Missing evidence stays unknown.",
            (),
        )

    fresh = [record for record in matched if _is_fresh(record, now, freshness)]
    stale = [record for record in matched if record not in fresh]
    if not fresh:
        return _result(
            Decision.UNKNOWN,
            "The matching source is stale, so it is not verified. Stale evidence stays unknown.",
            stale,
        )
    if _polarities_conflict(fresh + stale):
        return _result(
            Decision.UNKNOWN,
            "Records disagree about this hardware id, OS, and driver. "
            "Contradictory evidence stays unknown and is not verified.",
            fresh + stale,
        )

    verified = [record for record in fresh if _can_verify(query, record)]
    documented = [record for record in fresh if _can_document(query, record)]
    likely = [record for record in fresh if _can_likely(query, record)]
    incompatible = [record for record in fresh if _can_incompatible(query, record)]
    unsupported = [record for record in fresh if _can_unsupported(query, record)]

    if verified:
        return _result(
            Decision.COMPATIBLE_VERIFIED,
            "Exact match on manufacturer, model, hardware id, driver provider, version, signer, "
            "and OS build and architecture. The lab source is fresh and meets the verification "
            "confidence. The record is synthetic and is not a live machine.",
            verified,
        )
    if documented:
        return _result(
            Decision.COMPATIBLE_DOCUMENTED,
            "Vendor documentation matches this manufacturer, model, hardware id, driver provider, "
            "version, and OS build and architecture. Documentation is not a lab verification. "
            "The record is synthetic and is not a live machine.",
            documented,
        )
    if likely:
        return _result(
            Decision.LIKELY_COMPATIBLE,
            "A driver-catalogue source matches this component and states likely compatibility. "
            "That is weaker than a lab verification. The record is synthetic and is not a live machine.",
            likely,
        )
    if incompatible:
        note = incompatible[0].evidence_note
        return _result(
            Decision.INCOMPATIBLE,
            f"A fresh source records this combination as incompatible. Evidence: {note} "
            "The record is synthetic and is not a live machine.",
            incompatible,
        )
    if unsupported:
        return _result(
            Decision.UNSUPPORTED,
            "A fresh source records this component as unsupported. "
            "The record is synthetic and is not a live machine.",
            unsupported,
        )
    return _result(
        Decision.UNKNOWN,
        "The matching source is fresh but does not meet the evidence gate for a compatibility "
        "decision. Weak or incomplete evidence stays unknown and is not verified.",
        fresh,
    )


def _result(
    decision: Decision,
    reason: str,
    records: Sequence[ComponentRecord],
) -> DecisionResult:
    unique: list[ComponentRecord] = []
    seen: set[str] = set()
    for record in records:
        if record.record_id in seen:
            continue
        seen.add(record.record_id)
        unique.append(record)
    citations = tuple(
        SourceCitation(
            record_id=record.record_id,
            record_version=record.record_version,
            source_url=record.source_url,
            source_type=record.source_type.value,
            retrieved_at=record.retrieved_at.isoformat(),
        )
        for record in unique
    )
    ids = tuple(item.record_id for item in citations)
    why = f"{reason} Source records: {', '.join(ids)}." if ids else reason
    return DecisionResult(
        decision=decision,
        why=why,
        source_record_ids=ids,
        sources=citations,
    )


def _missing_query_fields(query: ComponentQuery) -> list[str]:
    required = (
        ("manufacturer", query.manufacturer),
        ("model", query.model),
        ("hardware id", query.hardware.hardware_id),
        ("driver provider", query.driver.provider),
        ("driver version", query.driver.version),
        ("OS build", query.operating_system.build),
        ("OS architecture", query.operating_system.architecture),
    )
    return [name for name, value in required if value is None]


def _eq(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    return left.casefold() == right.casefold()


def _both_absent_or_equal(left: str | None, right: str | None) -> bool:
    if left is None and right is None:
        return True
    return _eq(left, right)


def _hardware_match(query: ComponentQuery, record: ComponentRecord) -> bool:
    return _eq(query.hardware.hardware_id, record.hardware.hardware_id)


def _core_match(query: ComponentQuery, record: ComponentRecord) -> bool:
    hardware = query.hardware
    recorded = record.hardware
    system = query.operating_system
    recorded_system = record.operating_system
    return (
        _eq(query.manufacturer, record.manufacturer)
        and _eq(query.model, record.model)
        and _eq(hardware.hardware_id, recorded.hardware_id)
        and _both_absent_or_equal(hardware.vendor_id, recorded.vendor_id)
        and _both_absent_or_equal(hardware.device_id, recorded.device_id)
        and _both_absent_or_equal(hardware.subsystem_id, recorded.subsystem_id)
        and _eq(query.driver.provider, record.driver.provider)
        and _eq(query.driver.version, record.driver.version)
        and _eq(system.build, recorded_system.build)
        and _eq(system.architecture, recorded_system.architecture)
    )


def _signer_aligns(query: ComponentQuery, record: ComponentRecord) -> bool:
    return _both_absent_or_equal(query.driver.signer, record.driver.signer)


def _is_fresh(record: ComponentRecord, now: datetime, freshness: timedelta) -> bool:
    if record.retrieved_at > now:
        return False
    return now - record.retrieved_at <= freshness


def _cited(record: ComponentRecord) -> bool:
    return bool(record.source_url and record.record_version and record.evidence_note and record.synthetic)


def _polarity(stated: Decision) -> str | None:
    if stated in _POSITIVE:
        return "compatible"
    if stated is Decision.INCOMPATIBLE:
        return "incompatible"
    if stated is Decision.UNSUPPORTED:
        return "unsupported"
    return None


def _polarities_conflict(records: Sequence[ComponentRecord]) -> bool:
    poles = {pole for record in records if (pole := _polarity(record.stated)) is not None}
    return len(poles) > 1


def _can_verify(query: ComponentQuery, record: ComponentRecord) -> bool:
    return (
        record.stated is Decision.COMPATIBLE_VERIFIED
        and record.source_type is SourceType.LAB_VERIFICATION
        and record.confidence >= VERIFIED_MIN_CONFIDENCE
        and _cited(record)
        and _core_match(query, record)
        and _eq(query.driver.signer, record.driver.signer)
    )


def _can_document(query: ComponentQuery, record: ComponentRecord) -> bool:
    return (
        record.stated is Decision.COMPATIBLE_DOCUMENTED
        and record.source_type in _DOCUMENTED_SOURCES
        and record.confidence >= DOCUMENTED_MIN_CONFIDENCE
        and _cited(record)
        and _core_match(query, record)
        and _signer_aligns(query, record)
    )


def _can_likely(query: ComponentQuery, record: ComponentRecord) -> bool:
    return (
        record.stated is Decision.LIKELY_COMPATIBLE
        and record.source_type in _LIKELY_SOURCES
        and record.confidence >= LIKELY_MIN_CONFIDENCE
        and _cited(record)
        and _core_match(query, record)
        and _signer_aligns(query, record)
    )


def _can_incompatible(query: ComponentQuery, record: ComponentRecord) -> bool:
    return (
        record.stated is Decision.INCOMPATIBLE
        and record.source_type in _INCOMPATIBLE_SOURCES
        and record.confidence >= INCOMPATIBLE_MIN_CONFIDENCE
        and _cited(record)
        and _core_match(query, record)
        and _signer_aligns(query, record)
    )


def _can_unsupported(query: ComponentQuery, record: ComponentRecord) -> bool:
    return (
        record.stated is Decision.UNSUPPORTED
        and _cited(record)
        and record.confidence >= LIKELY_MIN_CONFIDENCE
        and _core_match(query, record)
        and _signer_aligns(query, record)
    )
