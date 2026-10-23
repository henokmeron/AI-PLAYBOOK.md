"""Three synthetic catalogue rows.

These rows are not an inventory of any computer. Source URLs use the
``.invalid`` domain and are citations only. Nothing in this module fetches
them or installs a driver.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .decide import DecisionResult, decide
from .records import (
    ComponentQuery,
    ComponentRecord,
    Decision,
    DriverIdentity,
    HardwareIdentity,
    OperatingSystem,
    SourceType,
)

_RETRIEVED = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
_OS = OperatingSystem(build="26100.6899", architecture="x64")

SYN_GPU_1000 = ComponentRecord(
    record_id="syn-gpu-1000-lab-2026-10-01",
    manufacturer="Northwind Synthetic Devices",
    model="SYN-GPU-1000",
    hardware=HardwareIdentity(
        hardware_id=r"PCI\VEN_F00D&DEV_1000&SUBSYS_SYN0001",
        vendor_id="F00D",
        device_id="1000",
        subsystem_id="SYN0001",
    ),
    driver=DriverIdentity(
        provider="Northwind Synthetic Driver Laboratory",
        version="1.2.3.4",
        signer="CN=Northwind Synthetic Test Signer, O=Synthetic Only, C=XX",
    ),
    operating_system=_OS,
    source_url="https://catalogue.invalid/synthetic/syn-gpu-1000/lab-verification/v1",
    source_type=SourceType.LAB_VERIFICATION,
    retrieved_at=_RETRIEVED,
    record_version="2026-10-01.1",
    confidence=0.95,
    stated=Decision.COMPATIBLE_VERIFIED,
    evidence_note=(
        "Synthetic lab row for SYN-GPU-1000 on build 26100.6899. Not a live PC."
    ),
    synthetic=True,
)

SYN_NIC_200 = ComponentRecord(
    record_id="syn-nic-200-doc-2026-10-01",
    manufacturer="Contoso Synthetic Networks",
    model="SYN-NIC-200",
    hardware=HardwareIdentity(
        hardware_id=r"PCI\VEN_F00D&DEV_0200&SUBSYS_SYN0200",
        vendor_id="F00D",
        device_id="0200",
        subsystem_id="SYN0200",
    ),
    driver=DriverIdentity(
        provider="Contoso Synthetic NDIS",
        version="10.0.0.1",
        signer=None,
    ),
    operating_system=_OS,
    source_url="https://catalogue.invalid/synthetic/syn-nic-200/vendor-note/v3",
    source_type=SourceType.VENDOR_DOCUMENTATION,
    retrieved_at=_RETRIEVED,
    record_version="2026-10-01.3",
    confidence=0.8,
    stated=Decision.COMPATIBLE_DOCUMENTED,
    evidence_note=(
        "Synthetic vendor note for SYN-NIC-200 driver 10.0.0.1 on build 26100.6899. "
        "The note does not name a signer. Not a live driver inventory."
    ),
    synthetic=True,
)

SYN_AUDIO_9 = ComponentRecord(
    record_id="syn-audio-9-evidence-2026-10-01",
    manufacturer="Fabrikam Synthetic Audio",
    model="SYN-AUDIO-9",
    hardware=HardwareIdentity(
        hardware_id=r"PCI\VEN_F00D&DEV_0900&SUBSYS_SYN0900",
        vendor_id="F00D",
        device_id="0900",
        subsystem_id="SYN0900",
    ),
    driver=DriverIdentity(
        provider="Fabrikam Synthetic Audio",
        version="0.9.0.0",
        signer="CN=Fabrikam Synthetic Bad Signer, O=Synthetic Only, C=XX",
    ),
    operating_system=_OS,
    source_url="https://catalogue.invalid/synthetic/syn-audio-9/incompatible/v2",
    source_type=SourceType.LAB_VERIFICATION,
    retrieved_at=_RETRIEVED,
    record_version="2026-10-01.2",
    confidence=0.92,
    stated=Decision.INCOMPATIBLE,
    evidence_note=(
        "Synthetic evidence: driver 0.9.0.0 signed by CN=Fabrikam Synthetic Bad Signer "
        "fails the catalogue check on build 26100.6899 x64. Not a live PC."
    ),
    synthetic=True,
)

SYNTHETIC_CATALOGUE: tuple[ComponentRecord, ...] = (SYN_GPU_1000, SYN_NIC_200, SYN_AUDIO_9)


def recommend(
    query: ComponentQuery,
    *,
    now: datetime,
    action: str = "recommend",
) -> DecisionResult:
    """Decide ``query`` against the synthetic catalogue only."""
    return decide(query, SYNTHETIC_CATALOGUE, now=now, action=action)
