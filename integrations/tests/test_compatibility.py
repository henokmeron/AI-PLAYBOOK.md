"""Recommendation-only compatibility decisions. No network and no live PC."""
from __future__ import annotations

import ast
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from integrations.compatibility import (
    DISABLED_ACTIONS,
    SYN_AUDIO_9,
    SYN_GPU_1000,
    SYN_NIC_200,
    SYNTHETIC_CATALOGUE,
    ComponentRecord,
    Decision,
    DriverIdentity,
    SourceType,
    decide,
    query_from_record,
    recommend,
)

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
PACKAGE = Path(__file__).resolve().parents[1] / "compatibility"
_BANNED_MODULES = {"urllib", "requests", "httpx", "socket", "subprocess", "webbrowser", "ctypes", "winreg"}
_BANNED_FUNCTION_WORDS = ("install", "download", "reboot", "firmware")
_POSITIVE = {
    Decision.COMPATIBLE_VERIFIED,
    Decision.COMPATIBLE_DOCUMENTED,
    Decision.LIKELY_COMPATIBLE,
}


def _blocked_open(*_args, **_kwargs):
    raise AssertionError("compatibility tests must not open a URL")


class CompatibilityDecisionTests(unittest.TestCase):
    def test_exact_match_is_verified(self) -> None:
        result = recommend(query_from_record(SYN_GPU_1000), now=NOW)
        self.assertEqual(result.decision, Decision.COMPATIBLE_VERIFIED)
        self.assertEqual(result.source_record_ids, (SYN_GPU_1000.record_id,))
        self.assertEqual(result.sources[0].record_version, SYN_GPU_1000.record_version)
        self.assertEqual(result.sources[0].source_type, SourceType.LAB_VERIFICATION.value)
        self.assertIn("exact match", result.why.casefold())
        self.assertIn("synthetic", result.why.casefold())
        self._assert_recommendation_only(result)

    def test_documented_match_is_not_verified(self) -> None:
        result = recommend(query_from_record(SYN_NIC_200), now=NOW)
        self.assertEqual(result.decision, Decision.COMPATIBLE_DOCUMENTED)
        self.assertNotEqual(result.decision, Decision.COMPATIBLE_VERIFIED)
        self.assertEqual(result.source_record_ids, (SYN_NIC_200.record_id,))
        self.assertEqual(result.sources[0].source_type, SourceType.VENDOR_DOCUMENTATION.value)
        self.assertIn("documentation", result.why.casefold())
        self._assert_recommendation_only(result)

    def test_incompatible_cites_evidence(self) -> None:
        result = recommend(query_from_record(SYN_AUDIO_9), now=NOW)
        self.assertEqual(result.decision, Decision.INCOMPATIBLE)
        self.assertEqual(result.source_record_ids, (SYN_AUDIO_9.record_id,))
        self.assertIn("0.9.0.0", result.why)
        self.assertIn("Fabrikam Synthetic Bad Signer", result.why)
        self.assertIn(SYN_AUDIO_9.record_id, result.why)
        self._assert_recommendation_only(result)

    def test_missing_record_is_unknown(self) -> None:
        query = query_from_record(SYN_GPU_1000)
        missing = query.__class__(
            manufacturer=query.manufacturer,
            model="SYN-GPU-MISSING",
            hardware=query.hardware.__class__(
                hardware_id=r"PCI\VEN_F00D&DEV_DEAD&SUBSYS_SYNDEAD",
                vendor_id="F00D",
                device_id="DEAD",
                subsystem_id="SYNDEAD",
            ),
            driver=query.driver,
            operating_system=query.operating_system,
        )
        result = recommend(missing, now=NOW)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertEqual(result.source_record_ids, ())
        self.assertIn("no catalogue record", result.why.casefold())
        self.assertNotIn(result.decision, _POSITIVE)
        self._assert_recommendation_only(result)

    def test_stale_source_is_not_verified(self) -> None:
        stale = ComponentRecord(
            record_id="syn-gpu-1000-lab-stale",
            manufacturer=SYN_GPU_1000.manufacturer,
            model=SYN_GPU_1000.model,
            hardware=SYN_GPU_1000.hardware,
            driver=SYN_GPU_1000.driver,
            operating_system=SYN_GPU_1000.operating_system,
            source_url=SYN_GPU_1000.source_url,
            source_type=SYN_GPU_1000.source_type,
            retrieved_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            record_version="2025-01-01.1",
            confidence=SYN_GPU_1000.confidence,
            stated=Decision.COMPATIBLE_VERIFIED,
            evidence_note="Synthetic stale lab row. Not a live PC.",
        )
        result = decide(query_from_record(SYN_GPU_1000), (stale,), now=NOW)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertNotEqual(result.decision, Decision.COMPATIBLE_VERIFIED)
        self.assertEqual(result.source_record_ids, ("syn-gpu-1000-lab-stale",))
        self.assertIn("stale", result.why.casefold())
        self.assertIn("not verified", result.why.casefold())
        self._assert_recommendation_only(result)

    def test_contradictory_records_are_unknown(self) -> None:
        conflict = ComponentRecord(
            record_id="syn-gpu-1000-lab-conflict",
            manufacturer=SYN_GPU_1000.manufacturer,
            model=SYN_GPU_1000.model,
            hardware=SYN_GPU_1000.hardware,
            driver=SYN_GPU_1000.driver,
            operating_system=SYN_GPU_1000.operating_system,
            source_url="https://catalogue.invalid/synthetic/syn-gpu-1000/conflict/v1",
            source_type=SourceType.LAB_VERIFICATION,
            retrieved_at=SYN_GPU_1000.retrieved_at,
            record_version="2026-10-01.9",
            confidence=0.93,
            stated=Decision.INCOMPATIBLE,
            evidence_note="Synthetic opposing lab row for the same driver. Not a live PC.",
        )
        result = decide(
            query_from_record(SYN_GPU_1000),
            (SYN_GPU_1000, conflict),
            now=NOW,
        )
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertNotIn(result.decision, _POSITIVE)
        self.assertNotEqual(result.decision, Decision.INCOMPATIBLE)
        self.assertCountEqual(
            result.source_record_ids,
            [SYN_GPU_1000.record_id, conflict.record_id],
        )
        self.assertIn("contradict", result.why.casefold())
        self._assert_recommendation_only(result)

    def test_missing_signer_is_not_compatible(self) -> None:
        query = query_from_record(SYN_GPU_1000)
        unsigned = query.__class__(
            manufacturer=query.manufacturer,
            model=query.model,
            hardware=query.hardware,
            driver=DriverIdentity(
                provider=query.driver.provider,
                version=query.driver.version,
                signer=None,
            ),
            operating_system=query.operating_system,
        )
        result = decide(unsigned, SYNTHETIC_CATALOGUE, now=NOW)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertNotIn(result.decision, _POSITIVE)
        self.assertEqual(result.source_record_ids, (SYN_GPU_1000.record_id,))
        self.assertIn("signer", result.why.casefold())
        self._assert_recommendation_only(result)

    def test_weak_confidence_is_not_verified(self) -> None:
        weak = ComponentRecord(
            record_id="syn-gpu-1000-lab-weak",
            manufacturer=SYN_GPU_1000.manufacturer,
            model=SYN_GPU_1000.model,
            hardware=SYN_GPU_1000.hardware,
            driver=SYN_GPU_1000.driver,
            operating_system=SYN_GPU_1000.operating_system,
            source_url=SYN_GPU_1000.source_url,
            source_type=SourceType.LAB_VERIFICATION,
            retrieved_at=SYN_GPU_1000.retrieved_at,
            record_version="2026-10-01.4",
            confidence=0.5,
            stated=Decision.COMPATIBLE_VERIFIED,
            evidence_note="Synthetic low-confidence lab row. Not a live PC.",
        )
        result = decide(query_from_record(SYN_GPU_1000), (weak,), now=NOW)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertNotEqual(result.decision, Decision.COMPATIBLE_VERIFIED)
        self.assertEqual(result.source_record_ids, (weak.record_id,))
        self._assert_recommendation_only(result)

    def test_likely_catalogue_match_stays_likely(self) -> None:
        likely = ComponentRecord(
            record_id="syn-gpu-1000-catalogue-likely",
            manufacturer=SYN_GPU_1000.manufacturer,
            model=SYN_GPU_1000.model,
            hardware=SYN_GPU_1000.hardware,
            driver=DriverIdentity(
                provider=SYN_GPU_1000.driver.provider,
                version=SYN_GPU_1000.driver.version,
                signer=None,
            ),
            operating_system=SYN_GPU_1000.operating_system,
            source_url="https://catalogue.invalid/synthetic/syn-gpu-1000/likely/v1",
            source_type=SourceType.DRIVER_CATALOGUE,
            retrieved_at=SYN_GPU_1000.retrieved_at,
            record_version="2026-10-01.5",
            confidence=0.6,
            stated=Decision.LIKELY_COMPATIBLE,
            evidence_note="Synthetic driver catalogue row. Not a live PC.",
        )
        result = decide(query_from_record(likely), (likely,), now=NOW)
        self.assertEqual(result.decision, Decision.LIKELY_COMPATIBLE)
        self.assertNotEqual(result.decision, Decision.COMPATIBLE_VERIFIED)
        self.assertEqual(result.source_record_ids, (likely.record_id,))
        self._assert_recommendation_only(result)

    def test_disabled_actions_stay_unsupported(self) -> None:
        query = query_from_record(SYN_GPU_1000)
        for action in DISABLED_ACTIONS:
            result = decide(query, SYNTHETIC_CATALOGUE, now=NOW, action=action)
            self.assertEqual(result.decision, Decision.UNSUPPORTED, action)
            self.assertEqual(result.source_record_ids, (), action)
            self.assertIsNone(result.procedure, action)
            self.assertIn("disabled", result.why.casefold())
            self.assertNotIn(result.decision, _POSITIVE)
            self._assert_recommendation_only(result)

    def test_fixtures_are_synthetic_and_claim_no_live_pc(self) -> None:
        self.assertEqual(len(SYNTHETIC_CATALOGUE), 3)
        self.assertEqual(
            {item.record_id for item in SYNTHETIC_CATALOGUE},
            {SYN_GPU_1000.record_id, SYN_NIC_200.record_id, SYN_AUDIO_9.record_id},
        )
        for record in SYNTHETIC_CATALOGUE:
            self.assertTrue(record.synthetic)
            self.assertIn("synthetic", record.evidence_note.casefold())
            self.assertIn("not a live", record.evidence_note.casefold())
            self.assertIsNotNone(record.source_url)
            assert record.source_url is not None
            self.assertTrue(record.source_url.startswith("https://catalogue.invalid/synthetic/"))
            self.assertIsNotNone(record.retrieved_at.tzinfo)
            self.assertGreater(len(record.record_version), 0)
        self.assertEqual(
            {Decision.COMPATIBLE_VERIFIED, Decision.COMPATIBLE_DOCUMENTED, Decision.LIKELY_COMPATIBLE,
             Decision.INCOMPATIBLE, Decision.UNKNOWN, Decision.UNSUPPORTED},
            set(Decision),
        )

    def test_package_does_not_call_the_network(self) -> None:
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], _BANNED_MODULES, path.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0], _BANNED_MODULES, path.name)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lowered = node.name.casefold()
                    for word in _BANNED_FUNCTION_WORDS:
                        self.assertNotIn(word, lowered, node.name)
        with mock.patch.object(urllib.request, "urlopen", _blocked_open):
            for record in SYNTHETIC_CATALOGUE:
                recommend(query_from_record(record), now=NOW)

    def test_records_reject_live_or_naive_evidence(self) -> None:
        with self.assertRaises(ValueError):
            ComponentRecord(
                record_id="syn-live-rejected",
                manufacturer=SYN_GPU_1000.manufacturer,
                model=SYN_GPU_1000.model,
                hardware=SYN_GPU_1000.hardware,
                driver=SYN_GPU_1000.driver,
                operating_system=SYN_GPU_1000.operating_system,
                source_url=SYN_GPU_1000.source_url,
                source_type=SourceType.LAB_VERIFICATION,
                retrieved_at=SYN_GPU_1000.retrieved_at,
                record_version="2026-10-01.8",
                confidence=0.99,
                stated=Decision.COMPATIBLE_VERIFIED,
                evidence_note="Synthetic row marked live, which this package refuses.",
                synthetic=False,
            )
        with self.assertRaises(ValueError):
            ComponentRecord(
                record_id="syn-naive-time",
                manufacturer=SYN_GPU_1000.manufacturer,
                model=SYN_GPU_1000.model,
                hardware=SYN_GPU_1000.hardware,
                driver=SYN_GPU_1000.driver,
                operating_system=SYN_GPU_1000.operating_system,
                source_url=SYN_GPU_1000.source_url,
                source_type=SourceType.LAB_VERIFICATION,
                retrieved_at=datetime(2026, 10, 1, 12, 0),
                record_version="2026-10-01.8",
                confidence=0.95,
                stated=Decision.COMPATIBLE_VERIFIED,
                evidence_note="Synthetic row with a naive timestamp.",
            )

    def test_freshness_boundary_is_not_stale_on_the_exact_day(self) -> None:
        on_the_day = ComponentRecord(
            record_id="syn-gpu-1000-lab-boundary",
            manufacturer=SYN_GPU_1000.manufacturer,
            model=SYN_GPU_1000.model,
            hardware=SYN_GPU_1000.hardware,
            driver=SYN_GPU_1000.driver,
            operating_system=SYN_GPU_1000.operating_system,
            source_url=SYN_GPU_1000.source_url,
            source_type=SourceType.LAB_VERIFICATION,
            retrieved_at=NOW - timedelta(days=90),
            record_version="2026-07-25.1",
            confidence=0.95,
            stated=Decision.COMPATIBLE_VERIFIED,
            evidence_note="Synthetic lab row retrieved on the freshness boundary. Not a live PC.",
        )
        fresh = decide(query_from_record(SYN_GPU_1000), (on_the_day,), now=NOW)
        self.assertEqual(fresh.decision, Decision.COMPATIBLE_VERIFIED)
        just_over = ComponentRecord(
            record_id="syn-gpu-1000-lab-just-over",
            manufacturer=on_the_day.manufacturer,
            model=on_the_day.model,
            hardware=on_the_day.hardware,
            driver=on_the_day.driver,
            operating_system=on_the_day.operating_system,
            source_url=on_the_day.source_url,
            source_type=on_the_day.source_type,
            retrieved_at=NOW - timedelta(days=90, seconds=1),
            record_version="2026-07-25.0",
            confidence=0.95,
            stated=Decision.COMPATIBLE_VERIFIED,
            evidence_note="Synthetic lab row one second past the freshness window. Not a live PC.",
        )
        stale = decide(query_from_record(SYN_GPU_1000), (just_over,), now=NOW)
        self.assertEqual(stale.decision, Decision.UNKNOWN)

    def _assert_recommendation_only(self, result) -> None:
        self.assertTrue(result.recommendation_only)
        self.assertFalse(result.live_machine_claim)
        self.assertIsNone(result.procedure)
        self.assertEqual(result.enabled_actions, ("recommend",))
        self.assertEqual(result.disabled_actions, DISABLED_ACTIONS)


if __name__ == "__main__":
    unittest.main()
