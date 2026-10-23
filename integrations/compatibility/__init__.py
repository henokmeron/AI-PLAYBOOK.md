"""Recommendation-only hardware and driver compatibility.

Catalogue rows shipped here are synthetic. They are not a scan of a live PC.
Decisions do not install, download, reboot, or update firmware.
"""
from __future__ import annotations

from .catalogue import SYN_AUDIO_9, SYN_GPU_1000, SYN_NIC_200, SYNTHETIC_CATALOGUE, recommend
from .decide import DecisionResult, SourceCitation, decide
from .records import (
    DEFAULT_FRESHNESS,
    DISABLED_ACTIONS,
    ENABLED_ACTIONS,
    ComponentQuery,
    ComponentRecord,
    Decision,
    DriverIdentity,
    HardwareIdentity,
    OperatingSystem,
    SourceType,
    query_from_record,
)

__all__ = [
    "DEFAULT_FRESHNESS",
    "DISABLED_ACTIONS",
    "ENABLED_ACTIONS",
    "SYNTHETIC_CATALOGUE",
    "SYN_AUDIO_9",
    "SYN_GPU_1000",
    "SYN_NIC_200",
    "ComponentQuery",
    "ComponentRecord",
    "Decision",
    "DecisionResult",
    "DriverIdentity",
    "HardwareIdentity",
    "OperatingSystem",
    "SourceCitation",
    "SourceType",
    "decide",
    "query_from_record",
    "recommend",
]
