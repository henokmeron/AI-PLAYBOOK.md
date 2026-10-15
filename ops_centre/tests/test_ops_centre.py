"""Unit tests for the Operations Centre (no GPU / no Pod)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops_centre.detections import run_detections
from ops_centre.health import HealthAggregator
from ops_centre.models import AlertStatus
from ops_centre.service import OpsCentre, OpsCentreConfig
from ops_centre.store import EventStore


class EventStoreTests(unittest.TestCase):
    def test_hash_chain_and_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.jsonl")
            first = store.append(
                event_type="test.event",
                component="unit",
                outcome="ok",
                summary="hello",
                detail={"api_key": "sk-abcdefghijklmnopqrstuvwxyz", "note": "x"},
            )
            second = store.append(
                event_type="test.event",
                component="unit",
                outcome="ok",
                summary="again",
            )
            self.assertNotEqual(first.hash, second.hash)
            self.assertEqual(second.prev_hash, first.hash)
            self.assertEqual(first.detail.get("api_key"), "[REDACTED]")
            self.assertTrue(store.verify_chain()["ok"])
            reloaded = EventStore(Path(tmp) / "events.jsonl")
            self.assertTrue(reloaded.verify_chain()["ok"])
            self.assertGreaterEqual(len(reloaded.list(limit=10)), 2)


class HealthTests(unittest.TestCase):
    def test_never_healthy_without_probe(self) -> None:
        def probe(url: str, _timeout: float) -> dict:
            if "livez" in url:
                return {"ok": True, "http_status": 200, "detail": "alive", "latency_ms": 1, "body": "{}"}
            if "readyz" in url:
                return {"ok": False, "http_status": 503, "detail": "HTTP 503", "latency_ms": 2, "body": "{}"}
            if "8002" in url:
                return {"ok": False, "http_status": 0, "detail": "unreachable", "latency_ms": 3, "body": ""}
            return {
                "ok": True,
                "http_status": 200,
                "detail": "ok",
                "latency_ms": 1,
                "body": '{"connection":"ready"}',
            }

        agg = HealthAggregator(probe=probe)
        snap = agg.snapshot()
        self.assertEqual(snap["verification"], "observed")
        self.assertIn(snap["overall"], {"degraded", "unavailable"})
        names = {s["name"]: s for s in snap["services"]}
        self.assertEqual(names["qwen"]["state"], "unavailable")
        self.assertEqual(names["gateway_ready"]["state"], "degraded")


class DetectionAlertIncidentTests(unittest.TestCase):
    def test_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = OpsCentre(OpsCentreConfig(data_dir=Path(tmp)))
            for _ in range(3):
                centre.events.append(
                    event_type="agent.task_failed",
                    component="agent",
                    outcome="failed",
                    severity="high",
                    summary="task failed",
                )
            hits = run_detections(centre.events.list(limit=50))
            self.assertTrue(any(h.rule_id == "agent.repeated_failures" for h in hits))
            created = centre.alerts.ingest_hits(hits)
            self.assertGreaterEqual(len(created), 1)
            alert = created[0]
            alert = centre.alerts.transition(
                alert.alert_id, status=AlertStatus.ACKNOWLEDGED.value, actor="tester", note="looking",
            )
            self.assertEqual(alert.status, "acknowledged")
            incident = centre.incidents.create_from_alert(alert, actor="tester")
            self.assertEqual(incident.status, "open")
            report = centre.incidents.report(incident.incident_id)
            self.assertIn("facts", report)
            self.assertTrue(report["facts"])


class OverviewHonestyTests(unittest.TestCase):
    def test_overview_marks_degraded_when_critical_alert_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = OpsCentre(OpsCentreConfig(data_dir=Path(tmp)))

            def fake_snapshot() -> dict:
                return {
                    "overall": "healthy",
                    "verification": "observed",
                    "verified_at": "2026-10-16T00:00:00Z",
                    "services": [],
                    "note": "test",
                }

            with patch.object(centre, "refresh_health", side_effect=lambda: fake_snapshot()):
                centre.events.append(
                    event_type="agent.task_failed",
                    component="agent",
                    outcome="failed",
                    severity="high",
                    summary="a",
                )
                centre.events.append(
                    event_type="agent.task_failed",
                    component="agent",
                    outcome="failed",
                    severity="high",
                    summary="b",
                )
                centre.events.append(
                    event_type="agent.task_failed",
                    component="agent",
                    outcome="failed",
                    severity="high",
                    summary="c",
                )
                overview = centre.overview()
                self.assertNotEqual(overview["overall"], "healthy")


if __name__ == "__main__":
    unittest.main()
