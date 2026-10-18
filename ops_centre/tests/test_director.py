"""Director report tests. No GPU, no network, no Pod."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops_centre.director import FORBIDDEN_CAPABILITIES, READ_ONLY_TOOLS, build_report
from ops_centre.service import OpsCentre, OpsCentreConfig


def _health(services: list[dict]) -> dict:
    return {
        "overall": "degraded",
        "verification": "observed",
        "verified_at": "2026-10-18T22:00:00Z",
        "services": services,
    }


class DirectorReportTests(unittest.TestCase):
    def _centre(self, tmp: str) -> OpsCentre:
        return OpsCentre(OpsCentreConfig(data_dir=Path(tmp)))

    def test_degraded_model_is_not_called_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            snapshot = _health([
                {"name": "qwen", "state": "unavailable", "verified_at": "2026-10-18T22:00:00Z", "http_status": 0, "detail": "URLError"},
                {"name": "gateway_live", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "http_status": 200, "detail": "process alive"},
                {"name": "gateway_ready", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "http_status": 200, "detail": "upstream ready"},
                {"name": "console", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "http_status": 200, "detail": "connection=ready"},
                {"name": "disk", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "detail": "free"},
            ])
            with patch.object(centre.health, "snapshot", return_value=snapshot):
                with patch.dict(os.environ, {"MICROSOFT_CLIENT_ID": "", "RAG_DOCS_DIR": ""}, clear=False):
                    os.environ.pop("MICROSOFT_CLIENT_ID", None)
                    os.environ.pop("RAG_DOCS_DIR", None)
                    report = build_report(centre)
            model = next(c for c in report["components"] if c["name"] == "model")
            self.assertEqual(model["state"], "DEGRADED")
            self.assertEqual(report["overall"], "DEGRADED")
            self.assertTrue(any("qwen" in item for item in model["evidence"]))
            self.assertIsNone(report["model_explanation"])
            self.assertEqual(report["hypotheses"], [])
            self.assertFalse(report["scheduler"]["available"])
            self.assertTrue(all(item["executed"] is False for item in report["recommendations"]))

    def test_missing_integrations_are_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            snapshot = _health([
                {"name": "qwen", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "http_status": 200, "detail": "ok"},
                {"name": "gateway_live", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "http_status": 200, "detail": "ok"},
                {"name": "gateway_ready", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "http_status": 200, "detail": "ok"},
                {"name": "console", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "http_status": 200, "detail": "ok"},
                {"name": "disk", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "detail": "ok"},
            ])
            with patch.object(centre.health, "snapshot", return_value=snapshot):
                os.environ.pop("MICROSOFT_CLIENT_ID", None)
                os.environ.pop("RAG_DOCS_DIR", None)
                report = build_report(centre)
            graph = next(c for c in report["components"] if c["name"] == "microsoft_graph")
            rag = next(c for c in report["components"] if c["name"] == "rag")
            agents = next(c for c in report["components"] if c["name"] == "agents")
            self.assertEqual(graph["state"], "NOT CONFIGURED")
            self.assertEqual(rag["state"], "NOT CONFIGURED")
            self.assertEqual(agents["state"], "UNKNOWN")
            self.assertNotIn("client_secret", str(report))

    def test_stale_probe_without_timestamp_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            snapshot = _health([
                {"name": "qwen", "state": "healthy", "http_status": 200, "detail": "ok"},
            ])
            snapshot["verified_at"] = None
            with patch.object(centre.health, "snapshot", return_value=snapshot):
                report = build_report(centre)
            model = next(c for c in report["components"] if c["name"] == "model")
            self.assertEqual(model["state"], "UNKNOWN")

    def test_allowlist_excludes_destructive_capabilities(self) -> None:
        self.assertNotIn("shell", READ_ONLY_TOOLS)
        self.assertIn("shell", FORBIDDEN_CAPABILITIES)
        self.assertIn("delete_audit", FORBIDDEN_CAPABILITIES)
        self.assertNotIn("ops_compose_investigation", READ_ONLY_TOOLS)

    def test_report_is_audited_and_does_not_delete_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            centre.record_event(event_type="unit.seed", component="unit", outcome="ok", summary="keep me")
            before = len(centre.events.list(limit=50))
            snapshot = _health([
                {"name": "qwen", "state": "unknown", "verified_at": "2026-10-18T22:00:00Z", "detail": "not checked"},
            ])
            with patch.object(centre.health, "snapshot", return_value=snapshot):
                build_report(centre)
            rows = centre.events.list(limit=50)
            self.assertGreaterEqual(len(rows), before)
            self.assertTrue(any(e.event_type == "director.report" for e in rows))
            self.assertTrue(any(e.event_type == "unit.seed" for e in rows))
            self.assertTrue(centre.events.verify_chain()["ok"])


if __name__ == "__main__":
    unittest.main()
