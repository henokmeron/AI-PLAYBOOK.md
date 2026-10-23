"""Device health stays read-only. Driver install is a refusal or a plan, never a download."""
from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path

from windows_repair.driver_health import (
    ALLOWED_SOURCES,
    PROCEDURE_ID,
    SYNTHETIC_COMPLETE,
    SYNTHETIC_DENIED,
    SYNTHETIC_MISSING,
    assess_device_health,
    collect_device_health,
    install_driver,
    propose_driver_install,
)

_FIELDS = ("name", "class", "problem_code", "driver_version", "driver_provider", "driver_date")
_GAP = {"unavailable", "unsupported", "permission-denied"}


def _complete(**overrides):
    device = {
        "name": "USB Audio",
        "class": "MEDIA",
        "problem_code": 28,
        "driver_version": "10.0.19041.1",
        "driver_provider": "Microsoft",
        "driver_date": "2024-05-01",
    }
    device.update(overrides)
    return {"status": "collected", "devices": [device]}


def _approval(**overrides):
    body = {
        "device_id": "dev-audio-1",
        "action_id": "act-9",
        "device_target": "USB Audio",
        "source": "windows-update",
        "downloaded": True,
        "executed": True,
    }
    body.update(overrides)
    return body


class DriverHealthTests(unittest.TestCase):
    def _assert_gap(self, reading: dict) -> None:
        self.assertFalse(reading["ok"])
        self.assertIn(reading["status"], _GAP)
        self.assertNotEqual(reading["status"], "ok")
        self.assertNotEqual(reading["evidence_source"], "live_windows")
        self.assertEqual(reading["evidence_source"], "unavailable")
        self.assertFalse(reading["problem_resolved"])
        self.assertFalse(reading["changed_device"])
        self.assertFalse(reading["downloaded"])
        for device in reading["devices"]:
            self.assertNotEqual(device["status"], "ok")
            for field in _FIELDS:
                self.assertNotEqual(device[field], "ok")

    def test_synthetic_complete_is_not_a_live_success(self) -> None:
        reading = assess_device_health(SYNTHETIC_COMPLETE)
        self.assertEqual(reading["procedure_id"], PROCEDURE_ID)
        self.assertEqual(reading["fixture"], "synthetic")
        self._assert_gap(reading)
        self.assertEqual(reading["status"], "unavailable")
        self.assertEqual(reading["devices"], [])
        blob = json.dumps(reading)
        self.assertNotIn("Synthetic Audio", blob)
        self.assertNotIn("Synthetic Provider", blob)
        self.assertNotIn("live_windows", blob)

    def test_synthetic_missing_and_denied_are_not_ok(self) -> None:
        missing = assess_device_health(SYNTHETIC_MISSING)
        self.assertEqual(missing["fixture"], "synthetic")
        self._assert_gap(missing)
        self.assertEqual(missing["devices"], [])
        denied = assess_device_health(SYNTHETIC_DENIED)
        self.assertEqual(denied["fixture"], "synthetic")
        self.assertEqual(denied["status"], "permission-denied")
        self._assert_gap(denied)
        self.assertNotIn("Synthetic Audio", json.dumps(denied))
        unsupported = assess_device_health({"status": "unsupported", "devices": [{"name": "USB Audio"}]})
        self.assertEqual(unsupported["status"], "unsupported")
        self._assert_gap(unsupported)
        self.assertEqual(unsupported["devices"], [])

    def test_missing_fields_are_gap_statuses_never_ok(self) -> None:
        missing_date = assess_device_health(_complete(driver_date=""))
        self._assert_gap(missing_date)
        self.assertEqual(missing_date["devices"][0]["driver_date"], "unavailable")
        self.assertEqual(missing_date["devices"][0]["name"], "USB Audio")
        self.assertFalse(missing_date["devices"][0]["ok"])

        denied_version = assess_device_health(_complete(
            driver_version="",
            driver_date="",
            field_status={"driver_version": "permission-denied", "driver_date": "ok"},
        ))
        self.assertEqual(denied_version["status"], "permission-denied")
        self.assertEqual(denied_version["devices"][0]["driver_version"], "permission-denied")
        self.assertEqual(denied_version["devices"][0]["driver_date"], "unavailable")
        self._assert_gap(denied_version)

        unsupported_class = assess_device_health(_complete(
            **{"class": ""},
            field_status={"class": "unsupported"},
        ))
        self.assertEqual(unsupported_class["devices"][0]["class"], "unsupported")
        self.assertEqual(unsupported_class["status"], "unsupported")
        self._assert_gap(unsupported_class)

        empty = assess_device_health({"status": "collected", "devices": []})
        self._assert_gap(empty)
        self.assertEqual(empty["devices"], [])

        mixed = assess_device_health({
            "status": "collected",
            "devices": [
                _complete()["devices"][0],
                {"name": "Second Device", "class": "USB", "problem_code": 0},
            ],
        })
        self._assert_gap(mixed)
        self.assertEqual(mixed["devices"][1]["driver_provider"], "unavailable")
        self.assertTrue(mixed["devices"][0]["ok"])
        self.assertFalse(mixed["ok"])

    def test_complete_supplied_reading_keeps_present_fields(self) -> None:
        reading = assess_device_health(_complete())
        self.assertTrue(reading["ok"])
        self.assertEqual(reading["status"], "collected")
        self.assertEqual(reading["evidence_source"], "supplied")
        self.assertNotEqual(reading["evidence_source"], "live_windows")
        self.assertEqual(reading["fixture"], "")
        self.assertFalse(reading["problem_resolved"])
        device = reading["devices"][0]
        self.assertEqual(device["name"], "USB Audio")
        self.assertEqual(device["class"], "MEDIA")
        self.assertEqual(device["problem_code"], "28")
        self.assertEqual(device["driver_version"], "10.0.19041.1")
        self.assertEqual(device["driver_provider"], "Microsoft")
        self.assertEqual(device["driver_date"], "2024-05-01")
        self.assertTrue(device["ok"])
        self.assertFalse(reading["downloaded"])

        coded = assess_device_health(_complete(
            problem_code="CM_PROB_NONE",
            driver_date="20240501000000.000000-000",
            DriverProviderName="Microsoft",
        ))
        self.assertEqual(coded["devices"][0]["problem_code"], "CM_PROB_NONE")
        self.assertEqual(coded["devices"][0]["driver_date"], "2024-05-01")
        self.assertTrue(coded["ok"])

        for gap in (
            {"problem_code": None},
            {"problem_code": True},
            {"problem_code": 99},
            {"driver_version": "10.0.1.1; whoami"},
            {"driver_date": "not-a-date"},
            {"class": ""},
            {"name": "   "},
        ):
            with self.subTest(gap=sorted(gap)):
                incomplete = assess_device_health(_complete(**gap))
                self._assert_gap(incomplete)
                self.assertNotIn("whoami", json.dumps(incomplete))

        labelled = assess_device_health({**_complete(), "evidence_source": "live_windows"})
        self.assertEqual(labelled["evidence_source"], "supplied")
        self.assertTrue(labelled["ok"])

    def test_serial_numbers_commands_and_urls_are_not_stored(self) -> None:
        hostile = _complete(
            serial="SECRET-SERIAL-99",
            SerialNumber="ABC123456",
            PNPDeviceID=r"USB\VID_1234&PID_5678\SERIAL99",
            HardwareID=r"PCI\VEN_8086&DEV_1234",
        )
        hostile["devices"][0]["command"] = "Get-PnpDevice"
        hostile["credential"] = "token=abc"
        reading = assess_device_health(hostile)
        blob = json.dumps(reading).casefold()
        self.assertTrue(reading["ok"])
        self.assertNotIn("secret-serial", blob)
        self.assertNotIn("abc123456", blob)
        self.assertNotIn("vid_1234", blob)
        self.assertNotIn("serial99", blob)
        self.assertNotIn("ven_8086", blob)
        self.assertNotIn("token=abc", blob)
        self.assertNotIn("get-pnpdevice", blob)
        for banned in ("serial", "SerialNumber", "PNPDeviceID", "HardwareID", "command", "credential"):
            self.assertNotIn(banned, reading)
            self.assertNotIn(banned, reading["devices"][0])

        commanded = assess_device_health(_complete(name="cmd /c whoami", driver_provider="powershell -enc AA"))
        blob = json.dumps(commanded).casefold()
        self._assert_gap(commanded)
        self.assertNotIn("whoami", blob)
        self.assertNotIn("powershell", blob)

    def test_unknown_fixture_and_non_object_are_unavailable(self) -> None:
        foreign_payload = _complete()
        foreign_payload["fixture"] = "not-the-second-endpoint"
        foreign = assess_device_health(foreign_payload)
        self._assert_gap(foreign)
        self.assertEqual(foreign["fixture"], "")
        self.assertNotIn("not-the-second-endpoint", json.dumps(foreign))
        self.assertFalse(assess_device_health(["synthetic"]).get("ok"))
        self.assertEqual(assess_device_health(None)["status"], "unavailable")
        crowded = assess_device_health({
            "status": "collected",
            "devices": [{"name": f"Device {index}", "class": "USB"} for index in range(33)],
        })
        self._assert_gap(crowded)
        self.assertEqual(crowded["devices"], [])
        self.assertNotIn("Device 32", json.dumps(crowded))

    def test_collector_uses_fakes_and_does_not_take_a_command(self) -> None:
        names = set(inspect.signature(collect_device_health).parameters)
        self.assertFalse(names & {"command", "path", "credential", "password", "secret", "argv", "url"})
        self.assertEqual(collect_device_health()["status"], "unavailable")
        denied = collect_device_health(read="powershell -enc AA")  # type: ignore[arg-type]
        self._assert_gap(denied)
        scripted = collect_device_health(read=lambda: {
            "ok": False,
            "status": "failed",
            "detail": "Access is denied",
            "stderr": "SerialNumber SECRET-SERIAL Win32_PnPEntity",
        })
        self.assertEqual(scripted["status"], "permission-denied")
        self._assert_gap(scripted)
        self.assertNotIn("SECRET-SERIAL", json.dumps(scripted))
        self.assertNotIn("Win32", json.dumps(scripted))
        missing_tool = collect_device_health(read=lambda: {"ok": False, "status": "tool_missing"})
        self.assertEqual(missing_tool["status"], "unsupported")
        self._assert_gap(missing_tool)
        supplied = collect_device_health(read=lambda: {"ok": True, "payload": _complete()})
        self.assertTrue(supplied["ok"])
        self.assertEqual(supplied["evidence_source"], "supplied")
        self.assertNotEqual(supplied["evidence_source"], "live_windows")
        def _boom() -> dict:
            raise RuntimeError("secret path")

        crashed = collect_device_health(read=_boom)
        self.assertEqual(crashed["status"], "unavailable")
        self.assertNotIn("secret path", json.dumps(crashed))

    def test_propose_refuses_by_default_and_names_only_allowed_sources(self) -> None:
        refused = propose_driver_install()
        self.assertEqual(refused["status"], "refused")
        self.assertTrue(refused["refused"])
        self.assertEqual(refused["reason"], "default-refuse")
        self.assertFalse(refused["source_eligible"])
        self.assertFalse(refused["downloaded"])
        self.assertFalse(refused["executed"])
        self.assertIsNone(refused["would_run"])
        self.assertEqual(refused["allowed_sources"], list(ALLOWED_SOURCES))

        for source in ("windows-update", "pnputil", "PNPUTIL"):
            with self.subTest(source=source):
                named = propose_driver_install(source=source, approval=_approval(source=source))
                self.assertEqual(named["status"], "refused")
                self.assertTrue(named["refused"])
                self.assertTrue(named["source_eligible"])
                self.assertEqual(named["source"], source.strip().casefold())
                self.assertFalse(named["downloaded"])
                self.assertFalse(named["executed"])
                self.assertIsNone(named["would_run"])
                self.assertFalse(named["problem_resolved"])

        other = propose_driver_install(source=r"C:\secret-driver-pack\oem.inf")
        self.assertEqual(other["reason"], "source-not-allowed")
        self.assertNotIn("secret-driver-pack", json.dumps(other))
        self.assertEqual(other["source"], "")

    def test_arbitrary_url_is_refused_even_with_approval(self) -> None:
        marker = "https://driver-pack.example/oem.inf"
        approval = _approval(source=marker, device_target="USB Audio")
        proposed = propose_driver_install(source=marker, approval=approval)
        installed = install_driver(
            approval,
            device_id="dev-audio-1",
            action_id="act-9",
            device_target="USB Audio",
        )
        for result in (proposed, installed):
            self.assertEqual(result["status"], "refused")
            self.assertEqual(result["reason"], "arbitrary-url")
            self.assertTrue(result["refused"])
            self.assertFalse(result["downloaded"])
            self.assertFalse(result["executed"])
            self.assertIsNone(result["would_run"])
            blob = json.dumps(result)
            self.assertNotIn("driver-pack.example", blob)
            self.assertNotIn("http", blob)
        hidden = install_driver(_approval(download_url=marker))
        self.assertEqual(hidden["reason"], "arbitrary-url")
        self.assertNotIn("driver-pack.example", json.dumps(hidden))
        self.assertEqual(propose_driver_install(source="file://C:/drivers/x.inf")["reason"], "arbitrary-url")
        self.assertEqual(propose_driver_install(source=r"\\server\share\driver.inf")["reason"], "arbitrary-url")

    def test_install_refuses_until_approval_names_the_exact_target(self) -> None:
        self.assertEqual(install_driver(None)["reason"], "approval-missing")
        self.assertEqual(install_driver(["windows-update"])["reason"], "approval-missing")
        incomplete = install_driver({"source": "pnputil", "device_id": "dev-audio-1", "device_target": "USB Audio"})
        self.assertEqual(incomplete["reason"], "approval-incomplete")
        self.assertIsNone(incomplete["would_run"])
        mismatch = install_driver(
            _approval(source="pnputil"),
            device_id="dev-audio-1",
            action_id="act-9",
            device_target="NOT-THE-DEVICE",
        )
        self.assertEqual(mismatch["reason"], "device-target-mismatch")
        self.assertNotIn("NOT-THE-DEVICE", json.dumps(mismatch))
        self.assertEqual(
            install_driver(_approval(), device_id="other-device", action_id="act-9", device_target="USB Audio")["reason"],
            "device-id-mismatch",
        )
        self.assertEqual(
            install_driver(_approval(), device_id="dev-audio-1", action_id="other-action", device_target="USB Audio")["reason"],
            "action-id-mismatch",
        )
        self.assertTrue(install_driver(_approval(source="vendor-site"))["refused"])
        self.assertEqual(install_driver(_approval(source="vendor-site"))["reason"], "source-not-allowed")

    def test_approved_plan_does_not_download_or_shell_out(self) -> None:
        for source, action in (
            ("windows-update", "search-driver-for-device"),
            ("pnputil", "stage-driver-for-device"),
        ):
            with self.subTest(source=source):
                plan = install_driver(
                    _approval(source=source, extra_path=r"C:\secret-local-inf\oem.inf"),
                    device_id="dev-audio-1",
                    action_id="act-9",
                    device_target="USB Audio",
                )
                self.assertEqual(plan["status"], "plan")
                self.assertFalse(plan["refused"])
                self.assertFalse(plan["executed"])
                self.assertFalse(plan["downloaded"])
                self.assertFalse(plan["changed_device"])
                self.assertFalse(plan["problem_resolved"])
                self.assertEqual(plan["source"], source)
                self.assertEqual(plan["device_id"], "dev-audio-1")
                self.assertEqual(plan["action_id"], "act-9")
                self.assertEqual(plan["device_target"], "USB Audio")
                self.assertEqual(plan["would_run"]["action"], action)
                self.assertFalse(plan["would_run"]["invoked"])
                self.assertFalse(plan["would_run"]["downloaded"])
                blob = json.dumps(plan).casefold()
                self.assertNotIn("secret-local-inf", blob)
                self.assertNotIn("http", blob)
                self.assertNotIn("add-driver", blob)
                self.assertNotIn("subprocess", blob)
        named_only = install_driver(_approval(source="pnputil"))
        self.assertEqual(named_only["status"], "plan")
        self.assertEqual(named_only["device_id"], "dev-audio-1")
        self.assertEqual(named_only["action_id"], "act-9")
        self.assertEqual(named_only["device_target"], "USB Audio")
        self.assertFalse(named_only["executed"])
        self.assertFalse(named_only["downloaded"])
        self.assertFalse(named_only["would_run"]["invoked"])
        names = set(inspect.signature(install_driver).parameters)
        self.assertTrue({"approval", "device_id", "action_id", "device_target"} <= names)
        self.assertFalse(names & {"command", "path", "url", "credential", "argv"})

    def test_module_has_no_network_or_installer_calls(self) -> None:
        source = Path(inspect.getfile(assess_device_health)).read_text(encoding="utf-8").casefold()
        for banned in (
            "subprocess",
            "urllib",
            "urlopen",
            "requests",
            "socket",
            "invoke-webrequest",
            "invoke-restmethod",
            "os.system",
            "pnputil.exe",
            "pnputil /",
            "add-driver",
            "start-process",
            "winhttp",
        ):
            self.assertNotIn(banned, source)
        self.assertIn("windows-update", source)
        self.assertIn('"pnputil"', source)

    def test_result_note_does_not_call_the_synthetic_fixture_a_live_success(self) -> None:
        note = Path("docs/results/windows-driver-health-2026-10-23.md").read_text(encoding="utf-8")
        folded = note.casefold()
        self.assertIn("synthetic", folded)
        self.assertIn("not a live success", folded)
        self.assertIn("no-go", folded)
        self.assertIn("windows-update", folded)
        self.assertIn("pnputil", folded)
        self.assertIn("arbitrary url", folded)
        self.assertIn("supplied", folded)
        self.assertNotIn("live_windows", folded)
        self.assertNotIn("second_endpoint_worker_ok", folded)


if __name__ == "__main__":
    unittest.main()
