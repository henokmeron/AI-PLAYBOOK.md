"""Shared enums and dataclasses for the Operations Centre."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    UNKNOWN = "unknown"


class Verification(str, Enum):
    """How much we trust a status claim."""

    OBSERVED = "observed"  # Fresh probe or recorded platform signal
    INFERRED = "inferred"  # Derived from other signals
    UNKNOWN = "unknown"  # Not checked yet / check failed to run


class ServiceState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class AlertStatus(str, Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    REOPENED = "reopened"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class OpsEvent:
    event_id: str
    at: str  # ISO-8601 UTC
    event_type: str
    component: str
    outcome: str
    severity: str = Severity.INFO.value
    tenant_id: str = "local-console"
    correlation_id: str | None = None
    actor: str | None = None
    summary: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    verification: str = Verification.OBSERVED.value
    prev_hash: str = ""
    hash: str = ""

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ServiceHealth:
    name: str
    state: str
    verification: str
    verified_at: str | None
    latency_ms: int | None = None
    http_status: int | None = None
    detail: str = ""
    check_kind: str = "liveness"  # liveness | readiness | functional

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Alert:
    alert_id: str
    rule_id: str
    rule_version: str
    title: str
    severity: str
    status: str
    created_at: str
    updated_at: str
    tenant_id: str = "local-console"
    evidence: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    confidence: str = "medium"
    owner: str | None = None
    ack_note: str = ""
    resolution: str = ""
    fingerprint: str = ""

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SecurityIncident:
    incident_id: str
    title: str
    severity: str
    status: str
    created_at: str
    updated_at: str
    tenant_id: str = "local-console"
    detection_source: str = ""
    alert_ids: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    resolution_summary: str = ""
    lessons_learned: str = ""

    def to_public(self) -> dict[str, Any]:
        return asdict(self)
