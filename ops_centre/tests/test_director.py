"""Director report tests. No GPU, no network, no Pod."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops_centre.director import FORBIDDEN_CAPABILITIES, READ_ONLY_TOOLS, build_report
from ops_centre.service import OpsCentre, OpsCentreConfig
from web.auth.passwords import hash_password


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
            schedule = str(Path(tmp) / "director-schedule.json")
            with patch.object(centre.health, "snapshot", return_value=snapshot):
                with patch.dict(
                    os.environ,
                    {"OPERATOR_AUTH_DIR": tmp, "DIRECTOR_SCHEDULE_FILE": schedule},
                    clear=False,
                ):
                    os.environ.pop("MICROSOFT_CLIENT_ID", None)
                    os.environ.pop("RAG_DOCS_DIR", None)
                    report = build_report(centre)
            model = next(c for c in report["components"] if c["name"] == "model")
            self.assertEqual(model["state"], "DEGRADED")
            self.assertEqual(report["overall"], "DEGRADED")
            self.assertTrue(any("qwen" in item for item in model["evidence"]))
            self.assertIsNone(report["model_explanation"])
            self.assertEqual(report["hypotheses"], [])
            self.assertTrue(report["scheduler"]["available"])
            self.assertFalse(report["scheduler"]["enabled"])
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
                with patch.dict(os.environ, {"OPERATOR_AUTH_DIR": tmp}, clear=False):
                    os.environ.pop("MICROSOFT_CLIENT_ID", None)
                    os.environ.pop("RAG_DOCS_DIR", None)
                    report = build_report(centre)
            auth = next(c for c in report["components"] if c["name"] == "operator_auth")
            self.assertEqual(auth["state"], "NOT CONFIGURED")
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
                with patch.dict(os.environ, {"OPERATOR_AUTH_DIR": tmp}, clear=False):
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
                with patch.dict(os.environ, {"OPERATOR_AUTH_DIR": tmp}, clear=False):
                    build_report(centre)
            rows = centre.events.list(limit=50)
            self.assertGreaterEqual(len(rows), before)
            self.assertTrue(any(e.event_type == "director.report" for e in rows))
            self.assertTrue(any(e.event_type == "unit.seed" for e in rows))
            self.assertTrue(centre.events.verify_chain()["ok"])

    def test_operator_auth_hides_hashes_and_needs_an_admin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            auth_dir = Path(tmp) / "auth"
            auth_dir.mkdir()
            secret_hash = hash_password("not-the-reported-secret-value")
            (auth_dir / "operators.json").write_text(
                json.dumps({"operators": [{
                    "operator_id": "abc",
                    "username": "ada",
                    "password_hash": secret_hash,
                    "role": "viewer",
                    "disabled": False,
                }]}),
                encoding="utf-8",
            )
            snapshot = _health([
                {"name": "qwen", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "http_status": 200, "detail": "ok"},
            ])
            with patch.object(centre.health, "snapshot", return_value=snapshot):
                with patch.dict(os.environ, {"OPERATOR_AUTH_DIR": str(auth_dir)}, clear=False):
                    report = build_report(centre)
            auth = next(c for c in report["components"] if c["name"] == "operator_auth")
            self.assertEqual(auth["state"], "DEGRADED")
            self.assertNotIn(secret_hash, json.dumps(report))
            (auth_dir / "operators.json").write_text(
                json.dumps({"operators": [{
                    "operator_id": "abc",
                    "username": "ada",
                    "password_hash": secret_hash,
                    "role": "admin",
                    "disabled": False,
                }]}),
                encoding="utf-8",
            )
            with patch.object(centre.health, "snapshot", return_value=snapshot):
                with patch.dict(os.environ, {"OPERATOR_AUTH_DIR": str(auth_dir)}, clear=False):
                    report = build_report(centre)
            auth = next(c for c in report["components"] if c["name"] == "operator_auth")
            self.assertEqual(auth["state"], "HEALTHY")
            self.assertNotIn(secret_hash, json.dumps(report))
            self.assertNotIn("ada", json.dumps(auth))

    def test_unusable_operator_file_is_not_healthy(self) -> None:
        secret = "plaintext-must-not-print"
        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            auth_dir = Path(tmp) / "auth"
            auth_dir.mkdir()
            path = auth_dir / "operators.json"
            snapshot = _health([
                {"name": "qwen", "state": "healthy", "verified_at": "2026-10-18T22:00:00Z", "http_status": 200, "detail": "ok"},
            ])

            def report_for(rows: list[dict]) -> dict:
                path.write_text(json.dumps({"operators": rows}), encoding="utf-8")
                with patch.object(centre.health, "snapshot", return_value=snapshot):
                    with patch.dict(os.environ, {"OPERATOR_AUTH_DIR": str(auth_dir)}, clear=False):
                        return build_report(centre)

            missing = report_for([{"role": "admin", "disabled": False, "password_hash": secret}])
            auth = next(c for c in missing["components"] if c["name"] == "operator_auth")
            self.assertEqual(auth["state"], "DEGRADED")
            self.assertNotIn(secret, json.dumps(missing))

            usable = {
                "operator_id": "abc",
                "username": "ada",
                "password_hash": hash_password("another-unprinted-password"),
                "role": "admin",
                "disabled": False,
            }
            replaced = report_for([
                usable,
                {**usable, "role": "viewer", "disabled": True},
            ])
            auth = next(c for c in replaced["components"] if c["name"] == "operator_auth")
            self.assertEqual(auth["state"], "DEGRADED")
            self.assertNotIn(usable["password_hash"], json.dumps(replaced))

            plain = report_for([{
                "operator_id": "abc",
                "username": "ada",
                "password_hash": secret,
                "role": "admin",
                "disabled": False,
            }])
            auth = next(c for c in plain["components"] if c["name"] == "operator_auth")
            self.assertEqual(auth["state"], "DEGRADED")
            self.assertNotIn(secret, json.dumps(plain))

            real = Path.is_symlink

            def fake_symlink(self: Path) -> bool:
                if self == path:
                    return True
                return real(self)

            path.write_text(json.dumps({"operators": [usable]}), encoding="utf-8")
            with patch.object(Path, "is_symlink", fake_symlink):
                with patch.object(centre.health, "snapshot", return_value=snapshot):
                    with patch.dict(os.environ, {"OPERATOR_AUTH_DIR": str(auth_dir)}, clear=False):
                        linked = build_report(centre)
            auth = next(c for c in linked["components"] if c["name"] == "operator_auth")
            self.assertEqual(auth["state"], "DEGRADED")
            self.assertIn("symlink", " ".join(auth["evidence"]))
            self.assertNotIn(usable["password_hash"], json.dumps(linked))

    def _healthy_snapshot(self) -> dict:
        return _health([
            {"name": "qwen", "state": "healthy", "verified_at": "2026-10-21T22:00:00Z", "http_status": 200, "detail": "ok"},
            {"name": "gateway_live", "state": "healthy", "verified_at": "2026-10-21T22:00:00Z", "http_status": 200, "detail": "ok"},
            {"name": "gateway_ready", "state": "healthy", "verified_at": "2026-10-21T22:00:00Z", "http_status": 200, "detail": "ok"},
            {"name": "console", "state": "healthy", "verified_at": "2026-10-21T22:00:00Z", "http_status": 200, "detail": "ok"},
            {"name": "disk", "state": "healthy", "verified_at": "2026-10-21T22:00:00Z", "detail": "ok"},
        ])

    def test_historical_agent_failures_stay_in_the_audit_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            for _ in range(3):
                centre.events.append(
                    event_type="agent.task_failed",
                    component="agent",
                    outcome="failed",
                    severity="high",
                    summary="historical task failed",
                )
            for event in centre.events.list(limit=10, event_type="agent.task_failed"):
                event.at = "2020-01-01T00:00:00Z"
            with patch.object(centre.health, "snapshot", return_value=self._healthy_snapshot()):
                with patch.dict(os.environ, {"OPERATOR_AUTH_DIR": tmp}, clear=False):
                    os.environ.pop("RAG_DOCS_DIR", None)
                    os.environ.pop("MICROSOFT_CLIENT_ID", None)
                    report = build_report(centre)
            agents = next(item for item in report["components"] if item["name"] == "agents")
            self.assertEqual(agents["state"], "UNKNOWN")
            self.assertIn("audit_preserved=true", agents["evidence"])
            self.assertIn("historical_failed_tasks=3", agents["evidence"])
            self.assertEqual(len(centre.events.list(limit=10, event_type="agent.task_failed")), 3)
            self.assertEqual(report["retained_failed_audit_rows"], 3)
            self.assertEqual(report["recent_failed_tasks"], 0)
            self.assertNotEqual(agents["state"], "DEGRADED")

    def test_a_current_agent_failure_is_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            centre.events.append(
                event_type="agent.task_failed",
                component="agent",
                outcome="failed",
                severity="high",
                summary="current task failed",
            )
            with patch.object(centre.health, "snapshot", return_value=self._healthy_snapshot()):
                with patch.dict(os.environ, {"OPERATOR_AUTH_DIR": tmp}, clear=False):
                    os.environ.pop("RAG_DOCS_DIR", None)
                    report = build_report(centre)
            agents = next(item for item in report["components"] if item["name"] == "agents")
            self.assertEqual(agents["state"], "DEGRADED")
            self.assertEqual(len(centre.events.list(limit=10, event_type="agent.task_failed")), 1)

    def test_rag_probe_cites_and_abstains_without_calling_a_model(self) -> None:
        from ops_centre.rag_probe import write_acceptance_corpus

        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            write_acceptance_corpus(docs)
            centre = self._centre(tmp)
            with patch.object(centre.health, "snapshot", return_value=self._healthy_snapshot()):
                with patch.dict(os.environ, {"OPERATOR_AUTH_DIR": tmp, "RAG_DOCS_DIR": str(docs)}, clear=False):
                    os.environ.pop("MICROSOFT_CLIENT_ID", None)
                    report = build_report(centre)
            rag = next(item for item in report["components"] if item["name"] == "rag")
            self.assertEqual(rag["state"], "HEALTHY")
            self.assertIn("model_called=false", rag["evidence"])
            self.assertIn("citation_file=warranty.txt", rag["evidence"])
            self.assertIn("abstained=true", rag["evidence"])
            self.assertNotIn("fourteen months", json.dumps(rag))


if __name__ == "__main__":
    unittest.main()
