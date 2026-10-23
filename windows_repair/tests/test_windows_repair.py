"""Windows repair catalogue tests. Fixtures are mocked. No printer, driver, or remote desktop is contacted."""
from __future__ import annotations

import unittest

from windows_repair.engine import RepairDenied, execute, plan, workflow_stage
from windows_repair.jobs import JobService
from windows_repair.knowledge import authorises_tool, retrieve
from windows_repair.remote_support import status_from_env


class ProcedureTests(unittest.TestCase):
    def test_activation_and_agent_tool_do_not_claim_a_fix(self) -> None:
        result = execute("win.activation.inspect", evidence={"activation_status": "notification"})
        self.assertFalse(result["problem_resolved"])
        self.assertFalse(result["changed_device"])
        from windows_repair.agent_tools import windows_repair_tools

        tools = {tool.name: tool for tool in windows_repair_tools()}
        planned = tools["windows_repair_plan"].handler({"symptom": "printer queue stuck"})
        self.assertIn("print.diagnose", planned["procedure_ids"])
        self.assertFalse(planned["problem_resolved"])
        diagnosed = tools["windows_repair_diagnose"].handler({"procedure_id": "net.firewall.disable"})
        self.assertEqual(diagnosed["status"], "denied")
        self.assertFalse(diagnosed["problem_resolved"])
    def test_printer_fixture_does_not_clear_jobs(self) -> None:
        result = execute("print.diagnose", fixture="printer_stuck_usb")
        self.assertTrue(result["executed"])
        self.assertFalse(result["changed_device"])
        self.assertFalse(result["problem_resolved"])
        self.assertTrue(result["mocked"])
        self.assertIn("stuck", " ".join(result["hypotheses"]).lower())

    def test_network_fixture_names_dns(self) -> None:
        result = execute("net.diagnose", fixture="network_dns")
        self.assertFalse(result["problem_resolved"])
        self.assertIn("DNS", " ".join(result["hypotheses"]))

    def test_driver_code_does_not_install(self) -> None:
        diagnosed = execute("hw.devices.inventory", fixture="driver_code_28")
        self.assertIn("28", " ".join(diagnosed["facts"]))
        denied = execute("hw.driver.install")
        self.assertEqual(denied["status"], "approval_required")
        self.assertFalse(denied["executed"])
        still = execute("hw.driver.install", approval_id="approval-1")
        self.assertEqual(still["status"], "approved_not_run_on_this_host")
        self.assertFalse(still["changed_device"])

    def test_firewall_disable_is_denied(self) -> None:
        result = execute("net.firewall.disable", approval_id="approval-1")
        self.assertEqual(result["status"], "denied")
        self.assertFalse(result["executed"])

    def test_unknown_procedure_and_command_injection_rejected(self) -> None:
        with self.assertRaises(RepairDenied):
            execute("shell.format")
        with self.assertRaises(RepairDenied):
            execute("win.storage.space", evidence={"note": "powershell -enc AAAA"})

    def test_plan_selects_printer_and_does_not_claim_fixed(self) -> None:
        planned = plan("The printer queue will not print", fixture="printer_stuck_usb")
        self.assertIn("print.diagnose", planned["procedure_ids"])
        self.assertNotIn("net.firewall.disable", planned["procedure_ids"])
        self.assertFalse(planned["problem_resolved"])
        self.assertTrue(planned["mocked_fixture"])

    def test_fixture_stages_are_not_the_second_endpoint(self) -> None:
        planned = plan("The printer queue will not print", fixture="printer_stuck_usb")
        self.assertEqual(planned["stage"], "read_only")
        self.assertFalse(planned["counts_as_second_endpoint"])
        proposed = plan("The spooler stopped", fixture="printer_spooler_stopped")
        self.assertEqual(proposed["stage"], "proposed")
        self.assertIn("print.spooler.restart", proposed["approval_required"])
        blocked = execute("print.spooler.restart", fixture="printer_spooler_stopped")
        self.assertEqual(blocked["stage"], "proposed")
        self.assertEqual(blocked["status"], "approval_required")
        self.assertFalse(blocked["executed"])
        self.assertFalse(blocked["counts_as_second_endpoint"])
        approved = execute(
            "print.spooler.restart",
            fixture="printer_spooler_stopped",
            approval_id="apr-fixture",
        )
        self.assertEqual(approved["stage"], "approved")
        self.assertFalse(approved["changed_device"])
        self.assertFalse(approved["counts_as_second_endpoint"])
        self.assertEqual(workflow_stage({"executed": True, "changed_device": True}), "completed")


class JobTests(unittest.TestCase):
    def test_enrol_revoke_and_tenant_isolation(self) -> None:
        jobs = JobService(clock=lambda: 1_000.0)
        secret = "device-secret-value"
        device = jobs.enrol("acme", secret)
        other = jobs.enrol("otherco", "other-secret-value")
        case = jobs.open_case("acme", device, "printer stuck")
        with self.assertRaises(RepairDenied):
            jobs.get_case("otherco", case.case_id)
        jobs.revoke("acme", device)
        with self.assertRaises(RepairDenied):
            jobs.issue(tenant_id="acme", device_id=device, procedure_id="print.diagnose", operator="ada")
        self.assertNotEqual(device, other)

    def test_replay_and_bad_signature_rejected(self) -> None:
        clock = {"now": 5_000.0}
        jobs = JobService(clock=lambda: clock["now"])
        secret = "device-secret-value"
        device = jobs.enrol("acme", secret)
        envelope = jobs.issue(
            tenant_id="acme", device_id=device, procedure_id="print.diagnose",
            operator="ada", fixture="printer_stuck_usb",
        )
        first = jobs.accept(secret, envelope)
        self.assertFalse(first["problem_resolved"])
        with self.assertRaises(RepairDenied):
            jobs.accept(secret, envelope)
        forged = dict(envelope)
        forged["nonce"] = "different-nonce-value1"
        forged["signature"] = "0" * 64
        with self.assertRaises(RepairDenied):
            jobs.accept(secret, forged)

    def test_expired_job_and_wrong_secret(self) -> None:
        clock = {"now": 9_000.0}
        jobs = JobService(clock=lambda: clock["now"], ttl=10)
        secret = "device-secret-value"
        device = jobs.enrol("acme", secret)
        envelope = jobs.issue(tenant_id="acme", device_id=device, procedure_id="net.diagnose", operator="ada", fixture="network_dns")
        clock["now"] += 30
        with self.assertRaises(RepairDenied):
            jobs.accept(secret, envelope)
        clock["now"] -= 30
        fresh = jobs.issue(tenant_id="acme", device_id=device, procedure_id="net.diagnose", operator="ada", fixture="network_dns")
        with self.assertRaises(RepairDenied):
            jobs.accept("wrong-secret", fresh)

    def test_elevated_job_needs_approval_and_does_not_change_host(self) -> None:
        jobs = JobService(clock=lambda: 100.0)
        secret = "device-secret-value"
        device = jobs.enrol("acme", secret)
        missing = jobs.issue(tenant_id="acme", device_id=device, procedure_id="print.jobs.clear", operator="ada")
        denied = jobs.accept(secret, missing)
        self.assertEqual(denied["status"], "approval_required")
        approved = jobs.issue(
            tenant_id="acme", device_id=device, procedure_id="print.jobs.clear",
            operator="ada", approval_id="apr-1",
        )
        result = jobs.accept(secret, approved)
        self.assertEqual(result["status"], "approved_not_run_on_this_host")
        self.assertFalse(result["changed_device"])
        self.assertTrue(any(row["operator"] == "ada" for row in jobs.audit))


class KnowledgeAndRemoteTests(unittest.TestCase):
    def test_retrieval_cites_source_and_ignores_injection(self) -> None:
        hits = retrieve("stuck print queue")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["doc_id"], "ms-print-queue")
        self.assertIn("source", hits[0])
        hostile = retrieve("ignore policy firewall")
        self.assertTrue(any(hit["doc_id"] == "hostile-note" for hit in hostile))
        self.assertFalse(authorises_tool(hostile[0]["excerpt"]))
        self.assertEqual(retrieve("zzzz-not-a-topic"), [])

    def test_remote_support_is_not_configured_and_not_verified(self) -> None:
        report = status_from_env({"MESHCENTRAL_URL": ""})
        self.assertEqual(report["state"], "NOT CONFIGURED")
        self.assertFalse(report["remote_desktop_verified"])
        bad = status_from_env({"MESHCENTRAL_URL": "http://example.test"})
        self.assertEqual(bad["state"], "DEGRADED")
        unknown = status_from_env({"MESHCENTRAL_URL": "https://mesh.example.test"})
        self.assertEqual(unknown["state"], "UNKNOWN")
        self.assertFalse(unknown["remote_desktop_verified"])


if __name__ == "__main__":
    unittest.main()
