"""Operator task types: general knowledge, Windows, Mac fixtures, Microsoft documents."""
from __future__ import annotations

import inspect
import json
import unittest
from dataclasses import asdict
from unittest.mock import patch

from agents.mac_catalogue import LIVE_MAC, mac_tools
from agents.microsoft_documents import microsoft_document_tools
from agents.model import ScriptedModel
from agents.task_kinds import resolve_task_kind
from agents.tools import ToolInputError
from agents.workspace import AgentDesk
from integrations.catalog import Effect
from integrations.errors import InvalidRequest
from integrations.microsoft365 import platform_catalog
from integrations.tenancy import TenantContext
from windows_repair.agent_tools import RepairToolSession, windows_repair_tools


def _final(summary: str, source: str, tools: list[str], answer: str | None = None) -> str:
    return json.dumps({
        "action": "final",
        "answer": answer or summary,
        "output": {"summary": summary, "source": source, "tools_used": tools},
    })


class TaskKindTests(unittest.TestCase):
    def test_prefixes_select_a_kind_and_unknown_types_are_rejected(self) -> None:
        self.assertEqual(resolve_task_kind("general knowledge: what is dns?"), "general_knowledge")
        self.assertEqual(resolve_task_kind("Windows repair: spooler stopped"), "windows_repair")
        self.assertEqual(resolve_task_kind("The MacBook cannot reach the network"), "mac_troubleshooting")
        self.assertEqual(resolve_task_kind("Save this to OneDrive"), "microsoft_documents")
        self.assertEqual(resolve_task_kind("What is 2 + 2?"), "")
        self.assertEqual(resolve_task_kind("Helpdesk ticket: VPN is down"), "it_support")
        with self.assertRaises(ValueError):
            resolve_task_kind("hello", "shell")

    def test_general_knowledge_does_not_pretend_a_tool_ran(self) -> None:
        token = "sk-" + "A" * 24
        body = "SECRETDOCUMENTBODY " + ("x" * 40)
        model = ScriptedModel([
            _final("I used the calculator.", "model", [], "I used the calculator to add the numbers."),
            _final("Four is even.", "model", [], "Four is even."),
        ])
        desk = AgentDesk()
        view = desk.start(
            f"general knowledge: is four even? {token} {body}",
            model,
            task_type="general_knowledge",
        )
        self.assertEqual(view["state"], "final")
        self.assertEqual(view["task_kind"], "general_knowledge")
        self.assertEqual(view["tools_executed"], [])
        self.assertNotIn("calculator", view["answer"])
        blob = json.dumps([asdict(entry) for entry in desk.audit.entries()])
        self.assertNotIn(token, blob)
        self.assertNotIn("SECRETDOCUMENTBODY", blob)
        self.assertIn("did not", model.calls[1][-1]["content"])

    def test_general_knowledge_records_only_a_tool_that_ran(self) -> None:
        model = ScriptedModel([
            json.dumps({"action": "tool", "tool": "calculator", "arguments": {"expression": "2+2"}}),
            _final("The calculator returned 4.", "tool", ["calculator", "mac_diagnose"]),
            _final("The calculator returned 4.", "tool", ["calculator"]),
        ])
        desk = AgentDesk()
        view = desk.start("general knowledge: what is 2 + 2?", model, task_type="general_knowledge")
        self.assertEqual(view["state"], "final")
        self.assertEqual(view["tools_executed"], ["calculator"])
        blob = json.dumps([asdict(entry) for entry in desk.audit.entries()])
        self.assertIn("calculator", blob)
        self.assertIn("not-required", blob)
        self.assertNotIn("mac_diagnose", view["tools_executed"])


class WindowsTaskTests(unittest.TestCase):
    def test_privileged_repair_needs_a_second_approver_and_does_not_run(self) -> None:
        class Boom:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def collect(self, procedure_id: str, timeout: float = 18) -> dict[str, str]:
                self.calls.append(procedure_id)
                raise AssertionError("collector ran")

        desk = AgentDesk()
        boom = Boom()
        desk.repair_tools.provider = boom
        model = ScriptedModel([
            json.dumps({
                "action": "tool",
                "tool": "windows_repair_request_change",
                "arguments": {"procedure_id": "print.spooler.restart"},
            }),
            _final(
                "The approval was recorded. This computer was not changed.",
                "tool",
                ["windows_repair_request_change"],
            ),
        ])
        view = desk.start(
            "Windows repair: restart the spooler",
            model,
            started_by="operator@example.com",
            task_type="windows_repair",
        )
        self.assertEqual(view["state"], "awaiting_approval")
        self.assertEqual(view["pending_approval"]["tool"], "windows_repair_request_change")
        with self.assertRaises(ValueError):
            desk.decide(
                view["task_id"], True, "operator@example.com", view["pending_approval"]["call_id"],
            )
        done = desk.decide(
            view["task_id"], True, "approver@example.com", view["pending_approval"]["call_id"],
        )
        self.assertEqual(done["state"], "final")
        self.assertEqual(done["tools_executed"], ["windows_repair_request_change"])
        self.assertEqual(boom.calls, [])
        self.assertNotIn("changed_device\": true", json.dumps(done).casefold())
        blob = json.dumps([asdict(entry) for entry in desk.audit.entries()])
        self.assertIn("windows_repair_request_change", blob)
        self.assertIn("granted", blob)
        self.assertNotIn("SECRETDOCUMENTBODY", blob)

    def test_firewall_driver_and_credentials_are_not_run(self) -> None:
        class Boom:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def collect(self, procedure_id: str, timeout: float = 18) -> dict[str, str]:
                self.calls.append(procedure_id)
                return {"ok": True, "evidence_source": "live_windows", "detail": "SECRETDOCUMENTBODY"}

        session = RepairToolSession(provider=Boom())
        tools = {tool.name: tool for tool in windows_repair_tools(session)}
        for procedure_id in ("net.firewall.disable", "hw.driver.install"):
            diagnosed = tools["windows_repair_diagnose"].handler({"procedure_id": procedure_id})
            self.assertFalse(diagnosed["changed_device"])
            self.assertNotEqual(diagnosed["status"], "diagnosed")
            requested = tools["windows_repair_request_change"].handler({"procedure_id": procedure_id})
            self.assertEqual(requested["status"], "denied")
            self.assertFalse(requested["changed_device"])
        with self.assertRaises(ToolInputError) as caught:
            tools["windows_repair_diagnose"].handler({"procedure_id": "credential.dump"})
        self.assertIn("not-approved", str(caught.exception))
        self.assertEqual(session.provider.calls, [])
        blob = json.dumps([asdict(entry) for entry in session.audit.entries()])
        self.assertIn("windows_repair_diagnose", blob)
        self.assertIn("not-approved", blob)
        self.assertNotIn("SECRETDOCUMENTBODY", blob)


class MacCatalogueTests(unittest.TestCase):
    def test_fixtures_are_not_executed_and_live_mac_is_not_tested(self) -> None:
        source = inspect.getsource(mac_tools)
        self.assertNotIn("import subprocess", inspect.getsource(__import__("agents.mac_catalogue", fromlist=["mac_tools"])))
        tools = {tool.name: tool for tool in mac_tools()}
        with patch("subprocess.run", side_effect=AssertionError("subprocess")), patch(
            "subprocess.Popen", side_effect=AssertionError("subprocess"),
        ):
            planned = tools["mac_plan"].handler({"symptom": "disk is full on the mac"})
            disk = tools["mac_diagnose"].handler({"check_id": "mac.disk.space", "fixture": "disk_low"})
            network = tools["mac_diagnose"].handler({"check_id": "mac.network.inspect", "fixture": "network_dns"})
            crash = tools["mac_diagnose"].handler({
                "check_id": "mac.crash.reports", "fixture": "crash_windowserver",
            })
            skipped = tools["mac_diagnose"].handler({"check_id": "mac.network.inspect"})
        self.assertEqual(planned["check_ids"], ["mac.disk.space"])
        self.assertFalse(planned["executed"])
        self.assertEqual(planned["live_mac"], "NOT TESTED")
        for result in (disk, network, crash):
            tools["mac_diagnose"].validate_output(result)
            self.assertFalse(result["executed"])
            self.assertFalse(result["changed_device"])
            self.assertEqual(result["evidence_source"], "fixture")
            self.assertEqual(result["live_mac"], LIVE_MAC)
        self.assertEqual(skipped["status"], "not-run")
        self.assertIn("NOT TESTED", skipped["detail"])
        self.assertIn("No remote Mac agent", skipped["detail"])
        self.assertNotIn("import subprocess", source)

    def test_mac_task_uses_a_fixture_and_records_the_tool(self) -> None:
        model = ScriptedModel([
            json.dumps({
                "action": "tool",
                "tool": "mac_diagnose",
                "arguments": {"check_id": "mac.disk.space", "fixture": "disk_low"},
            }),
            _final("Fixture only. Live Mac was not tested.", "tool", ["mac_diagnose"]),
        ])
        desk = AgentDesk()
        with patch("subprocess.run", side_effect=AssertionError("subprocess")):
            view = desk.start(
                "Mac troubleshooting: disk space looks low",
                model,
                task_type="mac_troubleshooting",
            )
        self.assertEqual(view["state"], "final")
        self.assertEqual(view["tools_executed"], ["mac_diagnose"])
        self.assertIn("NOT TESTED", json.dumps(view["record"]))
        blob = json.dumps([asdict(entry) for entry in desk.audit.entries()])
        self.assertIn("mac_diagnose", blob)
        self.assertIn("not-required", blob)


class MicrosoftDocumentTests(unittest.TestCase):
    def test_missing_write_is_not_approved_and_does_not_call_out(self) -> None:
        catalog, client = platform_catalog()
        ctx = TenantContext.create("local-console", "console-user", [])
        tools = {tool.name: tool for tool in microsoft_document_tools(catalog, ctx)}
        create = tools["m365_create_document"]
        self.assertFalse(create.requires_approval)
        result = create.handler({"name": "notes.docx"})
        create.validate_output(result)
        self.assertEqual(result["status"], "not-approved")
        self.assertFalse(result["executed"])
        self.assertIn("not-approved", result["detail"])
        self.assertEqual(client.network_calls, 0)
        with self.assertRaises(ToolInputError):
            create.validate_input({"name": "notes.docx", "body": "SECRETDOCUMENTBODY"})
        source = inspect.getsource(microsoft_document_tools)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)

    def test_catalog_write_drops_file_contents_and_tokens(self) -> None:
        class Operation:
            evidence = "mock-tested"
            effect = Effect.CONSEQUENTIAL
            requires_approval = True

        class Spec:
            def operation(self, name: str) -> Operation:
                if name == "create_document":
                    return Operation()
                raise InvalidRequest("missing")

        class Catalog:
            def __init__(self) -> None:
                self.calls: list[tuple[str, bool]] = []

            def spec(self, connector_id: str) -> Spec:
                return Spec()

            def execute(self, ctx: object, connector: str, operation: str, params: dict[str, str], authorised: bool = False) -> dict[str, str]:
                self.calls.append((operation, authorised))
                return {
                    "status": "stored",
                    "body": "SECRETDOCUMENTBODY",
                    "access_token": "token-should-not-leak",
                }

        catalog = Catalog()
        ctx = TenantContext.create("local-console", "console-user", ["files:write"])
        tool = microsoft_document_tools(catalog, ctx)[0]  # type: ignore[arg-type]
        self.assertTrue(tool.requires_approval)
        refused = tool.handler({"name": "notes.docx"})
        self.assertEqual(refused["status"], "not-approved")
        self.assertEqual(catalog.calls, [])
        from integrations.approvals import payload_hash

        arguments = {"name": "notes.docx"}
        tool.approval_grant["call_id"] = "call-1"  # type: ignore[attr-defined]
        tool.approval_grant["arguments"] = dict(arguments)  # type: ignore[attr-defined]
        self.assertEqual(payload_hash(arguments), payload_hash(tool.approval_grant["arguments"]))  # type: ignore[attr-defined]
        accepted = tool.handler(arguments)
        self.assertEqual(accepted["status"], "catalog")
        self.assertTrue(accepted["executed"])
        self.assertNotIn("SECRETDOCUMENTBODY", json.dumps(accepted))
        self.assertNotIn("token-should-not-leak", json.dumps(accepted))
        self.assertEqual(catalog.calls, [("create_document", True)])

    def test_desk_document_task_audits_the_refusal(self) -> None:
        token = "sk-" + "B" * 24
        model = ScriptedModel([
            json.dumps({
                "action": "tool",
                "tool": "m365_create_document",
                "arguments": {"name": "notes.docx"},
            }),
            _final("The document write is not approved. No file was sent.", "tool", ["m365_create_document"]),
        ])
        desk = AgentDesk()
        view = desk.start(
            f"Microsoft documents: create notes.docx {token} SECRETDOCUMENTBODY",
            model,
            task_type="microsoft_documents",
        )
        self.assertEqual(view["state"], "final")
        self.assertEqual(view["tools_executed"], ["m365_create_document"])
        self.assertIn("not-approved", json.dumps(view["record"]))
        blob = json.dumps([asdict(entry) for entry in desk.audit.entries()])
        self.assertIn("m365_create_document", blob)
        self.assertIn("not-approved", blob)
        self.assertNotIn(token, blob)
        self.assertNotIn("SECRETDOCUMENTBODY", blob)
        self.assertNotIn("notes.docx", blob)

    def test_catalog_file_write_pauses_and_audit_omits_the_contents(self) -> None:
        catalog, client = platform_catalog()
        ctx = TenantContext.create("local-console", "console-user", [])
        desk = AgentDesk(catalog, ctx)
        body = "SECRETDOCUMENTBODY " + ("z" * 40)
        model = ScriptedModel([
            json.dumps({
                "action": "tool",
                "tool": "m365_upload_file",
                "arguments": {"path": "notes.docx", "content": body},
            }),
            _final("The upload was not sent.", "model", []),
        ])
        view = desk.start(
            "Microsoft documents: upload notes.docx",
            model,
            started_by="operator@example.com",
            task_type="microsoft_documents",
        )
        self.assertEqual(view["state"], "awaiting_approval")
        self.assertEqual(view["pending_approval"]["tool"], "m365_upload_file")
        with self.assertRaises(ValueError):
            desk.decide(
                view["task_id"], True, "operator@example.com", view["pending_approval"]["call_id"],
            )
        decided = desk.decide(
            view["task_id"], False, "approver@example.com", view["pending_approval"]["call_id"],
        )
        self.assertNotEqual(decided["state"], "awaiting_approval")
        self.assertEqual(client.network_calls, 0)
        self.assertEqual(decided["tools_executed"], [])
        blob = json.dumps([asdict(entry) for entry in desk.audit.entries()])
        self.assertIn("m365_upload_file", blob)
        self.assertIn("denied", blob)
        self.assertNotIn("SECRETDOCUMENTBODY", blob)
        self.assertNotIn(body, blob)


if __name__ == "__main__":
    unittest.main()
