"""Live diagnostic parsing and the printer approval workflow.

Fixture and fake-provider tests are marked mocked. The Windows integration
tests run only on Windows and do not restart any service.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from types import SimpleNamespace

from windows_repair.device_store import DeviceStore, grant_from_session


def _ada(tenant_id: str = "acme"):
    return grant_from_session(
        SimpleNamespace(session_id="sess-ada", operator_id="op-ada", username="ada", role="operator"),
        tenant_id,
    )
from windows_repair.engine import RepairDenied
from windows_repair.printer_flow import PrinterWorkflow, classify_printer
from windows_repair.providers import FixtureProvider, normalise_live
from windows_repair.remote_support import request_session, revoke_session, status_from_env
from windows_repair.runner import powershell_exe, run_argv


class ParseTests(unittest.TestCase):
    def test_live_printer_json_is_not_a_fixture(self) -> None:
        evidence = normalise_live("print.diagnose", {
            "spooler": {"Name": "Spooler", "Status": 4},
            "printers": [{"Name": "Office", "DriverName": "HP", "PortName": "USB001", "PrinterStatus": 0, "JobCount": 1}],
            "jobs": [{"Id": 3, "PrinterName": "Office", "JobStatus": 1}],
        })
        self.assertEqual(evidence["evidence_source"], "live_windows")
        self.assertFalse(evidence["mocked"])
        self.assertEqual(evidence["spooler"], "Running")
        self.assertEqual(evidence["printers"][0]["name"], "Office")

    def test_fixture_is_labelled_fixture(self) -> None:
        evidence = FixtureProvider().collect("print.diagnose")
        self.assertEqual(evidence["evidence_source"], "fixture")
        self.assertTrue(evidence["mocked"])
        found = classify_printer(evidence)
        self.assertEqual(found["category"], "stuck_or_pending_job")
        self.assertIsNone(found["proposed_procedure"])
        self.assertFalse(found["problem_resolved"])

    def test_stopped_spooler_proposes_restart_only(self) -> None:
        found = classify_printer({
            "evidence_source": "live_windows",
            "ok": True,
            "spooler": "Stopped",
            "printers": [{"name": "Office"}],
            "jobs": [],
        })
        self.assertEqual(found["proposed_procedure"], "print.spooler.restart")
        self.assertEqual(found["risk"], "ELEVATED_RISK")


class _Script:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = list(rows)

    def collect(self, procedure_id: str) -> dict:
        return dict(self.rows.pop(0))


class PrinterWorkflowTests(unittest.TestCase):
    def test_restart_is_blocked_until_a_different_person_approves(self) -> None:
        provider = _Script([
            {"evidence_source": "mock", "mocked": True, "spooler": "Stopped", "printers": [{"name": "Office"}], "jobs": []},
            {"evidence_source": "mock", "mocked": True, "spooler": "Running", "printers": [{"name": "Office"}], "jobs": []},
        ])
        calls = []
        flow = PrinterWorkflow(provider=provider, restarter=lambda params: calls.append(params) or {"executed": True, "changed_device": True, "status": "restarted"})
        requested = flow.request_restart("acme", "device-1", "requester@example.com")
        blocked = flow.execute_restart("acme", "device-1", requested["approval_id"], "operator@example.com")
        self.assertEqual(blocked["status"], "approval_rejected")
        self.assertEqual(calls, [])
        rejected = flow.approve("acme", requested["approval_id"], "requester@example.com")
        self.assertEqual(rejected["status"], "approval_rejected")
        decided = flow.approve("acme", requested["approval_id"], "approver@example.com")
        self.assertEqual(decided["status"], "approved")
        mismatched = flow.execute_restart("acme", "device-2", requested["approval_id"], "operator@example.com")
        self.assertEqual(mismatched["status"], "approval_rejected")
        result = flow.execute_restart("acme", "device-1", requested["approval_id"], "operator@example.com")
        self.assertEqual(result["verification"], "resolved")
        self.assertTrue(result["problem_resolved"])
        self.assertEqual(result["evidence_source"], "mock")
        self.assertTrue(result["mocked"] if "mocked" in result else True)
        again = flow.execute_restart("acme", "device-1", requested["approval_id"], "operator@example.com")
        self.assertEqual(again["status"], "approval_rejected")

    def test_default_restarter_does_not_change_this_computer(self) -> None:
        provider = _Script([
            {"evidence_source": "mock", "mocked": True, "spooler": "Stopped"},
            {"evidence_source": "mock", "mocked": True, "spooler": "Stopped"},
        ])
        flow = PrinterWorkflow(provider=provider)
        requested = flow.request_restart("acme", "device-1", "requester@example.com")
        flow.approve("acme", requested["approval_id"], "approver@example.com")
        with patch.dict(os.environ, {"WINDOWS_REPAIR_ALLOW_SERVICE_RESTART": ""}, clear=False):
            os.environ.pop("WINDOWS_REPAIR_ALLOW_SERVICE_RESTART", None)
            result = flow.execute_restart("acme", "device-1", requested["approval_id"], "operator@example.com")
        self.assertEqual(result["status"], "needs_administrator")
        self.assertFalse(result["executed"])
        self.assertFalse(result["changed_device"])
        self.assertEqual(result["verification"], "could_not_verify")
        self.assertFalse(result["problem_resolved"])


class DeviceAndRemoteTests(unittest.TestCase):
    def test_revoked_replay_and_tenant_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 1000.0}
            store = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"], ttl=10)
            secret = "d" * 32
            device = store.enrol("acme", secret)
            other = store.enrol("otherco", "e" * 32)
            with self.assertRaises(RepairDenied):
                store.issue(tenant_id="acme", device_id=other, procedure_id="win.storage.space", grant=_ada())
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            provider = _Script([{"evidence_source": "mock", "mocked": True, "status": "collected", "problem_resolved": False}])
            first = store.accept(secret, envelope, provider=provider)
            self.assertEqual(first["evidence_source"], "mock")
            self.assertFalse(first["problem_resolved"])
            with self.assertRaises(RepairDenied):
                store.accept(secret, envelope, provider=provider)
            expired = store.issue(tenant_id="acme", device_id=device, procedure_id="print.diagnose", grant=_ada())
            clock["now"] += 30
            with self.assertRaises(RepairDenied):
                store.accept(secret, expired, provider=provider)
            store.revoke("acme", device)
            clock["now"] += 1
            with self.assertRaises(RepairDenied):
                store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())

    def test_remote_session_is_not_established(self) -> None:
        report = status_from_env({"MESHCENTRAL_URL": ""})
        self.assertEqual(report["state"], "NOT CONFIGURED")
        self.assertIn("Apache", report["licence_note"])
        session = request_session(operator="ada", device_id="device-1", tenant_id="acme", customer_authorised=True)
        self.assertFalse(session["established"])
        self.assertFalse(session["remote_desktop_verified"])
        revoked = revoke_session(session)
        self.assertEqual(revoked["state"], "revoked")
        self.assertFalse(revoked["established"])

    def test_missing_tool_and_timeout(self) -> None:
        missing = run_argv([r"C:\no\such\repair-tool.exe"], timeout=1)
        self.assertEqual(missing["status"], "tool_missing")
        self.assertEqual(missing["evidence_source"], "unavailable")
        executable = powershell_exe()
        if executable is None:
            self.skipTest("Windows PowerShell is not on this computer")
        timed = run_argv([executable, "-NoProfile", "-NonInteractive", "-Command", "Start-Sleep -Seconds 5"], timeout=0.4)
        self.assertTrue(timed["timed_out"])
        self.assertEqual(timed["status"], "timeout")


@unittest.skipUnless(os.name == "nt", "Windows integration test")
class WindowsIntegrationTests(unittest.TestCase):
    def test_live_storage_and_printer_are_not_fixtures(self) -> None:
        import time
        from windows_repair.providers import LiveWindowsProvider

        storage = LiveWindowsProvider().collect("win.storage.space")
        self.assertEqual(storage["evidence_source"], "live_windows")
        self.assertFalse(storage["mocked"])
        self.assertFalse(storage["problem_resolved"])
        self.assertTrue(storage.get("disks"))
        printers = LiveWindowsProvider().collect("print.diagnose")
        self.assertNotEqual(printers["evidence_source"], "fixture")
        self.assertFalse(printers.get("mocked", False))
        self.assertFalse(printers.get("problem_resolved", False))
        self.assertGreater(int(storage["collected_at_unix"]), int(time.time()) - 180)

    def test_enrolled_device_runs_one_live_read_only_job(self) -> None:
        """Local live check on this PC through an enrolled job. Not a customer endpoint."""
        import time

        with tempfile.TemporaryDirectory() as tmp:
            store = DeviceStore(Path(tmp) / "device.json")
            secret = "d" * 32
            device = store.enrol("local-test", secret)
            envelope = store.issue(
                tenant_id="local-test",
                device_id=device,
                procedure_id="win.storage.space",
                grant=_ada("local-test"),
            )
            result = store.accept(secret, envelope)
            self.assertEqual(result["evidence_source"], "live_windows")
            self.assertFalse(result["mocked"])
            self.assertFalse(result["problem_resolved"])
            self.assertTrue(result["evidence_fresh"])
            self.assertFalse(result.get("repair_authority", False))
            self.assertGreater(int(result["collected_at_unix"]), int(time.time()) - 180)
            self.assertEqual(store.job_states[envelope["job_id"]]["lifecycle"], "accepted")
            self.assertGreaterEqual(store.summary()["live_accepted_jobs"], 1)
            self.assertNotIn(secret, json.dumps(store.summary()))


class DirectorGapTests(unittest.TestCase):
    def test_missing_files_are_not_healthy(self) -> None:
        from ops_centre.director import _endpoint_fleet, _repair_jobs

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENDPOINT_STATE_FILE", None)
            os.environ.pop("REPAIR_DEVICE_STATE", None)
            self.assertEqual(_endpoint_fleet("2026-10-19T00:00:00Z")["state"], "UNKNOWN")
            self.assertEqual(_repair_jobs("2026-10-19T00:00:00Z")["state"], "NOT CONFIGURED")

    def _store(self, tmp: str, clock: dict) -> tuple[DeviceStore, str, str]:
        store = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"], ttl=10)
        secret = "d" * 32
        device = store.enrol("acme", secret)
        return store, secret, device

    def test_job_moves_from_issued_to_accepted_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 1_000.0}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            self.assertEqual(store.summary()["open_jobs"], 1)
            self.assertEqual(store.summary()["pending_jobs"], 1)
            provider = _Script([{"evidence_source": "mock", "mocked": True, "status": "collected", "ok": True, "problem_resolved": False}])
            accepted = store.accept(secret, envelope, provider=provider)
            self.assertFalse(accepted["problem_resolved"])
            summary = store.summary()
            self.assertEqual(summary["open_jobs"], 0)
            self.assertEqual(summary["accepted_jobs"], 1)
            self.assertEqual(summary["expired_jobs"], 0)
            self.assertFalse(summary["stale"])
            reloaded = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"])
            self.assertEqual(reloaded.job_states[envelope["job_id"]]["lifecycle"], "accepted")
            self.assertEqual(reloaded.summary()["accepted_jobs"], 1)
            self.assertNotIn("key", json.dumps(reloaded.summary()))

    def test_unaccepted_job_expires_without_becoming_healthy(self) -> None:
        from ops_centre.director import _repair_jobs

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 1_000.0}
            store, _secret, device = self._store(tmp, clock)
            store.issue(tenant_id="acme", device_id=device, procedure_id="print.diagnose", grant=_ada())
            clock["now"] += 30
            summary = store.summary()
            self.assertEqual(summary["open_jobs"], 0)
            self.assertEqual(summary["expired_jobs"], 1)
            self.assertIsNone(summary["last_seen"])
            previous = os.environ.get("REPAIR_DEVICE_STATE")
            os.environ["REPAIR_DEVICE_STATE"] = str(Path(tmp) / "device.json")
            try:
                report = _repair_jobs("2026-10-20T00:00:00Z")
            finally:
                if previous is None:
                    os.environ.pop("REPAIR_DEVICE_STATE", None)
                else:
                    os.environ["REPAIR_DEVICE_STATE"] = previous
            self.assertEqual(report["state"], "UNKNOWN")
            self.assertNotEqual(report["state"], "HEALTHY")

    def test_stale_and_failed_checkins_are_not_healthy(self) -> None:
        import time
        from ops_centre.director import _repair_jobs

        with tempfile.TemporaryDirectory() as tmp:
            stale_clock = {"now": 1_000.0}
            store, secret, device = self._store(tmp, stale_clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            provider = _Script([{"evidence_source": "mock", "mocked": True, "status": "collected", "ok": True, "problem_resolved": False}])
            store.accept(secret, envelope, provider=provider)
            stale_clock["now"] += 86401
            self.assertTrue(store.summary()["stale"])
            self.assertNotEqual(store.summary()["last_seen"], None)
            path = str(Path(tmp) / "device.json")
            previous = os.environ.get("REPAIR_DEVICE_STATE")
            os.environ["REPAIR_DEVICE_STATE"] = path
            try:
                stale = _repair_jobs("2026-10-20T00:00:00Z")
                self.assertEqual(stale["state"], "DEGRADED")
                self.assertNotEqual(stale["state"], "HEALTHY")
                self.assertTrue(any(item.startswith("age_seconds=") for item in stale["evidence"]))
            finally:
                if previous is None:
                    os.environ.pop("REPAIR_DEVICE_STATE", None)
                else:
                    os.environ["REPAIR_DEVICE_STATE"] = previous

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": time.time()}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            provider = _Script([{"evidence_source": "mock", "mocked": True, "status": "failed", "ok": False, "problem_resolved": False}])
            store.accept(secret, envelope, provider=provider)
            previous = os.environ.get("REPAIR_DEVICE_STATE")
            os.environ["REPAIR_DEVICE_STATE"] = str(Path(tmp) / "device.json")
            try:
                failed = _repair_jobs("2026-10-20T00:00:00Z")
            finally:
                if previous is None:
                    os.environ.pop("REPAIR_DEVICE_STATE", None)
                else:
                    os.environ["REPAIR_DEVICE_STATE"] = previous
            self.assertEqual(failed["state"], "DEGRADED")
            self.assertNotEqual(failed["state"], "HEALTHY")

    def _director_repair(self, path: str) -> dict:
        from ops_centre.director import _repair_jobs

        previous = os.environ.get("REPAIR_DEVICE_STATE")
        os.environ["REPAIR_DEVICE_STATE"] = path
        try:
            return _repair_jobs("2026-10-20T00:00:00Z")
        finally:
            if previous is None:
                os.environ.pop("REPAIR_DEVICE_STATE", None)
            else:
                os.environ["REPAIR_DEVICE_STATE"] = previous

    def test_mock_accept_is_not_healthy_and_live_windows_is(self) -> None:
        import time

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": time.time()}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            provider = _Script([{"evidence_source": "mock", "mocked": True, "status": "collected", "ok": True, "problem_resolved": False}])
            accepted = store.accept(secret, envelope, provider=provider)
            self.assertEqual(accepted["evidence_source"], "mock")
            self.assertFalse(accepted["problem_resolved"])
            report = self._director_repair(str(Path(tmp) / "device.json"))
            self.assertEqual(report["state"], "UNKNOWN")
            self.assertNotEqual(report["state"], "HEALTHY")
            self.assertIn("live_accepted_jobs=0", report["evidence"])

            live = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            live_provider = _Script([{
                "evidence_source": "live_windows",
                "mocked": False,
                "status": "collected",
                "ok": True,
                "problem_resolved": False,
                "collected_at_unix": int(clock["now"]),
            }])
            store.accept(secret, live, provider=live_provider)
            fresh = self._director_repair(str(Path(tmp) / "device.json"))
            self.assertEqual(fresh["state"], "HEALTHY")
            self.assertIn("repair_authority=false", fresh["evidence"])
            self.assertIn("live_accepted_jobs=1", fresh["evidence"])
            self.assertIn("not a repair", fresh["detail"])

    def test_older_file_without_job_states_is_not_called_healthy(self) -> None:
        import time

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device.json"
            clock = {"now": time.time()}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            provider = _Script([{"evidence_source": "live_windows", "mocked": False, "status": "collected", "ok": True, "problem_resolved": False}])
            store.accept(secret, envelope, provider=provider)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw.pop("job_states", None)
            path.write_text(json.dumps(raw), encoding="utf-8")
            reloaded = DeviceStore(path, clock=lambda: clock["now"])
            summary = reloaded.summary()
            self.assertEqual(summary["accepted_jobs"], 0)
            self.assertGreaterEqual(summary["rejected_jobs"], 1)
            self.assertEqual(summary["live_accepted_jobs"], 0)
            report = self._director_repair(str(path))
            self.assertEqual(report["state"], "UNKNOWN")
            self.assertNotEqual(report["state"], "HEALTHY")


class _MustNotRun:
    """Fixture double. A rejected or expired job must not collect."""

    def collect(self, procedure_id: str) -> dict:
        raise AssertionError(f"collector ran for {procedure_id}")


class JobRejectionTests(unittest.TestCase):
    """Fixture and mock tests. They do not touch this PC."""

    def _store(self, tmp: str, clock: dict) -> tuple[DeviceStore, str, str]:
        store = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"], ttl=10)
        secret = "d" * 32
        device = store.enrol("acme", secret)
        return store, secret, device

    def test_blank_or_hostile_operator_cannot_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 1_000.0}
            store, _secret, device = self._store(tmp, clock)
            for operator in ("", "ada;whoami", "operator name"):
                with self.assertRaises(RepairDenied):
                    store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", operator=operator)
            self.assertEqual(store.summary()["issued_jobs"], 0)

    def test_revoked_and_unauthorised_jobs_are_persisted_rejections(self) -> None:
        from ops_centre.director import _repair_jobs

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 1_000.0}
            store, secret, device = self._store(tmp, clock)
            revoked_job = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            store.revoke("acme", device)
            with self.assertRaises(RepairDenied) as revoked:
                store.accept(secret, revoked_job, provider=_MustNotRun())
            self.assertIn("revoked", str(revoked.exception))
            self.assertEqual(store.job_states[revoked_job["job_id"]]["lifecycle"], "rejected")
            self.assertEqual(store.job_states[revoked_job["job_id"]]["reason"], "revoked")
            other = store.enrol("acme", "e" * 32)
            unauthorised = store.issue(tenant_id="acme", device_id=other, procedure_id="print.diagnose", grant=_ada())
            with self.assertRaises(RepairDenied) as denied:
                store.accept("f" * 32, unauthorised, provider=_MustNotRun())
            self.assertIn("authentication", str(denied.exception))
            with self.assertRaises(RepairDenied):
                store.accept("e" * 32, unauthorised, provider=_MustNotRun())
            self.assertEqual(store.job_states[unauthorised["job_id"]]["reason"], "unauthorised")
            reloaded = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"])
            self.assertEqual(reloaded.summary()["rejected_jobs"], 2)
            self.assertIsNone(reloaded.summary()["last_seen"])
            previous = os.environ.get("REPAIR_DEVICE_STATE")
            os.environ["REPAIR_DEVICE_STATE"] = str(Path(tmp) / "device.json")
            try:
                report = _repair_jobs("2026-10-20T00:00:00Z")
            finally:
                if previous is None:
                    os.environ.pop("REPAIR_DEVICE_STATE", None)
                else:
                    os.environ["REPAIR_DEVICE_STATE"] = previous
            self.assertNotEqual(report["state"], "HEALTHY")
            self.assertIn("rejected_jobs=2", report["evidence"])

    def test_expired_accept_does_not_collect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 2_000.0}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            clock["now"] += 30
            with self.assertRaises(RepairDenied) as expired:
                store.accept(secret, envelope, provider=_MustNotRun())
            self.assertIn("expired", str(expired.exception))
            self.assertEqual(store.job_states[envelope["job_id"]]["lifecycle"], "expired")
            reloaded = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"])
            self.assertEqual(reloaded.summary()["expired_jobs"], 1)
            self.assertEqual(reloaded.summary()["accepted_jobs"], 0)

    def test_stale_or_missing_live_evidence_is_not_healthy(self) -> None:
        """Mock payloads. A live_windows label without a fresh timestamp is not HEALTHY."""
        import time

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": time.time()}
            store, secret, device = self._store(tmp, clock)
            missing = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            provider = _Script([{
                "evidence_source": "live_windows",
                "mocked": True,
                "status": "collected",
                "ok": True,
                "problem_resolved": False,
            }])
            accepted = store.accept(secret, missing, provider=provider)
            self.assertFalse(accepted["evidence_fresh"])
            self.assertEqual(store.summary()["stale_evidence_jobs"], 1)
            self.assertEqual(store.summary()["live_accepted_jobs"], 0)
            report = DirectorGapTests()._director_repair(str(Path(tmp) / "device.json"))
            self.assertEqual(report["state"], "DEGRADED")
            self.assertNotEqual(report["state"], "HEALTHY")
            self.assertIn("stale_evidence_jobs=1", report["evidence"])

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": time.time()}
            store, secret, device = self._store(tmp, clock)
            stale = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            provider = _Script([{
                "evidence_source": "live_windows",
                "mocked": True,
                "status": "collected",
                "ok": True,
                "problem_resolved": False,
                "collected_at_unix": int(clock["now"]) - 90_000,
            }])
            store.accept(secret, stale, provider=provider)
            report = DirectorGapTests()._director_repair(str(Path(tmp) / "device.json"))
            self.assertEqual(report["state"], "DEGRADED")
            self.assertNotEqual(report["state"], "HEALTHY")
            ages = [item.split("=", 1)[1] for item in report["evidence"] if item.startswith("evidence_age_seconds=")]
            self.assertTrue(ages)
            self.assertGreater(int(ages[0]), 86400)

    def test_failed_collector_is_not_healthy(self) -> None:
        """Mock collector. The exception is caught and is not a repair."""
        import time

        class _Boom:
            def collect(self, procedure_id: str) -> dict:
                raise OSError("collector failed")

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": time.time()}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            result = store.accept(secret, envelope, provider=_Boom())
            self.assertFalse(result["ok"])
            self.assertEqual(result["evidence_source"], "unavailable")
            self.assertFalse(result["problem_resolved"])
            self.assertEqual(result["detail"], "OSError")
            self.assertEqual(store.job_states[envelope["job_id"]]["lifecycle"], "failed")
            report = DirectorGapTests()._director_repair(str(Path(tmp) / "device.json"))
            self.assertEqual(report["state"], "DEGRADED")
            self.assertNotEqual(report["state"], "HEALTHY")

    def test_spooler_restart_is_refused_at_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 3_000.0}
            store, _secret, device = self._store(tmp, clock)
            with self.assertRaises(RepairDenied) as denied:
                store.issue(
                    tenant_id="acme",
                    device_id=device,
                    procedure_id="print.spooler.restart",
                    grant=_ada(),
                )
            self.assertIn("read-only", str(denied.exception))
            with self.assertRaises(RepairDenied) as approved:
                store.issue(
                    tenant_id="acme",
                    device_id=device,
                    procedure_id="print.spooler.restart",
                    grant=_ada(),
                    approval_id="apr-1",
                )
            self.assertIn("approval", str(approved.exception))
            self.assertEqual(store.summary()["issued_jobs"], 0)

    def test_session_name_and_role_do_not_grant_authority_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 3_000.0}
            store, _secret, device = self._store(tmp, clock)
            with self.assertRaises(RepairDenied):
                store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", operator="ada")
            with self.assertRaises(RepairDenied):
                grant_from_session(
                    SimpleNamespace(session_id="s", operator_id="op", username="ada", role="viewer"),
                    "acme",
                )
            with self.assertRaises(RepairDenied):
                grant_from_session("ada", "acme")
            other = grant_from_session(
                SimpleNamespace(session_id="s2", operator_id="op2", username="ada", role="operator"),
                "otherco",
            )
            with self.assertRaises(RepairDenied) as crossed:
                store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=other)
            self.assertIn("organisation", str(crossed.exception))
            self.assertEqual(store.summary()["issued_jobs"], 0)

    def test_key_is_split_and_reload_verifies_signatures(self) -> None:
        import os as _os
        import stat
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device.json"
            clock = {"now": 4_000.0}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["version"], 2)
            self.assertNotIn("key", raw)
            key_path = Path(str(path) + ".key")
            self.assertTrue(key_path.is_file())
            if _os.name == "posix":
                self.assertEqual(stat.S_IMODE(key_path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            reloaded = DeviceStore(path, clock=lambda: clock["now"])
            provider = _Script([{
                "evidence_source": "mock",
                "mocked": True,
                "status": "collected",
                "ok": True,
                "problem_resolved": False,
            }])
            result = reloaded.accept(secret, envelope, provider=provider)
            self.assertEqual(result["evidence_source"], "mock")
            with self.assertRaises(RepairDenied):
                reloaded.accept(secret, envelope, provider=_MustNotRun())
            tampered = dict(envelope)
            tampered["job_id"] = "changed"
            with self.assertRaises(RepairDenied):
                reloaded.accept(secret, tampered, provider=_MustNotRun())
            moved = dict(envelope)
            moved["device_id"] = "other-device"
            with self.assertRaises(RepairDenied):
                reloaded.accept(secret, moved, provider=_MustNotRun())
            broken = Path(tmp) / "broken.json"
            broken.write_text("{", encoding="utf-8")
            with self.assertRaises(RepairDenied):
                DeviceStore(broken, clock=lambda: clock["now"])
            self.assertEqual(broken.read_text(encoding="utf-8"), "{")

            clock["now"] = 5_000.0
            second_store, second_secret, second_device = self._store(str(Path(tmp) / "race"), clock)
            race = second_store.issue(
                tenant_id="acme",
                device_id=second_device,
                procedure_id="win.storage.space",
                grant=_ada(),
            )
            ran = {"n": 0}

            class _Count:
                def collect(self, procedure_id: str) -> dict:
                    ran["n"] += 1
                    return {"evidence_source": "mock", "mocked": True, "status": "collected", "ok": True, "problem_resolved": False}

            errors: list[BaseException] = []

            def _run() -> None:
                try:
                    second_store.accept(second_secret, race, provider=_Count())
                except RepairDenied as exc:
                    errors.append(exc)

            first = threading.Thread(target=_run)
            other = threading.Thread(target=_run)
            first.start()
            other.start()
            first.join()
            other.join()
            self.assertEqual(ran["n"], 1)
            self.assertEqual(len(errors), 1)

    def test_expiry_boundary_and_version_one_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 6_000.0}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            clock["now"] = float(envelope["expires_at"])
            with self.assertRaises(RepairDenied):
                store.accept(secret, envelope, provider=_MustNotRun())
            self.assertEqual(store.job_states[envelope["job_id"]]["lifecycle"], "expired")

            legacy = Path(tmp) / "legacy.json"
            key = "ab" * 32
            job_id = "job-legacy"
            legacy.write_text(json.dumps({
                "version": 1,
                "key": key,
                "devices": {"dev-1": {"device_id": "dev-1", "tenant_id": "acme", "secret_hash": "abc", "revoked": False, "repair_authority": False, "last_seen": None}},
                "jobs": [{"job_id": job_id, "tenant_id": "acme", "device_id": "dev-1", "nonce": "n-1", "expires_at": 9_000}],
                "job_states": {job_id: {"lifecycle": "issued"}},
                "nonces": [],
                "audit": [{"action": "issue", "job_id": job_id}],
            }), encoding="utf-8")
            loaded = DeviceStore(legacy, clock=lambda: 6_000.0)
            self.assertEqual(loaded.jobs[0]["job_id"], job_id)
            self.assertEqual(len(loaded.audit), 1)
            migrated = json.loads(legacy.read_text(encoding="utf-8"))
            self.assertEqual(migrated["version"], 2)
            self.assertNotIn("key", migrated)
            self.assertEqual((Path(str(legacy) + ".key")).read_text(encoding="utf-8").strip(), key)


if __name__ == "__main__":
    unittest.main()
