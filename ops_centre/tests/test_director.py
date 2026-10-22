"""Director report tests. No GPU, no network, no Pod."""
from __future__ import annotations

import json
import os
import tempfile
import time
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

    def test_graph_is_not_healthy_when_evidence_is_missing_or_stale(self) -> None:
        secret = "graph-token-must-not-print"
        client_id = "graph-client-must-not-print"
        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            token_path = Path(tmp) / "token.json"
            snapshot = self._healthy_snapshot()
            snapshot["verified_at"] = datetime_now()

            def report_for(env: dict[str, str]) -> dict:
                with patch.object(centre.health, "snapshot", return_value=snapshot):
                    with patch.dict(os.environ, env, clear=False):
                        os.environ.pop("RAG_DOCS_DIR", None)
                        return build_report(centre)

            base = {
                "OPERATOR_AUTH_DIR": tmp,
                "ENDPOINT_STATE_FILE": "",
                "REPAIR_DEVICE_STATE": "",
                "MICROSOFT_TOKEN_FILE": "",
            }
            missing = report_for({**base, "MICROSOFT_CLIENT_ID": ""})
            graph = next(item for item in missing["components"] if item["name"] == "microsoft_graph")
            self.assertEqual(graph["state"], "NOT CONFIGURED")
            self.assertIn("graph_called=false", graph["evidence"])
            self.assertNotEqual(graph["state"], "HEALTHY")

            configured = report_for({**base, "MICROSOFT_CLIENT_ID": client_id})
            graph = next(item for item in configured["components"] if item["name"] == "microsoft_graph")
            self.assertEqual(graph["state"], "UNKNOWN")
            self.assertNotEqual(graph["state"], "HEALTHY")
            self.assertNotIn(client_id, json.dumps(configured))

            token_path.write_text(json.dumps({
                "access_token": secret,
                "refresh_token": secret,
                "expires_at": 1_000,
            }), encoding="utf-8")
            stale = report_for({
                **base,
                "MICROSOFT_CLIENT_ID": client_id,
                "MICROSOFT_TOKEN_FILE": str(token_path),
            })
            graph = next(item for item in stale["components"] if item["name"] == "microsoft_graph")
            self.assertEqual(graph["state"], "DEGRADED")
            self.assertIn("token_expired=true", graph["evidence"])
            self.assertNotEqual(graph["state"], "HEALTHY")
            self.assertNotIn(secret, json.dumps(stale))

            token_path.write_text(json.dumps({
                "access_token": secret,
                "expires_at": int(time.time()) + 3600,
            }), encoding="utf-8")
            fresh_token = report_for({
                **base,
                "MICROSOFT_CLIENT_ID": client_id,
                "MICROSOFT_TOKEN_FILE": str(token_path),
            })
            graph = next(item for item in fresh_token["components"] if item["name"] == "microsoft_graph")
            self.assertEqual(graph["state"], "UNKNOWN")
            self.assertIn("graph_called=false", graph["evidence"])
            self.assertNotEqual(graph["state"], "HEALTHY")
            self.assertNotIn(secret, json.dumps(fresh_token))

    def test_stale_fleet_and_repair_evidence_are_not_healthy(self) -> None:
        import time as time_mod

        from integrations.endpoint import DeviceRegistry
        from web.auth.store import SessionRecord
        from windows_repair.device_store import DeviceStore, grant_from_session

        class Provider:
            def collect(self, _procedure_id: str) -> dict:
                return {
                    "evidence_source": "live_windows",
                    "mocked": False,
                    "status": "collected",
                    "ok": True,
                    "problem_resolved": False,
                    "collected_at_unix": int(time_mod.time()),
                }

        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            now = time_mod.time()
            registry_path = Path(tmp) / "devices.json"
            registry = DeviceRegistry(registry_path, clock=lambda: now)
            created = registry.create_enrolment("local-console")
            device_secret = "e" * 32
            registry.enrol(created["enrolment_code"], "Office PC", device_secret)
            registry.submit(device_secret, {
                "os_family": "windows",
                "os_version": "test",
                "disk_free_bytes": 10,
                "disk_total_bytes": 20,
                "memory_total_bytes": 30,
                "boot_time_unix": 100,
                "collected_at_unix": 1000,
                "checks": [{
                    "procedure_id": "win.storage.space",
                    "evidence_source": "live_windows",
                    "ok": True,
                    "collected_at_unix": 1000,
                    "summary": "disks=1",
                }],
            })

            repair_path = Path(tmp) / "device.json"
            store = DeviceStore(repair_path, ttl=10)
            repair_secret = "d" * 32
            device_id = store.enrol("acme", repair_secret)
            end = now + 3600
            grant = grant_from_session(SessionRecord(
                "sess-ada", "op-ada", "ada", "operator", "csrf-ada", now, now, end, end,
            ), "acme")
            envelope = store.issue(
                tenant_id="acme",
                device_id=device_id,
                procedure_id="win.storage.space",
                grant=grant,
            )
            store.accept(repair_secret, envelope, provider=Provider())
            raw = json.loads(repair_path.read_text(encoding="utf-8"))
            raw["devices"][device_id]["last_seen"] = time_mod.time()
            for state in raw["job_states"].values():
                state["collected_at_unix"] = int(time_mod.time()) - 90_000
                state["evidence_fresh"] = True
            repair_path.write_text(json.dumps(raw), encoding="utf-8")

            snapshot = self._healthy_snapshot()
            snapshot["verified_at"] = datetime_now()
            with patch.object(centre.health, "snapshot", return_value=snapshot):
                with patch.dict(os.environ, {
                    "OPERATOR_AUTH_DIR": tmp,
                    "ENDPOINT_STATE_FILE": str(registry_path),
                    "REPAIR_DEVICE_STATE": str(repair_path),
                    "MICROSOFT_CLIENT_ID": "",
                    "MICROSOFT_TOKEN_FILE": "",
                }, clear=False):
                    os.environ.pop("RAG_DOCS_DIR", None)
                    report = build_report(centre)
            fleet = next(item for item in report["components"] if item["name"] == "endpoint_fleet")
            jobs = next(item for item in report["components"] if item["name"] == "repair_jobs")
            self.assertEqual(fleet["state"], "DEGRADED")
            self.assertNotEqual(fleet["state"], "HEALTHY")
            self.assertIn("evidence_stale=true", fleet["evidence"])
            self.assertEqual(jobs["state"], "DEGRADED")
            self.assertNotEqual(jobs["state"], "HEALTHY")
            self.assertTrue(any(
                item.startswith("evidence_age_seconds=") and int(item.split("=", 1)[1]) > 86400
                for item in jobs["evidence"]
            ))
            blob = json.dumps(report)
            self.assertNotIn(device_secret, blob)
            self.assertNotIn(repair_secret, blob)

    def test_off_pod_is_not_copied_forward_as_current_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            centre = self._centre(tmp)
            fresh = datetime_now()
            snapshot = self._healthy_snapshot()
            snapshot["verified_at"] = fresh
            by_name = {item["name"]: item for item in snapshot["services"]}
            by_name["qwen"]["verified_at"] = "2020-01-01T00:00:00Z"
            by_name["qwen"]["state"] = "healthy"
            by_name["gateway_ready"]["state"] = "healthy"
            by_name["gateway_ready"]["verified_at"] = fresh
            by_name["gateway_ready"]["pod"] = "stopped"
            by_name["gateway_ready"]["health"] = {"status": "ok", "upstream": "ok"}
            by_name["console"]["state"] = "healthy"
            by_name["console"]["verified_at"] = fresh
            by_name["console"]["detail"] = "model_engine_dead"
            with patch.object(centre.health, "snapshot", return_value=snapshot):
                with patch.dict(os.environ, {
                    "OPERATOR_AUTH_DIR": tmp,
                    "ENDPOINT_STATE_FILE": "",
                    "REPAIR_DEVICE_STATE": "",
                    "MICROSOFT_CLIENT_ID": "",
                    "MICROSOFT_TOKEN_FILE": "",
                }, clear=False):
                    os.environ.pop("RAG_DOCS_DIR", None)
                    report = build_report(centre)
            model = next(item for item in report["components"] if item["name"] == "model")
            gateway = next(item for item in report["components"] if item["name"] == "gateway")
            console = next(item for item in report["components"] if item["name"] == "console")
            self.assertEqual(model["state"], "UNKNOWN")
            self.assertIn("stale_or_off_probe_not_current=true", model["evidence"])
            self.assertEqual(gateway["state"], "DEGRADED")
            self.assertIn("previous_health_not_copied_forward=true", gateway["evidence"])
            self.assertEqual(console["state"], "DEGRADED")
            self.assertNotEqual(report["overall"], "HEALTHY")
            for component in (model, gateway, console):
                self.assertNotEqual(component["state"], "HEALTHY")


def datetime_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    unittest.main()
