"""Live diagnostic parsing and the printer approval workflow.

Fixture and fake-provider tests are marked mocked. The Windows integration
tests run only on Windows and do not restart any service.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from windows_repair.device_store import DeviceStore
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
                store.issue(tenant_id="acme", device_id=other, procedure_id="win.storage.space", operator="ada")
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", operator="ada")
            provider = _Script([{"evidence_source": "mock", "mocked": True, "status": "collected", "problem_resolved": False}])
            first = store.accept(secret, envelope, provider=provider)
            self.assertEqual(first["evidence_source"], "mock")
            self.assertFalse(first["problem_resolved"])
            with self.assertRaises(RepairDenied):
                store.accept(secret, envelope, provider=provider)
            expired = store.issue(tenant_id="acme", device_id=device, procedure_id="print.diagnose", operator="ada")
            clock["now"] += 30
            with self.assertRaises(RepairDenied):
                store.accept(secret, expired, provider=provider)
            store.revoke("acme", device)
            clock["now"] += 1
            with self.assertRaises(RepairDenied):
                store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", operator="ada")

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


class DirectorGapTests(unittest.TestCase):
    def test_missing_files_are_not_healthy(self) -> None:
        from ops_centre.director import _endpoint_fleet, _repair_jobs

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENDPOINT_STATE_FILE", None)
            os.environ.pop("REPAIR_DEVICE_STATE", None)
            self.assertEqual(_endpoint_fleet("2026-10-19T00:00:00Z")["state"], "UNKNOWN")
            self.assertEqual(_repair_jobs("2026-10-19T00:00:00Z")["state"], "NOT CONFIGURED")


if __name__ == "__main__":
    unittest.main()
