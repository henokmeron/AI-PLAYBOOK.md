"""Live diagnostic parsing and the printer approval workflow.

Fixture and fake-provider tests are marked mocked. The Windows integration
tests run only on Windows and do not restart any service.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from web.auth.store import SessionRecord
from windows_repair.device_store import DeviceStore, grant_from_session
from windows_repair.engine import RepairDenied
from windows_repair.printer_flow import PrinterWorkflow, classify_printer, default_restart
from windows_repair.providers import FixtureProvider, normalise_live
from windows_repair.remote_support import request_session, revoke_session, status_from_env
from windows_repair.runner import powershell_exe, run_argv


def _session(role: str = "operator", username: str = "ada", *, expired: bool = False) -> SessionRecord:
    now = time.time()
    end = now - 10 if expired else now + 3600
    return SessionRecord(
        session_id="sess-" + username,
        operator_id="op-" + username,
        username=username,
        role=role,
        csrf_token="csrf-" + username,
        created_at=now,
        last_seen=now,
        expires_at=end,
        absolute_expires_at=end,
    )


def _ada(tenant_id: str = "acme"):
    return grant_from_session(_session(), tenant_id)


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

    def test_new_collectors_drop_secrets_and_keep_counts(self) -> None:
        activation = normalise_live("win.activation.inspect", {
            "activation_status": "Licensed",
            "license_name": "Windows",
            "PartialProductKey": "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE",
        })
        activation_blob = json.dumps(activation)
        self.assertEqual(activation["evidence_source"], "live_windows")
        self.assertFalse(activation["mocked"])
        self.assertEqual(activation["activation_status"], "Licensed")
        self.assertNotIn("AAAAA", activation_blob)
        self.assertNotIn("PartialProductKey", activation)

        proxy = normalise_live("net.proxy.inspect", {
            "proxy": "user:secret@proxy.example:8080",
            "vpn": "connected",
            "winhttp": "direct",
            "ProxyPassword": "secret",
        })
        proxy_blob = json.dumps(proxy)
        self.assertNotIn("secret", proxy_blob)
        self.assertNotIn("@", proxy["proxy"])
        self.assertEqual(proxy["vpn"], "connected")
        self.assertNotIn("ProxyPassword", proxy)

        wifi = normalise_live("net.wifi.inspect", {
            "ssid": "Cafe",
            "radio": "Hardware On",
            "adapter_status": "Up",
            "signal_percent": 40,
            "KeyContent": "supersecret",
        })
        self.assertNotIn("supersecret", json.dumps(wifi))
        self.assertNotIn("KeyContent", wifi)
        self.assertEqual(wifi["ssid"], "Cafe")
        self.assertEqual(wifi["signal_percent"], 40)

        tls = normalise_live("net.tls.inspect", {
            "certificate_error": "none",
            "user_my_count": 2,
            "user_my_expired": 0,
            "user_my_expiring_30d": 1,
            "user_private_key_count": 1,
            "machine_root_count": 10,
            "schannel_error_count": 0,
            "schannel_ids": [36871, "nope"],
            "private_key_pem": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
        })
        tls_blob = json.dumps(tls)
        self.assertNotIn("BEGIN PRIVATE", tls_blob)
        self.assertEqual(tls["user_private_key_count"], 1)
        self.assertEqual(tls["schannel_ids"], [36871])
        self.assertEqual(tls["user_my_expiring_30d"], 1)

        permissions = normalise_live("app.permissions.inspect", {
            "path": "user_profile,temp,local_appdata",
            "access": "readable",
            "checks": [{"label": "temp", "exists": True, "access": "readable"}],
        })
        self.assertNotIn("\\", permissions["path"])
        self.assertEqual(permissions["checks"][0]["label"], "temp")

        crash = normalise_live("app.crash.evidence", {
            "application": "Application Error",
            "fault": "event_id=1000",
            "event_count": 1,
            "events": [{"Id": 1000, "ProviderName": "Application Error", "LevelDisplayName": "Error", "TimeCreated": "2026-10-22", "Message": "secret path"}],
        })
        self.assertNotIn("Message", json.dumps(crash))
        self.assertNotIn("secret path", json.dumps(crash))
        self.assertEqual(crash["events"][0]["provider"], "Application Error")

    def test_execute_forces_problem_resolved_false_for_new_collectors(self) -> None:
        from windows_repair.engine import execute

        class Provider:
            def collect(self, procedure_id: str, timeout: float = 18) -> dict:
                return {
                    "procedure_id": procedure_id,
                    "evidence_source": "live_windows",
                    "mocked": False,
                    "ok": True,
                    "status": "collected",
                    "problem_resolved": True,
                    "activation_status": "Notification",
                    "license_name": "Windows",
                    "PartialProductKey": "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE",
                    "devices": [{"name": "USB Input Device", "class": "USB", "status": "OK", "problem": ""}],
                    "device_count": 1,
                    "problem_count": 0,
                    "ssid": "Cafe",
                    "radio": "Hardware On",
                    "adapter_status": "Up",
                    "proxy": "direct",
                    "vpn": "none",
                    "certificate_error": "none",
                    "user_my_expiring_30d": 0,
                    "browser": "Microsoft Edge",
                    "error": "none",
                    "path": "user_profile,temp,local_appdata",
                    "access": "readable",
                    "application": "Application Error",
                    "fault": "event_id=1000",
                }

        for procedure_id in (
            "win.activation.inspect",
            "hw.usb.inspect",
            "net.wifi.inspect",
            "net.proxy.inspect",
            "net.tls.inspect",
            "app.browser.inspect",
            "app.permissions.inspect",
            "app.crash.evidence",
        ):
            with self.subTest(procedure_id=procedure_id):
                result = execute(procedure_id, provider=Provider())
                blob = json.dumps(result)
                self.assertEqual(result["evidence_source"], "live_windows")
                self.assertFalse(result["mocked"])
                self.assertFalse(result["problem_resolved"])
                self.assertFalse(result["changed_device"])
                self.assertEqual(result["status"], "diagnosed")
                self.assertNotIn("AAAAA", blob)
                self.assertNotRegex(blob, r"-----BEGIN")

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
        self.assertEqual(result["verification"], "not_independent")
        self.assertFalse(result["problem_resolved"])
        self.assertFalse(result["independent_verification"])
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

    def test_repair_without_a_recorded_approver_does_not_execute(self) -> None:
        """Fixture restarter. A blank or missing approver must not reach it."""
        provider = _Script([
            {"evidence_source": "fixture", "mocked": True, "spooler": "Stopped", "printers": [], "jobs": []},
            {"evidence_source": "fixture", "mocked": True, "spooler": "Running", "printers": [], "jobs": []},
        ])
        calls: list[dict] = []

        def _restarter(params: dict) -> dict:
            calls.append(dict(params))
            return {"executed": True, "changed_device": True, "status": "restarted"}

        flow = PrinterWorkflow(provider=provider, restarter=_restarter)
        requested = flow.request_restart("acme", "device-1", "requester@example.com")
        blank = flow.approve("acme", requested["approval_id"], " ")
        self.assertEqual(blank["status"], "approval_rejected")
        blocked = flow.execute_restart("acme", "device-1", requested["approval_id"], "operator@example.com")
        self.assertEqual(blocked["status"], "approval_rejected")
        self.assertFalse(blocked["executed"])
        self.assertFalse(blocked["changed_device"])
        self.assertEqual(calls, [])

        decided = flow.approve("acme", requested["approval_id"], "approver@example.com")
        self.assertEqual(decided["status"], "approved")
        flow.approvals._requests[requested["approval_id"]].approver = None
        missing = flow.execute_restart("acme", "device-1", requested["approval_id"], "operator@example.com")
        self.assertEqual(missing["status"], "approval_rejected")
        self.assertFalse(missing["executed"])
        self.assertFalse(missing["changed_device"])
        self.assertEqual(calls, [])
        self.assertTrue(all(row.get("action") != "repair" for row in flow.audit))

        with patch.dict(os.environ, {"WINDOWS_REPAIR_ALLOW_SERVICE_RESTART": "1"}):
            with patch("windows_repair.runner.run_argv", side_effect=AssertionError("spooler restart ran")):
                refused = default_restart({"device_id": "device-1", "service": "Spooler", "procedure_id": "print.spooler.restart"})
        self.assertEqual(refused["status"], "approval_required")
        self.assertFalse(refused["executed"])
        self.assertFalse(refused["changed_device"])


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

    def test_live_network_services_and_devices_do_not_repair(self) -> None:
        from windows_repair.engine import execute

        for procedure_id in ("net.diagnose", "win.services.inspect", "hw.devices.inventory"):
            with self.subTest(procedure_id=procedure_id):
                result = execute(procedure_id)
                self.assertEqual(result["evidence_source"], "live_windows")
                self.assertFalse(result["mocked"])
                self.assertFalse(result["problem_resolved"])
                self.assertFalse(result["changed_device"])
                blob = json.dumps(result)
                self.assertNotRegex(blob, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    def test_enrolled_device_runs_one_live_read_only_job(self) -> None:
        """In-process live check on this PC. The separate-process proof is the console worker test."""
        import time
        from windows_repair.providers import LiveWindowsProvider

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
            result = store.accept(secret, envelope, provider=LiveWindowsProvider())
            self.assertEqual(result["evidence_source"], "live_windows")
            self.assertFalse(result["mocked"])
            self.assertFalse(result["problem_resolved"])
            self.assertTrue(result["evidence_fresh"])
            self.assertFalse(result.get("repair_authority", False))
            self.assertGreater(int(result["collected_at_unix"]), int(time.time()) - 180)
            self.assertEqual(store.job_states[envelope["job_id"]]["lifecycle"], "accepted")
            self.assertGreaterEqual(store.summary()["live_accepted_jobs"], 1)
            self.assertNotIn(secret, json.dumps(store.summary()))

    def test_new_read_only_collectors_run_on_this_pc(self) -> None:
        from windows_repair.engine import execute
        from windows_repair.providers import LiveWindowsProvider

        provider = LiveWindowsProvider()
        secret_patterns = (
            r"\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}\b",
            r"(?i)key content",
            r"-----BEGIN",
            r"(?i)password\s*[:=]",
        )
        for procedure_id in (
            "win.activation.inspect",
            "hw.usb.inspect",
            "net.wifi.inspect",
            "net.proxy.inspect",
            "net.tls.inspect",
            "app.browser.inspect",
            "app.permissions.inspect",
            "app.crash.evidence",
        ):
            with self.subTest(procedure_id=procedure_id):
                collected = provider.collect(procedure_id, timeout=25)
                self.assertEqual(collected["evidence_source"], "live_windows", collected.get("detail"))
                self.assertTrue(collected.get("ok"), collected.get("detail"))
                self.assertFalse(collected["mocked"])
                self.assertFalse(collected["problem_resolved"])
                collected_blob = json.dumps(collected)
                for pattern in secret_patterns:
                    self.assertNotRegex(collected_blob, pattern)
                if procedure_id == "app.permissions.inspect":
                    self.assertNotIn("\\", str(collected.get("path")))
                    self.assertNotIn(":", str(collected.get("path")))
                if procedure_id == "net.proxy.inspect":
                    self.assertNotIn("@", str(collected.get("proxy")))
                result = execute(procedure_id, script_timeout=25)
                self.assertEqual(result["evidence_source"], "live_windows")
                self.assertFalse(result["problem_resolved"])
                self.assertFalse(result["changed_device"])
                self.assertEqual(result["status"], "diagnosed")
                result_blob = json.dumps(result)
                for pattern in secret_patterns:
                    self.assertNotRegex(result_blob, pattern)


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

    def test_unauthenticated_or_expired_heartbeat_is_not_a_healthy_check_in(self) -> None:
        """A bad secret is not stored. A later mock timestamp does not refresh an old live check-in."""
        import time

        now = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": now - 200_000}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            store.accept(secret, envelope, provider=_Script([{
                "evidence_source": "live_windows",
                "mocked": False,
                "status": "collected",
                "ok": True,
                "collected_at_unix": int(clock["now"]),
            }]))
            seen_before = store.devices[device]["last_seen"]
            clock["now"] = now
            with self.assertRaises(RepairDenied):
                store.check_in("not-a-real-device-secret-value!!")
            self.assertEqual(store.devices[device]["last_seen"], seen_before)
            store.check_in(secret)
            later = store.issue(tenant_id="acme", device_id=device, procedure_id="print.diagnose", grant=_ada())
            store.accept(secret, later, provider=_Script([{
                "evidence_source": "mock",
                "mocked": True,
                "status": "collected",
                "ok": True,
                "collected_at_unix": int(clock["now"]),
            }]))
            summary = store.summary()
            self.assertEqual(summary["live_accepted_jobs"], 0)
            self.assertGreater(summary["stale_evidence_jobs"], 0)
            self.assertGreater(summary["evidence_age_seconds"], 86400)
            report = DirectorGapTests()._director_repair(str(Path(tmp) / "device.json"))
            self.assertNotEqual(report["state"], "HEALTHY")
            self.assertEqual(report["state"], "DEGRADED")

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
                grant_from_session(_session(role="viewer"), "acme")
            with self.assertRaises(RepairDenied):
                grant_from_session("ada", "acme")
            with self.assertRaises(RepairDenied):
                grant_from_session(
                    SimpleNamespace(
                        session_id="s", operator_id="op", username="ada", role="operator",
                        csrf_token="csrf", expires_at=9_999_999_999, absolute_expires_at=9_999_999_999,
                    ),
                    "acme",
                )
            with self.assertRaises(RepairDenied):
                grant_from_session(_session(expired=True), "acme")
            other = grant_from_session(_session(), "otherco")
            with self.assertRaises(RepairDenied) as crossed:
                store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=other)
            self.assertIn("organisation", str(crossed.exception))
            self.assertEqual(store.summary()["issued_jobs"], 0)

    def test_console_module_path_is_still_a_real_session(self) -> None:
        web = Path(__file__).resolve().parents[2] / "web"
        sys.path.insert(0, str(web))
        from auth.store import SessionRecord as ConsoleSession

        now = time.time()
        console = ConsoleSession(
            session_id="sess-console",
            operator_id="op-console",
            username="admin",
            role="admin",
            csrf_token="csrf-console",
            created_at=now,
            last_seen=now,
            expires_at=now + 600,
            absolute_expires_at=now + 600,
        )
        grant = grant_from_session(console, "local-console")
        self.assertEqual(grant.username, "admin")
        self.assertIsNot(type(console), SessionRecord)

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


def _cross_process_accept(path: str, secret: str, envelope: dict, marker: str, now: float, queue) -> None:
    """Child process used to prove two processes cannot both collect one job."""
    import time as _time

    from windows_repair.device_store import DeviceStore as _Store
    from windows_repair.engine import RepairDenied as _Denied

    class _Slow:
        def collect(self, procedure_id: str) -> dict:
            with open(marker, "a", encoding="utf-8") as handle:
                handle.write("x")
                handle.flush()
            _time.sleep(0.4)
            return {
                "evidence_source": "mock",
                "mocked": True,
                "status": "collected",
                "ok": True,
                "problem_resolved": True,
            }

    try:
        store = _Store(Path(path), clock=lambda: now, ttl=30)
        result = store.accept(secret, envelope, provider=_Slow())
        queue.put("duplicate" if result.get("duplicate") else "accepted")
    except _Denied as exc:
        queue.put("denied:" + str(exc))
    except Exception as exc:
        queue.put("error:" + type(exc).__name__ + ":" + str(exc))


class DeviceStoreGuardTests(unittest.TestCase):
    """File permissions, crash safety, and diagnostic-only acceptance. Mock collectors are labelled."""

    def _store(self, tmp: str, clock: dict) -> tuple[DeviceStore, str, str]:
        store = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"], ttl=30)
        secret = "d" * 32
        device = store.enrol("acme", secret)
        return store, secret, device

    def test_private_acl_is_checked_and_permission_failure_keeps_the_previous_file(self) -> None:
        from integrations.state_guard import StatePermissionError, assert_private

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 8_000.0}
            root = Path(tmp) / "fresh"
            store = DeviceStore(root / "device.json", clock=lambda: clock["now"], ttl=30)
            secret = "d" * 32
            device = store.enrol("acme", secret)
            assert_private(root)
            assert_private(root / "device.json")
            assert_private(root / "device.json.key")
            assert_private(root / "device.json.lock")
            before = (root / "device.json").read_text(encoding="utf-8")
            with patch("windows_repair.device_store.restrict_private", side_effect=StatePermissionError("denied")):
                with self.assertRaises(RepairDenied) as denied:
                    store.enrol("acme", "e" * 32)
            self.assertIn("permissions", str(denied.exception))
            self.assertEqual((root / "device.json").read_text(encoding="utf-8"), before)
            reloaded = DeviceStore(root / "device.json", clock=lambda: clock["now"])
            self.assertIn(device, reloaded.devices)
            self.assertEqual(reloaded.summary()["device_count"], 1)
            self.assertNotIn(secret, before)

    def test_interrupted_replace_preserves_the_previous_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 8_100.0}
            store, _secret, device = self._store(tmp, clock)
            path = Path(tmp) / "device.json"
            before = path.read_text(encoding="utf-8")
            with patch("windows_repair.device_store.os.replace", side_effect=OSError("interrupted")):
                with self.assertRaises(RepairDenied):
                    store.enrol("acme", "e" * 32)
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            self.assertFalse(path.with_name("device.json.tmp").exists())
            reloaded = DeviceStore(path, clock=lambda: clock["now"])
            self.assertIn(device, reloaded.devices)
            self.assertEqual(reloaded.summary()["device_count"], 1)

    def test_symlink_and_bad_keys_fail_closed_without_dropping_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 8_200.0}
            store, _secret, device = self._store(tmp, clock)
            path = Path(tmp) / "device.json"
            before = path.read_text(encoding="utf-8")
            link = Path(tmp) / "linked.json"
            try:
                os.symlink(path, link)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaises(RepairDenied):
                DeviceStore(link, clock=lambda: clock["now"])
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            key_path = Path(str(path) + ".key")
            key_text = key_path.read_text(encoding="utf-8")
            key_path.unlink()
            os.symlink(path, key_path)
            with self.assertRaises(RepairDenied):
                DeviceStore(path, clock=lambda: clock["now"])
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            key_path.unlink()
            key_path.write_text(key_text, encoding="utf-8")
            reloaded = DeviceStore(path, clock=lambda: clock["now"])
            self.assertEqual(reloaded.devices[device]["device_id"], device)

            missing = Path(tmp) / "missing-key.json"
            missing.write_text(json.dumps({"version": 2, "devices": {"keep": {}}, "jobs": [], "nonces": []}), encoding="utf-8")
            missing_before = missing.read_text(encoding="utf-8")
            with self.assertRaises(RepairDenied):
                DeviceStore(missing, clock=lambda: clock["now"])
            self.assertEqual(missing.read_text(encoding="utf-8"), missing_before)

            broken_key = Path(tmp) / "bad-key.json"
            broken_key.write_text(before, encoding="utf-8")
            (Path(str(broken_key) + ".key")).write_text("not-a-key\n", encoding="utf-8")
            with self.assertRaises(RepairDenied):
                DeviceStore(broken_key, clock=lambda: clock["now"])
            self.assertEqual(broken_key.read_text(encoding="utf-8"), before)

            mismatched = Path(tmp) / "mismatch.json"
            payload = json.loads(before)
            payload["version"] = 1
            payload["key"] = "cd" * 32
            mismatched.write_text(json.dumps(payload), encoding="utf-8")
            (Path(str(mismatched) + ".key")).write_text(key_text, encoding="utf-8")
            mismatch_before = mismatched.read_text(encoding="utf-8")
            with self.assertRaises(RepairDenied):
                DeviceStore(mismatched, clock=lambda: clock["now"])
            self.assertEqual(mismatched.read_text(encoding="utf-8"), mismatch_before)

    def test_reported_symlink_is_refused(self) -> None:
        """Path.is_symlink is patched. This PC could not create a real symlink."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device.json"
            path.write_text("{}\n", encoding="utf-8")
            real = Path.is_symlink

            def fake(self: Path) -> bool:
                if self.name == "device.json":
                    return True
                return real(self)

            with patch.object(Path, "is_symlink", fake):
                with self.assertRaises(RepairDenied):
                    DeviceStore(path, clock=lambda: 8_200.0)
            self.assertEqual(path.read_text(encoding="utf-8"), "{}\n")

    def test_payload_fields_cannot_widen_a_diagnostic_job(self) -> None:
        import hashlib
        import hmac

        from windows_repair.device_store import _canonical

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 8_300.0}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            for field, value in (
                ("procedure_id", "print.spooler.restart"),
                ("approval_id", "apr-1"),
                ("lifecycle", "accepted"),
            ):
                mutated = dict(envelope)
                mutated[field] = value
                with self.assertRaises(RepairDenied) as denied:
                    store.accept(secret, mutated, provider=_MustNotRun())
                self.assertIn("signature", str(denied.exception))
            key = bytes.fromhex((Path(tmp) / "device.json.key").read_text(encoding="utf-8").strip())
            resigned = dict(envelope)
            resigned["procedure_id"] = "print.spooler.restart"
            resigned["approval_id"] = "apr-1"
            resigned["lifecycle"] = "accepted"
            body = {
                key_name: value
                for key_name, value in resigned.items()
                if key_name not in {"signature", "device_signature"}
            }
            resigned["signature"] = hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()
            with self.assertRaises(RepairDenied) as mismatched:
                store.accept(secret, resigned, provider=_MustNotRun())
            self.assertIn("does not match", str(mismatched.exception))

    def test_collector_cannot_declare_a_repair_successful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 8_400.0}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())

            class _Lie:
                def collect(self, procedure_id: str) -> dict:
                    return {
                        "evidence_source": "mock",
                        "mocked": True,
                        "status": "collected",
                        "ok": True,
                        "problem_resolved": True,
                    }

            result = store.accept(secret, envelope, provider=_Lie())
            self.assertFalse(result["problem_resolved"])
            self.assertTrue(result["mocked"])
            self.assertEqual(result["collected_by"], "endpoint_worker")
            self.assertFalse(store.job_states[envelope["job_id"]]["problem_resolved"])
            duplicate = store.record_result(secret, envelope, result)
            self.assertTrue(duplicate["duplicate"])
            self.assertFalse(duplicate["problem_resolved"])
            self.assertEqual(store.nonces.count(envelope["nonce"]), 1)

    def test_one_pull_claims_the_job_and_a_restart_keeps_that_claim(self) -> None:
        """Two workers must not both collect. A restarted console keeps the claim and a duplicate result."""
        import threading

        from integrations.endpoint_worker import execute_assigned_job

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 11_000.0}
            store = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"], ttl=300)
            secret = "d" * 32
            device = store.enrol("acme", secret)
            other = store.enrol("acme", "e" * 32)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            self.assertEqual(store.pending_jobs("e" * 32), [])
            self.assertEqual(store.pending_jobs(secret)[0]["job_id"], envelope["job_id"])
            self.assertEqual(store.pending_jobs(secret), [])
            path = Path(tmp) / "device.json"
            restarted = DeviceStore(path, clock=lambda: clock["now"])
            self.assertEqual(restarted.pending_jobs(secret), [])
            seen = {"n": 0}
            errors: list[BaseException] = []

            def _pull() -> None:
                try:
                    rows = store.pending_jobs(secret)
                    seen["n"] += len(rows)
                except RepairDenied as exc:
                    errors.append(exc)

            clock["now"] = 11_061.0
            first = threading.Thread(target=_pull)
            second = threading.Thread(target=_pull)
            first.start()
            second.start()
            first.join()
            second.join()
            self.assertEqual(errors, [])
            self.assertEqual(seen["n"], 1)

            class _Once:
                def collect(self, procedure_id: str) -> dict:
                    return {
                        "evidence_source": "mock",
                        "mocked": True,
                        "status": "collected",
                        "ok": True,
                        "problem_resolved": True,
                        "collected_at_unix": clock["now"],
                    }

            pulled = store.pending_jobs(secret)
            self.assertEqual(len(pulled), 0)
            clock["now"] = 11_122.0
            pulled = DeviceStore(path, clock=lambda: clock["now"]).pending_jobs(secret)
            self.assertEqual(len(pulled), 1)
            result = execute_assigned_job(
                pulled[0],
                device_id=device,
                tenant_id="acme",
                mac_key=store.mac_key(device),
                provider=_Once(),
                now=clock["now"],
            )
            self.assertFalse(result["problem_resolved"])
            recorded = store.record_result(secret, pulled[0], result)
            self.assertEqual(recorded["collected_by"], "endpoint_worker")
            self.assertFalse(recorded["problem_resolved"])
            recovered = DeviceStore(path, clock=lambda: clock["now"])
            duplicate = recovered.record_result(secret, pulled[0], result)
            self.assertTrue(duplicate["duplicate"])
            self.assertEqual(recovered.nonces.count(envelope["nonce"]), 1)
            self.assertEqual(recovered.pending_jobs(secret), [])
            self.assertNotEqual(other, device)

    def test_two_processes_cannot_both_collect(self) -> None:
        import multiprocessing

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 10_000.0}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            marker = Path(tmp) / "collects.txt"
            marker.write_text("", encoding="utf-8")
            ctx = multiprocessing.get_context("spawn")
            queue = ctx.Queue()
            procs = [
                ctx.Process(
                    target=_cross_process_accept,
                    args=(str(Path(tmp) / "device.json"), secret, envelope, str(marker), clock["now"], queue),
                )
                for _ in range(2)
            ]
            for proc in procs:
                proc.start()
            results = []
            for proc in procs:
                proc.join(20)
                if proc.is_alive():
                    proc.terminate()
                    proc.join(5)
                    self.fail("cross-process accept did not finish")
                self.assertEqual(proc.exitcode, 0)
                results.append(queue.get(timeout=5))
            self.assertEqual(sorted(item.split(":", 1)[0] for item in results), ["accepted", "denied"])
            self.assertEqual(marker.read_text(encoding="utf-8"), "x")
            reloaded = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"])
            self.assertEqual(reloaded.job_states[envelope["job_id"]]["lifecycle"], "accepted")
            self.assertFalse(reloaded.job_states[envelope["job_id"]]["problem_resolved"])
            self.assertEqual(reloaded.nonces.count(envelope["nonce"]), 1)
            follow = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"])
            follow.enrol("acme", "e" * 32)
            self.assertEqual(follow.summary()["device_count"], 2)

    def test_failed_accept_releases_the_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 10_100.0}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada())
            broken = dict(envelope)
            broken["signature"] = "0" * 64
            with self.assertRaises(RepairDenied):
                store.accept(secret, broken, provider=_MustNotRun())
            again = store.issue(tenant_id="acme", device_id=device, procedure_id="win.services.inspect", grant=_ada())
            self.assertEqual(again["procedure_id"], "win.services.inspect")
            self.assertNotEqual(again["job_id"], envelope["job_id"])

    def test_accepted_result_does_not_keep_the_result_signature(self) -> None:
        from integrations.endpoint_worker import execute_assigned_job

        class _Once:
            def collect(self, procedure_id: str) -> dict:
                return {
                    "evidence_source": "mock",
                    "mocked": True,
                    "status": "collected",
                    "ok": True,
                    "collected_at_unix": 10_000,
                }

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 10_000.0}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(
                tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada(),
            )
            result = execute_assigned_job(
                envelope,
                device_id=device,
                tenant_id="acme",
                mac_key=store.mac_key(device),
                provider=_Once(),
                now=clock["now"],
            )
            signature = result["result_signature"]
            recorded = store.record_result(secret, envelope, result)
            self.assertEqual(recorded.get("result_signature"), signature)
            raw = (Path(tmp) / "device.json").read_text(encoding="utf-8")
            self.assertNotIn(signature, raw)
            self.assertNotIn("result_signature", raw)
            reloaded = DeviceStore(Path(tmp) / "device.json", clock=lambda: clock["now"])
            stored = reloaded.job_states[envelope["job_id"]]["public_result"]
            self.assertNotIn("result_signature", stored)
            duplicate = reloaded.record_result(secret, envelope, result)
            self.assertTrue(duplicate["duplicate"])
            self.assertNotIn("result_signature", duplicate)
            self.assertNotIn(signature, json.dumps(duplicate))

    def test_changed_result_text_does_not_match_the_signature(self) -> None:
        from integrations.endpoint_worker import execute_assigned_job

        class _Once:
            def collect(self, procedure_id: str) -> dict:
                return {
                    "evidence_source": "mock",
                    "mocked": True,
                    "status": "collected",
                    "ok": True,
                    "collected_at_unix": 10_000,
                    "detail": "disk free is fine",
                }

        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 10_000.0}
            store, secret, device = self._store(tmp, clock)
            envelope = store.issue(
                tenant_id="acme", device_id=device, procedure_id="win.storage.space", grant=_ada(),
            )
            result = execute_assigned_job(
                envelope,
                device_id=device,
                tenant_id="acme",
                mac_key=store.mac_key(device),
                provider=_Once(),
                now=clock["now"],
            )
            self.assertEqual(result["detail"], "disk free is fine")
            self.assertTrue(result["mocked"])
            swapped = dict(result)
            swapped["detail"] = "restart the spooler now"
            swapped["mocked"] = False
            with self.assertRaises(RepairDenied):
                store.record_result(secret, envelope, swapped)
            recorded = store.record_result(secret, envelope, result)
            self.assertEqual(recorded["detail"], "disk free is fine")
            self.assertTrue(recorded["mocked"])
            self.assertNotIn("result_signature", (Path(tmp) / "device.json").read_text(encoding="utf-8"))
            stored = store.job_states[envelope["job_id"]]["public_result"]
            self.assertEqual(stored["detail"], "disk free is fine")
            self.assertTrue(stored["mocked"])
            self.assertNotIn("restart the spooler", json.dumps(stored))

    def test_http_issue_rejects_request_identity(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "web" / "server.py").read_text(encoding="utf-8")
        self.assertIn("grant_from_session(session, CONSOLE_TENANT)", source)
        self.assertIn("operator, tenant, and approval are not taken from the request", source)


if __name__ == "__main__":
    unittest.main()
