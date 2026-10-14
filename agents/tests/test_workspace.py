"""Agent desk: real runner, no Microsoft calls, no hidden transcript in the view."""
from __future__ import annotations

import json
import unittest

from agents.model import ScriptedModel
from agents.workspace import AgentDesk, tools_for
from integrations.microsoft365 import platform_catalog
from integrations.tenancy import TenantContext


class WorkspaceTests(unittest.TestCase):
    def test_default_tools_are_only_the_calculator(self) -> None:
        catalog, _client = platform_catalog()
        ctx = TenantContext.create("local-console", "console-user", [])
        self.assertEqual([tool.name for tool in tools_for(catalog, ctx)], ["calculator"])

    def test_public_view_omits_hidden_reasoning(self) -> None:
        desk = AgentDesk()
        secret = "SECRET-THOUGHT-do-not-show"
        model = ScriptedModel([json.dumps({
            "action": "final",
            "answer": "The calculator was not needed.",
            "thought": secret,
        })])
        view = desk.start("Say hello.", model)
        blob = json.dumps(view)
        self.assertEqual(view["state"], "final")
        self.assertEqual(view["answer"], "The calculator was not needed.")
        self.assertNotIn(secret, blob)
        self.assertNotIn("system", blob)

    def test_consequential_tool_pauses_before_any_provider_call(self) -> None:
        catalog, client = platform_catalog()
        record = catalog.connection("acme", "microsoft365")
        record.connected = True
        record.granted_scopes = frozenset({"teams:write"})
        ctx = TenantContext.create("acme", "worker@example.com", [])
        desk = AgentDesk(catalog, ctx)
        names = [tool.name for tool in tools_for(catalog, ctx)]
        self.assertIn("m365_send_teams_message", names)
        self.assertNotIn("m365_search_mail", names)
        model = ScriptedModel([json.dumps({
            "action": "tool",
            "tool": "m365_send_teams_message",
            "arguments": {"conversation_id": "chat-1", "body": "Ship the note."},
        })])
        view = desk.start("Send the note.", model)
        self.assertEqual(view["state"], "awaiting_approval")
        self.assertEqual(view["pending_approval"]["tool"], "m365_send_teams_message")
        self.assertEqual(client.network_calls, 0)
        decided = desk.decide(view["task_id"], False, "reviewer@example.com")
        self.assertEqual(client.network_calls, 0)
        self.assertNotEqual(decided["state"], "awaiting_approval")
