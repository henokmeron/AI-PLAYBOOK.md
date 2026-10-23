"""Read-only health checks. Fakes only. A synthetic fixture is not live success."""
from __future__ import annotations

import inspect
import json
import os
import unittest
from unittest.mock import patch

from integrations.endpoint import CHECK_SUMMARY_LIMIT, _CHECK_PROCEDURES
from integrations.endpoint_worker import _default_collector, summarise_live_check
from windows_repair.health_checks import (
    FIXED_SCRIPT,
    HEALTH_PROCEDURE_IDS,
    HEALTH_SUMMARY_LIMIT,
    _run_fixed_script,
    assess_check,
    collect_health_bundle,
    collect_health_check,
    readings_from_script_result,
)

_ORIGINAL = (
    "win.storage.space",
    "win.services.inspect",
    "win.update.inspect",
    "hw.devices.inventory",
    "print.diagnose",
    "net.diagnose",
    "win.events.recurring",
    "win.startup.inspect",
    "hw.identity.inspect",
)
_MUTATIONS = (
    "restart-service",
    "start-service",
    "stop-service",
    "set-service",
    "clear-printjob",
    "remove-printjob",
    "remove-item",
    "set-itemproperty",
    "new-itemproperty",
    "set-content",
    "add-content",
    "out-file",
    "restart-computer",
    "stop-computer",
    "shutdown",
    "invoke-webrequest",
    "invoke-expression",
    "invoke-command",
    "start-process",
    "pnputil",
    "reg add",
    "reg delete",
    "format-volume",
    "clear-disk",
    "repair-volume",
    "chkdsk",
)


def _bundle(**sections):
    payload = {
        "reboot": {"status": "collected", "pending": False, "sources_read": 3},
        "services": {"status": "collected", "failed": []},
        "queues": {"status": "collected", "printers": []},
        "storage": {"status": "collected", "source": "physical_disk", "disks": []},
        "devices": {"status": "collected", "problems": []},
        "errors": {"status": "collected", "error_count": 0, "window_hours": 24},
    }
    payload.update(sections)
    return {"ok": True, "payload": payload}


class HealthCheckTests(unittest.TestCase):
    def test_ids_extend_the_original_nine_without_replacing_recurring_events(self) -> None:
        self.assertEqual(HEALTH_SUMMARY_LIMIT, CHECK_SUMMARY_LIMIT)
        self.assertEqual(_CHECK_PROCEDURES[:9], _ORIGINAL)
        self.assertEqual(_CHECK_PROCEDURES[9:], HEALTH_PROCEDURE_IDS)
        self.assertTrue(set(HEALTH_PROCEDURE_IDS).isdisjoint(_ORIGINAL))
        self.assertIn("win.events.recurring", _CHECK_PROCEDURES)
        self.assertIn("win.events.recent", _CHECK_PROCEDURES)
        from windows_repair.runner import SCRIPTS

        self.assertIn("ProviderName", SCRIPTS["system_events"])
        self.assertNotIn("win.events.recent", SCRIPTS)

    def test_fixed_script_is_read_only_and_does_not_collect_serials(self) -> None:
        folded = FIXED_SCRIPT.casefold()
        runner = inspect.getsource(_run_fixed_script).casefold()
        for token in _MUTATIONS:
            self.assertNotIn(token, folded, token)
            self.assertNotIn(token, runner, token)
        self.assertNotIn("serialnumber", folded)
        self.assertNotIn("win32_logicaldisk", folded)
        self.assertNotIn("freespace", folded)
        for required in (
            "rebootpending",
            "rebootrequired",
            "pendingfilerenameoperations",
            "get-service",
            "get-printer",
            "get-physicaldisk",
            "get-pnpdevice",
            "get-winevent",
            "error_count",
            "friendlyname",
        ):
            self.assertIn(required, folded)
        self.assertNotIn("job document", folded)
        names = set()
        for fn in (assess_check, collect_health_bundle, collect_health_check):
            names.update(inspect.signature(fn).parameters)
        self.assertFalse(names & {"command", "path", "credential", "password", "secret", "argv", "shell"})

    def test_pending_reboot_is_reported_and_not_performed(self) -> None:
        pending = assess_check("win.reboot.pending", {
            "status": "collected",
            "pending": True,
            "sources_read": ["cbs", "windows_update", "pending_file_rename"],
        })
        self.assertTrue(pending["ok"])
        self.assertEqual(pending["evidence_source"], "live_windows")
        self.assertTrue(pending["pending"])
        self.assertEqual(pending["summary"], "pending=true")
        self.assertFalse(pending["problem_resolved"])
        self.assertNotIn("command", pending)
        clear = assess_check("win.reboot.pending", {
            "status": "collected",
            "pending": False,
            "sources_read": 3,
        })
        self.assertTrue(clear["ok"])
        self.assertFalse(clear["pending"])
        self.assertEqual(clear["summary"], "pending=false")
        for gap in (
            {"status": "collected"},
            {"status": "collected", "pending": True},
            {"status": "collected", "pending": "yes", "sources_read": 3},
            {"status": "collected", "pending": False, "sources_read": 0},
            None,
        ):
            with self.subTest(gap=gap):
                missing = assess_check("win.reboot.pending", gap)
                self.assertFalse(missing["ok"])
                self.assertEqual(missing["status"], "unavailable")
                self.assertNotIn("pending", missing)
        synthetic = assess_check("win.reboot.pending", {
            "fixture": "synthetic",
            "status": "collected",
            "pending": True,
            "sources_read": 3,
        })
        self.assertEqual(synthetic["fixture"], "synthetic")
        self.assertFalse(synthetic["ok"])
        self.assertEqual(synthetic["evidence_source"], "unavailable")
        denied = assess_check("win.reboot.pending", {
            "status": "permission-denied",
            "pending": True,
            "sources_read": 3,
        })
        self.assertEqual(denied["status"], "permission-denied")
        self.assertFalse(denied["ok"])
        foreign = assess_check("win.reboot.pending", {
            "fixture": "not-the-second-endpoint",
            "status": "collected",
            "pending": False,
            "sources_read": 3,
        })
        self.assertFalse(foreign["ok"])
        self.assertNotIn("not-the-second-endpoint", json.dumps(foreign))

    def test_failed_automatic_services_report_name_and_state_only(self) -> None:
        reading = assess_check("win.services.failed", {
            "status": "collected",
            "services": [
                {"name": "Spooler", "state": "Stopped", "start": "Automatic", "pathname": r"C:\Windows\System32\spoolsv.exe", "serial": "SERIAL-XYZZY-99"},
                {"name": "wuauserv", "state": "Running", "start": "Automatic"},
                {"name": "MapsBroker", "state": "Stopped", "start": "Manual"},
                {"name": "W32Time", "state": 1, "start": "AutomaticDelayedStart"},
            ],
        })
        self.assertTrue(reading["ok"])
        self.assertEqual(reading["failed_count"], 2)
        self.assertEqual(reading["failed"], [
            {"name": "Spooler", "state": "Stopped"},
            {"name": "W32Time", "state": "Stopped"},
        ])
        self.assertEqual(reading["summary"], "failed=2; Spooler=Stopped; W32Time=Stopped")
        blob = json.dumps(reading).casefold()
        self.assertNotIn("spoolsv", blob)
        self.assertNotIn("system32", blob)
        self.assertNotIn("serial-xyzzy-99", blob)
        self.assertNotIn("restart", blob)
        empty = assess_check("win.services.failed", {"status": "collected", "failed": []})
        self.assertTrue(empty["ok"])
        self.assertEqual(empty["failed_count"], 0)
        self.assertEqual(empty["summary"], "failed=0")
        missing = assess_check("win.services.failed", {"status": "collected"})
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["status"], "unavailable")
        hostile = assess_check("win.services.failed", {
            "status": "collected",
            "failed": [{"name": "powershell -enc AA", "state": "Stopped"}],
        })
        self.assertFalse(hostile["ok"])
        self.assertNotIn("powershell", json.dumps(hostile).casefold())

    def test_printer_queue_depth_is_reported_and_not_cleared(self) -> None:
        reading = assess_check("print.queue.depth", {
            "status": "collected",
            "printers": [
                {"name": "Office", "depth": 3, "document": "secret-payroll.docx", "user": "job-owner-ada"},
                {"name": "Lab", "JobCount": 1},
            ],
        })
        self.assertTrue(reading["ok"])
        self.assertEqual(reading["depth"], 4)
        self.assertEqual(reading["printers"], [
            {"name": "Office", "depth": 3},
            {"name": "Lab", "depth": 1},
        ])
        self.assertIn("depth=4", reading["summary"])
        blob = json.dumps(reading).casefold()
        self.assertNotIn("secret-payroll", blob)
        self.assertNotIn("job-owner-ada", blob)
        self.assertNotIn("clear", blob)
        empty = assess_check("print.queue.depth", {"status": "collected", "queues": []})
        self.assertTrue(empty["ok"])
        self.assertEqual(empty["depth"], 0)
        missing = assess_check("print.queue.depth", {"status": "collected"})
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["status"], "unavailable")
        unsupported = assess_check("print.queue.depth", {"status": "unsupported", "printers": []})
        self.assertEqual(unsupported["status"], "unsupported")
        self.assertFalse(unsupported["ok"])

    def test_storage_health_ignores_free_space_and_a_missing_source(self) -> None:
        free_only = assess_check("win.storage.health", {
            "status": "collected",
            "disks": [{"device": "C:", "free": 10, "size": 100}],
        })
        self.assertFalse(free_only["ok"])
        self.assertEqual(free_only["status"], "unavailable")
        self.assertNotEqual(free_only["status"], "collected")
        no_source = assess_check("win.storage.health", {
            "status": "collected",
            "disks": [{"name": "Disk0", "health": "Healthy", "free": 10}],
        })
        self.assertFalse(no_source["ok"])
        self.assertEqual(no_source["status"], "unavailable")
        logical = assess_check("win.storage.health", {
            "status": "collected",
            "source": "logical_disk",
            "disks": [{"name": "C:", "health": "Healthy"}],
        })
        self.assertFalse(logical["ok"])
        healthy = assess_check("win.storage.health", {
            "status": "collected",
            "source": "physical_disk",
            "disks": [{
                "name": "Disk0",
                "health": "Healthy",
                "operational": "OK",
                "free": 10,
                "serial": "SERIAL-XYZZY-99",
            }],
        })
        self.assertTrue(healthy["ok"])
        self.assertEqual(healthy["evidence_source"], "live_windows")
        self.assertEqual(healthy["disks"], [{"name": "Disk0", "health": "Healthy", "operational": "OK"}])
        self.assertEqual(healthy["unhealthy"], 0)
        self.assertNotIn("SERIAL-XYZZY-99", json.dumps(healthy))
        self.assertNotIn("free", healthy["disks"][0])
        unknown = assess_check("win.storage.health", {
            "status": "collected",
            "source": "physical_disk",
            "disks": [{"name": "Disk0", "health": "Unknown"}],
        })
        self.assertFalse(unknown["ok"])
        self.assertEqual(unknown["status"], "unavailable")
        warning = assess_check("win.storage.health", {
            "status": "collected",
            "source": "storage_reliability",
            "volumes": [{"name": "Disk1", "HealthStatus": "Warning"}],
        })
        self.assertTrue(warning["ok"])
        self.assertEqual(warning["unhealthy"], 1)
        self.assertIn("Disk1=Warning", warning["summary"])
        empty = assess_check("win.storage.health", {
            "status": "collected",
            "source": "physical_disk",
            "disks": [],
        })
        self.assertTrue(empty["ok"])
        self.assertEqual(empty["summary"], "disks=0")

    def test_problem_devices_keep_name_class_and_code_only(self) -> None:
        reading = assess_check("hw.devices.problems", {
            "status": "collected",
            "problems": [
                {
                    "name": "Camera",
                    "class": "Camera",
                    "problem": "CM_PROB_FAILED_START",
                    "serial": "SERIAL-XYZZY-99",
                    "InstanceId": r"USB\VID_1234\SERIAL-XYZZY-99",
                },
                {"FriendlyName": "Mouse", "Class": "Mouse", "Problem": "CM_PROB_NONE"},
                {"name": "Audio", "class": "MEDIA", "problem": 28},
            ],
        })
        self.assertTrue(reading["ok"])
        self.assertEqual(reading["problem_count"], 2)
        self.assertEqual(reading["problems"], [
            {"name": "Camera", "class": "Camera", "problem": "CM_PROB_FAILED_START"},
            {"name": "Audio", "class": "MEDIA", "problem": "28"},
        ])
        blob = json.dumps(reading)
        self.assertNotIn("SERIAL-XYZZY-99", blob)
        self.assertNotIn("VID_1234", blob)
        self.assertNotIn("serial", blob.casefold())
        none = assess_check("hw.devices.problems", {"status": "collected", "devices": []})
        self.assertTrue(none["ok"])
        self.assertEqual(none["problem_count"], 0)
        missing = assess_check("hw.devices.problems", {"status": "collected"})
        self.assertFalse(missing["ok"])
        junk = assess_check("hw.devices.problems", {
            "status": "collected",
            "problems": [{"serial": "SERIAL-XYZZY-99"}],
        })
        self.assertFalse(junk["ok"])
        self.assertNotIn("SERIAL-XYZZY-99", json.dumps(junk))

    def test_recent_error_count_does_not_copy_the_recurring_event_list(self) -> None:
        counted = assess_check("win.events.recent", {
            "status": "collected",
            "error_count": 4,
            "window_hours": 24,
            "events": [{"Id": 41, "ProviderName": "Disk", "LevelDisplayName": "Error"}],
        })
        self.assertTrue(counted["ok"])
        self.assertEqual(counted["error_count"], 4)
        self.assertEqual(counted["window_hours"], 24)
        self.assertFalse(counted["truncated"])
        self.assertNotIn("events", counted)
        self.assertNotIn("Disk", json.dumps(counted))
        self.assertNotEqual(counted["procedure_id"], "win.events.recurring")
        zero = assess_check("win.events.recent", {"status": "collected", "error_count": 0, "window_hours": 24})
        self.assertTrue(zero["ok"])
        self.assertEqual(zero["summary"], "error_count=0; window_hours=24")
        listed = assess_check("win.events.recent", {
            "status": "collected",
            "events": [{"Id": 41, "ProviderName": "Disk"}],
            "window_hours": 24,
        })
        self.assertFalse(listed["ok"])
        self.assertEqual(listed["status"], "unavailable")
        self.assertNotIn("Disk", json.dumps(listed))
        self.assertNotIn("events", listed)
        for bad in (True, -1, None):
            with self.subTest(bad=bad):
                reading = assess_check("win.events.recent", {"status": "collected", "error_count": bad})
                self.assertFalse(reading["ok"])
        capped = assess_check("win.events.recent", {
            "status": "collected",
            "error_count": 200,
            "window_hours": 24,
            "capped_at": 200,
        })
        self.assertTrue(capped["truncated"])
        self.assertIn("truncated=true", capped["summary"])

    def test_one_section_failure_does_not_hide_the_others(self) -> None:
        bundle = readings_from_script_result(_bundle(
            services={"status": "permission-denied"},
            storage={"status": "unsupported"},
            devices={
                "status": "collected",
                "problems": [{
                    "name": "Camera",
                    "class": "Camera",
                    "problem": "CM_PROB_FAILED_START",
                    "serial": "NOPE-SERIAL",
                }],
            },
        ))
        self.assertEqual(set(bundle), set(HEALTH_PROCEDURE_IDS))
        self.assertTrue(bundle["win.reboot.pending"]["ok"])
        self.assertFalse(bundle["win.reboot.pending"]["pending"])
        self.assertEqual(bundle["win.services.failed"]["status"], "permission-denied")
        self.assertFalse(bundle["win.services.failed"]["ok"])
        self.assertTrue(bundle["print.queue.depth"]["ok"])
        self.assertEqual(bundle["print.queue.depth"]["depth"], 0)
        self.assertEqual(bundle["win.storage.health"]["status"], "unsupported")
        self.assertFalse(bundle["win.storage.health"]["ok"])
        self.assertTrue(bundle["hw.devices.problems"]["ok"])
        self.assertNotIn("NOPE-SERIAL", json.dumps(bundle))
        self.assertTrue(bundle["win.events.recent"]["ok"])
        self.assertEqual(bundle["win.events.recent"]["error_count"], 0)
        denied = readings_from_script_result({
            "ok": False,
            "status": "failed",
            "stderr": "Access is denied",
        })
        self.assertTrue(all(item["status"] == "permission-denied" and not item["ok"] for item in denied.values()))
        missing_tool = readings_from_script_result({"ok": False, "status": "tool_missing"})
        self.assertTrue(all(item["status"] == "unsupported" and not item["ok"] for item in missing_tool.values()))
        self.assertTrue(all(not item["ok"] for item in readings_from_script_result(None).values()))
        wrapper = _bundle()
        wrapper["payload"]["fixture"] = "synthetic"
        labelled = readings_from_script_result(wrapper)
        self.assertTrue(all(item["fixture"] == "synthetic" and not item["ok"] for item in labelled.values()))

    def test_fakes_do_not_call_the_fixed_script(self) -> None:
        def fake():
            return _bundle(reboot={"status": "collected", "pending": True, "sources_read": 2})

        with patch("windows_repair.runner.run_argv", side_effect=AssertionError("script ran")):
            bundle = collect_health_bundle(read=fake)
            denied = collect_health_bundle(read="powershell -enc AA")  # type: ignore[arg-type]
            unknown = collect_health_check("win.events.recurring", read=fake)
        self.assertTrue(bundle["win.reboot.pending"]["pending"])
        self.assertTrue(all(not item["ok"] and item["status"] == "unavailable" for item in denied.values()))
        self.assertFalse(unknown["ok"])
        self.assertEqual(unknown["procedure_id"], "win.events.recurring")
        long_names = assess_check("win.services.failed", {
            "status": "collected",
            "failed": [{"name": f"Svc{index}", "state": "Stopped"} for index in range(8)],
        })
        self.assertLessEqual(len(long_names["summary"]), CHECK_SUMMARY_LIMIT)
        self.assertTrue(long_names["summary"].startswith("failed=8"))
        summarised = summarise_live_check("win.reboot.pending", bundle["win.reboot.pending"], 200)
        self.assertTrue(summarised["ok"])
        self.assertEqual(summarised["summary"], "pending=true")
        self.assertEqual(summarised["evidence_source"], "live_windows")

    def test_worker_routes_health_checks_without_running_a_script(self) -> None:
        calls = {"n": 0}

        def bundle():
            calls["n"] += 1
            return {
                procedure_id: {
                    "ok": True,
                    "evidence_source": "live_windows",
                    "status": "collected",
                    "summary": "pending=false",
                }
                for procedure_id in HEALTH_PROCEDURE_IDS
            }

        box: dict = {}
        with patch("windows_repair.runner.run_argv", side_effect=AssertionError("script ran")):
            with patch("windows_repair.health_checks.collect_health_bundle", side_effect=bundle):
                first = _default_collector("win.reboot.pending", box)
                second = _default_collector("win.events.recent", box)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(first["summary"], "pending=false")
        self.assertEqual(second["summary"], "pending=false")
        self.assertIn("health_bundle", box)

    @unittest.skipUnless(os.name == "nt", "Windows provider path")
    def test_existing_storage_check_still_uses_the_provider(self) -> None:
        with patch("windows_repair.runner.run_argv", side_effect=AssertionError("script ran")):
            with patch(
                "windows_repair.providers.LiveWindowsProvider.collect",
                return_value={"ok": True, "evidence_source": "live_windows", "detail": "fake"},
            ) as collect:
                raw = _default_collector("win.storage.space", {})
        collect.assert_called_once()
        self.assertEqual(collect.call_args[0][0], "win.storage.space")
        self.assertEqual(raw["detail"], "fake")

    def test_unpatched_collector_receives_the_fixed_script_and_does_not_succeed(self) -> None:
        from windows_repair import runner

        with patch(
            "windows_repair.runner.run_argv",
            return_value={"ok": False, "status": "failed", "evidence_source": "unavailable"},
        ) as run:
            bundle = collect_health_bundle()
        self.assertTrue(all(not item["ok"] for item in bundle.values()))
        if runner.powershell_exe() is None:
            self.assertFalse(run.called)
            self.assertTrue(all(item["status"] == "unsupported" for item in bundle.values()))
            return
        argv = run.call_args[0][0]
        self.assertEqual(argv[1:], ["-NoProfile", "-NonInteractive", "-Command", FIXED_SCRIPT])
        self.assertNotIn("restart-service", " ".join(argv).casefold())


if __name__ == "__main__":
    unittest.main()
