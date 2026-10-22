"""Unit tests for the Operations Centre (no GPU / no Pod)."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from ops_centre.detections import run_detections
from ops_centre.health import HealthAggregator, _http_probe
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

    def test_off_loopback_probe_is_not_healthy_and_is_not_called(self) -> None:
        secret = "secret-token-must-not-print"
        called: list[str] = []

        def probe(url: str, _timeout: float) -> dict:
            called.append(url)
            if secret in url or "example.com" in url:
                raise AssertionError("off-loopback probe was called")
            return {"ok": True, "http_status": 200, "detail": "ok", "latency_ms": 1, "body": '{"connection":"ready"}'}

        agg = HealthAggregator(
            qwen_url=f"http://example.com/health?token={secret}",
            gateway_live_url="http://127.0.0.1:8010/livez",
            gateway_ready_url="http://127.0.0.1:8010/readyz",
            console_url="http://127.0.0.1:8080/api/status",
            probe=probe,
        )
        snap = agg.snapshot()
        names = {s["name"]: s for s in snap["services"]}
        self.assertEqual(names["qwen"]["state"], "unavailable")
        self.assertEqual(names["qwen"]["detail"], "probe URL is not loopback http")
        self.assertNotIn(secret, json.dumps(snap))
        self.assertNotIn("example.com", json.dumps(snap))
        self.assertTrue(called)
        self.assertTrue(all(url.startswith("http://127.0.0.1:") for url in called))

    def test_redirect_is_refused_without_reading_the_target(self) -> None:
        hits = {"secret": 0}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/secret":
                    hits["secret"] += 1
                    body = b"hidden"
                    self.send_response(200)
                else:
                    body = b""
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_address[1]}/secret")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            result = _http_probe(f"http://127.0.0.1:{port}/health", 2.0)
        finally:
            server.shutdown()
            server.server_close()
        self.assertFalse(result["ok"])
        self.assertEqual(result["detail"], "redirect refused")
        self.assertEqual(hits["secret"], 0)
        self.assertNotIn("secret", result["detail"])

    def test_status_body_longer_than_400_bytes_stays_valid_json(self) -> None:
        payload = {
            "ui": "ok",
            "connection": "ready",
            "detail": "gateway " + ("ready " * 80),
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.assertGreater(len(encoded), 400)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            result = _http_probe(f"http://127.0.0.1:{port}/api/status", 2.0)
        finally:
            server.shutdown()
            server.server_close()
        self.assertTrue(result["ok"])
        parsed = json.loads(result["body"])
        self.assertEqual(parsed["connection"], "ready")
        self.assertGreater(len(result["body"].encode("utf-8")), 400)

    def test_off_pod_body_is_not_copied_forward_as_healthy(self) -> None:
        def probe(url: str, _timeout: float) -> dict:
            if "8002" in url:
                body = json.dumps({"status": "ok", "reason": "model_engine_dead"})
            elif "readyz" in url:
                body = json.dumps({
                    "status": "not_ready",
                    "reason": "model_engine_dead",
                    "health": {"status": "ok", "upstream": "ok"},
                })
            elif "livez" in url:
                return {"ok": True, "http_status": 200, "detail": "alive", "latency_ms": 1, "body": "{}"}
            else:
                body = json.dumps({
                    "connection": "ready",
                    "upstream": "unavailable",
                    "pod": "stopped",
                    "health": {"status": "ok", "upstream": "ok"},
                })
            return {"ok": True, "http_status": 200, "detail": "HTTP 200", "latency_ms": 1, "body": body}

        snap = HealthAggregator(probe=probe).snapshot()
        names = {item["name"]: item for item in snap["services"]}
        self.assertEqual(names["qwen"]["state"], "unavailable")
        self.assertEqual(names["gateway_ready"]["state"], "degraded")
        self.assertEqual(names["console"]["state"], "unavailable")
        self.assertIn("not copied forward", names["console"]["detail"])
        self.assertIn("not copied forward", names["qwen"]["detail"])
        self.assertNotEqual(snap["overall"], "healthy")
        self.assertEqual(names["gateway_live"]["state"], "healthy")


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

    def test_historical_high_alert_stays_open_without_forcing_degraded(self) -> None:
        from ops_centre.detections import DetectionHit

        with tempfile.TemporaryDirectory() as tmp:
            centre = OpsCentre(OpsCentreConfig(data_dir=Path(tmp)))

            def fake_snapshot() -> dict:
                return {
                    "overall": "healthy",
                    "verification": "observed",
                    "verified_at": "2026-10-21T22:00:00Z",
                    "services": [],
                    "note": "test",
                }

            centre.alerts.ingest_hits([DetectionHit(
                rule_id="agent.repeated_failures",
                rule_version="1",
                title="Repeated agent task failures",
                severity="high",
                confidence="high",
                evidence=["2020-01-01T00:00:00Z task failed"],
                event_ids=["old"],
                fingerprint="historical-agent-failures",
                detail={"count": 3},
            )])
            with patch.object(centre, "refresh_health", side_effect=lambda: fake_snapshot()):
                overview = centre.overview()
            self.assertEqual(overview["overall"], "healthy")
            self.assertEqual(overview["open_alerts_outside_health_window"], 1)
            self.assertEqual(centre.alerts.open_counts()["total_open"], 1)
            self.assertNotEqual(centre.alerts.list()[0].status, "resolved")

    def test_snapshot_records_one_failure_per_task_and_keeps_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = OpsCentre(OpsCentreConfig(data_dir=Path(tmp)))

            class Desk:
                def history_list(self, limit: int = 20) -> list[dict]:
                    return [{
                        "task_id": "task-1",
                        "execution": "failed",
                        "failure": "tool timed out",
                        "goal": "check the queue",
                    }]

            first = centre.collect_agent_snapshot(Desk())
            second = centre.collect_agent_snapshot(Desk())
            rows = centre.events.list(limit=20, event_type="agent.task_failed")
            self.assertEqual(first["recorded"], 1)
            self.assertEqual(second["recorded"], 0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].correlation_id, "task-1")


if __name__ == "__main__":
    unittest.main()
