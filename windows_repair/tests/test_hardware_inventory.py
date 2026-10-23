"""Hardware identity stays read-only. Synthetic fixtures are labelled synthetic."""
from __future__ import annotations

import inspect
import json
import os
import unittest

from windows_repair.hardware_inventory import (
    PROCEDURE_ID,
    SYNTHETIC_COMPLETE,
    SYNTHETIC_DENIED,
    SYNTHETIC_MISSING,
    assess_hardware_identity,
    collect_hardware_identity,
    stored_hardware,
)


def _complete(**overrides):
    payload = {
        "status": "collected",
        "manufacturer": "Example OEM",
        "model": "Example Model",
        "bios_vendor": "Example BIOS",
        "bios_version": "1.0",
        "cpu": "Example CPU",
        "memory_available_bytes": 1024,
        "memory_total_bytes": 2048,
    }
    payload.update(overrides)
    return payload


class HardwareIdentityTests(unittest.TestCase):
    def test_synthetic_complete_is_not_a_live_success(self) -> None:
        reading = assess_hardware_identity(SYNTHETIC_COMPLETE)
        self.assertEqual(reading["fixture"], "synthetic")
        self.assertFalse(reading["ok"])
        self.assertEqual(reading["evidence_source"], "unavailable")
        self.assertEqual(reading["status"], "unavailable")
        self.assertFalse(reading["problem_resolved"])
        stored = stored_hardware(reading)
        self.assertEqual(stored["status"], "unavailable")
        self.assertEqual(stored["manufacturer"], "")
        self.assertIsNone(stored["memory_total_bytes"])

    def test_synthetic_missing_and_denied_are_not_ok(self) -> None:
        missing = assess_hardware_identity(SYNTHETIC_MISSING)
        self.assertEqual(missing["fixture"], "synthetic")
        self.assertEqual(missing["status"], "unavailable")
        self.assertFalse(missing["ok"])
        denied = assess_hardware_identity(SYNTHETIC_DENIED)
        self.assertEqual(denied["fixture"], "synthetic")
        self.assertEqual(denied["status"], "permission-denied")
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["evidence_source"], "unavailable")
        self.assertEqual(denied["manufacturer"], "")
        unsupported = assess_hardware_identity({"status": "unsupported", "manufacturer": "Synthetic OEM"})
        self.assertEqual(unsupported["status"], "unsupported")
        self.assertFalse(unsupported["ok"])

    def test_live_shape_requires_every_identity_field(self) -> None:
        reading = assess_hardware_identity(_complete())
        self.assertTrue(reading["ok"])
        self.assertEqual(reading["evidence_source"], "live_windows")
        self.assertEqual(reading["status"], "collected")
        self.assertEqual(reading["fixture"], "")
        self.assertFalse(reading["problem_resolved"])
        stored = stored_hardware(reading)
        self.assertEqual(stored["status"], "collected")
        self.assertEqual(stored["bios"], "1.0 Example BIOS")
        self.assertEqual(stored["memory_available_bytes"], 1024)
        self.assertEqual(stored["memory_total_bytes"], 2048)
        for gap in (
            {"manufacturer": "  "},
            {"model": ""},
            {"bios_vendor": ""},
            {"bios_version": ""},
            {"cpu": ""},
            {"memory_available_bytes": None},
            {"memory_total_bytes": 0},
            {"memory_available_bytes": 50, "memory_total_bytes": 40},
            {"memory_total_bytes": True},
            {"memory_available_bytes": "1024; whoami"},
        ):
            with self.subTest(gap=sorted(gap)):
                incomplete = assess_hardware_identity(_complete(**gap))
                self.assertFalse(incomplete["ok"])
                self.assertNotEqual(incomplete["status"], "collected")
                self.assertEqual(incomplete["evidence_source"], "unavailable")

    def test_commands_paths_and_credentials_are_not_stored(self) -> None:
        hostile = _complete(
            fixture="synthetic",
            model="cmd /c whoami",
            cpu="powershell -enc AA",
            bios_version="C:\\Windows\\System32",
            command="Get-CimInstance",
            path="C:\\secret",
            credential="token=abc",
            serial="SECRET-SERIAL",
            password="hunter2",
        )
        reading = assess_hardware_identity(hostile)
        blob = json.dumps(reading).casefold()
        self.assertEqual(reading["fixture"], "synthetic")
        self.assertFalse(reading["ok"])
        self.assertNotIn("whoami", blob)
        self.assertNotIn("powershell", blob)
        self.assertNotIn("system32", blob)
        self.assertNotIn("hunter2", blob)
        self.assertNotIn("secret-serial", blob)
        for banned in ("command", "path", "credential", "serial", "password"):
            self.assertNotIn(banned, reading)
        self.assertLess(len(blob), 800)

    def test_unknown_fixture_and_non_object_are_unavailable(self) -> None:
        foreign = assess_hardware_identity(_complete(fixture="not-the-second-endpoint"))
        self.assertFalse(foreign["ok"])
        self.assertEqual(foreign["fixture"], "")
        self.assertNotIn("not-the-second-endpoint", json.dumps(foreign))
        self.assertFalse(assess_hardware_identity(["synthetic"]).get("ok"))
        self.assertEqual(assess_hardware_identity(None)["status"], "unavailable")

    def test_collector_does_not_accept_a_command_path_or_credential(self) -> None:
        names = set(inspect.signature(collect_hardware_identity).parameters)
        self.assertFalse(names & {"command", "path", "credential", "password", "secret", "argv"})
        denied = collect_hardware_identity(read="powershell -enc AA")  # type: ignore[arg-type]
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["status"], "unavailable")
        scripted = collect_hardware_identity(read=lambda: {
            "ok": False,
            "status": "failed",
            "detail": "Access is denied",
            "stderr": "Win32_BIOS Access is denied",
        })
        self.assertEqual(scripted["status"], "permission-denied")
        self.assertFalse(scripted["ok"])
        self.assertNotIn("Win32_BIOS", json.dumps(scripted))
        missing_tool = collect_hardware_identity(read=lambda: {
            "ok": False,
            "status": "tool_missing",
            "evidence_source": "unavailable",
        })
        self.assertEqual(missing_tool["status"], "unsupported")
        self.assertFalse(missing_tool["ok"])

    def test_registered_script_is_fixed_and_does_not_read_serials(self) -> None:
        from windows_repair.runner import SCRIPTS

        script = SCRIPTS["hardware_identity"].casefold()
        self.assertIn("win32_computersystem", script)
        self.assertIn("win32_bios", script)
        self.assertIn("win32_processor", script)
        self.assertIn("win32_operatingsystem", script)
        self.assertNotIn("serialnumber", script)
        self.assertNotIn("username", script)
        self.assertNotIn("invoke-expression", script)
        self.assertNotIn("set-netfirewallprofile", script)
        self.assertNotIn("pnputil", script)

    def test_runner_records_identity_without_a_repair(self) -> None:
        from windows_repair.engine import execute

        result = execute(PROCEDURE_ID, evidence={
            "manufacturer": "Synthetic OEM",
            "model": "Synthetic Model",
            "bios_vendor": "Synthetic BIOS",
            "bios_version": "S1.0",
            "cpu": "Synthetic CPU",
            "memory_available_bytes": 1024,
            "memory_total_bytes": 2048,
            "status": "collected",
            "fixture": "synthetic",
        })
        self.assertEqual(result["evidence_source"], "supplied")
        self.assertFalse(result["problem_resolved"])
        self.assertFalse(result["changed_device"])
        self.assertFalse(result["counts_as_second_endpoint"])
        self.assertIn("Synthetic OEM", " ".join(result["facts"]))
        self.assertIn("does not authorise a repair", " ".join(result["hypotheses"]))


@unittest.skipUnless(os.name == "nt", "Windows identity collector")
class LiveHardwareIdentityTests(unittest.TestCase):
    def test_this_pc_reading_is_permission_aware(self) -> None:
        collected = collect_hardware_identity(timeout=25)
        self.assertEqual(collected["procedure_id"], PROCEDURE_ID)
        self.assertIn(collected["status"], {"collected", "unavailable", "permission-denied", "unsupported"})
        self.assertFalse(collected["problem_resolved"])
        self.assertNotEqual(collected.get("fixture"), "synthetic")
        self.assertNotIn("serial", collected)
        blob = json.dumps(collected).casefold()
        self.assertNotIn("password", blob)
        self.assertNotRegex(blob, r"\b[a-z0-9]{5}(?:-[a-z0-9]{5}){4}\b")
        if collected["status"] != "collected":
            self.assertFalse(collected["ok"])
            self.assertEqual(collected["evidence_source"], "unavailable")
            self.assertEqual(stored_hardware(collected)["manufacturer"], "")
            return
        self.assertTrue(collected["ok"])
        self.assertEqual(collected["evidence_source"], "live_windows")
        for key in ("manufacturer", "model", "bios_vendor", "bios_version", "cpu"):
            self.assertIsInstance(collected[key], str)
            self.assertTrue(collected[key])
            self.assertLessEqual(len(collected[key]), 64)
        self.assertGreaterEqual(collected["memory_total_bytes"], 1)
        self.assertGreaterEqual(collected["memory_available_bytes"], 0)
        self.assertLessEqual(collected["memory_available_bytes"], collected["memory_total_bytes"])
        stored = stored_hardware(collected)
        self.assertEqual(stored["status"], "collected")
        self.assertLessEqual(len(json.dumps(stored)), 400)


if __name__ == "__main__":
    unittest.main()
