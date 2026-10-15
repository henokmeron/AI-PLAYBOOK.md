"""IT helpdesk tools and end-to-end scripted investigation (mocked model)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agents.builtin.helpdesk import helpdesk_tools
from agents.it_support import approval_presentation, looks_like_it_support
from agents.model import ScriptedModel
from agents.runtime import AgentRunner
from agents.tools import ToolRegistry
from agents.workspace import AgentDesk, public_view


class HelpdeskToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.logs = self.root / "logs"
        self.cache = self.root / "cache"
        self.flag = self.root / "maintenance.flag"
        self.logs.mkdir()
        (self.logs / "console.log").write_text(
            "ready\napi_key=sk-abcdefghijklmnopqrstuvwxyz\n",
            encoding="utf-8",
        )
        self.cache.mkdir()
        (self.cache / "stale.tmp").write_text("old", encoding="utf-8")
        self.tools = {
            tool.name: tool
            for tool in helpdesk_tools(
                log_root=self.logs,
                cache_dir=self.cache,
                flag_path=self.flag,
                services={"gateway": "http://127.0.0.1:8010/health", "console": "http://127.0.0.1:8080/"},
                probe=lambda url, _timeout: {
                    "ok": "8010" in url,
                    "http_status": 200 if "8010" in url else 0,
                    "detail": "ok" if "8010" in url else "down",
                    "latency_ms": 1,
                },
            )
        }

    def test_classify_and_health(self) -> None:
        classified = self.tools["classify_it_issue"].handler({
            "category": "application",
            "severity": "high",
            "desired_outcome": "Restore chat for users",
            "missing_information": [],
        })
        self.assertEqual(classified["category"], "application")
        health = self.tools["check_platform_health"].handler({"services": ["gateway", "console"]})
        self.assertEqual(health["status"], "degraded")
        self.assertTrue(health["services"][0]["ok"])
        self.assertFalse(health["services"][1]["ok"])

    def test_log_redacts_secrets(self) -> None:
        result = self.tools["read_approved_log"].handler({"name": "console.log", "max_lines": 10})
        self.assertTrue(result["found"])
        blob = "\n".join(result["lines"])
        self.assertIn("[REDACTED]", blob)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", blob)

    def test_diagnostic_and_remediation(self) -> None:
        diag = self.tools["run_safe_diagnostic"].handler({"check": "temp_cache"})
        self.assertTrue(diag["ok"])
        self.assertIn("stale.tmp", diag["evidence"]["files"])
        rem = self.tools["apply_safe_remediation"]
        self.assertTrue(rem.requires_approval)
        cleared = rem.handler({
            "action": "clear_temp_cache",
            "what_changes": "Delete helpdesk temp cache files",
            "why": "Cache looks full during investigation",
            "system": "local helpdesk cache",
            "risks": "Only clears the helpdesk temp folder",
            "verification_plan": "Re-run temp_cache diagnostic",
        })
        self.assertTrue(cleared["applied"])
        self.assertTrue(cleared["needs_verification"])
        after = self.tools["run_safe_diagnostic"].handler({"check": "temp_cache"})
        self.assertEqual(after["evidence"]["files"], [])

    def test_compose_incident_report(self) -> None:
        out = self.tools["compose_incident_report"].handler({
            "summary": "Gateway was down; console recovered after cache clear",
            "severity": "medium",
            "category": "application",
            "desired_outcome": "Users can chat again",
            "evidence": ["Gateway health returned HTTP 0"],
            "actions_taken": ["Cleared temp cache after approval"],
            "verification": ["Gateway health rechecked"],
            "next_steps": ["Monitor for 24 hours"],
            "outcome": "mitigated",
        })
        self.assertTrue(out["ready_for_final"])
        self.assertEqual(out["report"]["outcome"], "mitigated")


class HelpdeskFlowTests(unittest.TestCase):
    def test_scripted_investigation_with_approval(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        cache = root / "cache"
        cache.mkdir()
        (cache / "noise.bin").write_text("x", encoding="utf-8")
        flag = root / "maint.flag"
        tools = helpdesk_tools(
            log_root=root / "logs",
            cache_dir=cache,
            flag_path=flag,
            services={"gateway": "http://127.0.0.1:8010/health"},
            probe=lambda _url, _t: {"ok": True, "http_status": 200, "detail": "ok", "latency_ms": 2},
        )
        model = ScriptedModel([
            json.dumps({
                "action": "tool",
                "tool": "classify_it_issue",
                "arguments": {
                    "category": "application",
                    "severity": "medium",
                    "desired_outcome": "Clear the noisy cache safely",
                },
            }),
            json.dumps({
                "action": "tool",
                "tool": "run_safe_diagnostic",
                "arguments": {"check": "temp_cache"},
            }),
            json.dumps({
                "action": "tool",
                "tool": "apply_safe_remediation",
                "arguments": {
                    "action": "clear_temp_cache",
                    "what_changes": "Delete files in the helpdesk temp cache",
                    "why": "Diagnostic showed leftover cache files",
                    "system": "local helpdesk cache",
                    "risks": "Low — only the helpdesk cache folder",
                    "verification_plan": "Re-run the temp_cache diagnostic",
                },
            }),
            json.dumps({
                "action": "tool",
                "tool": "run_safe_diagnostic",
                "arguments": {"check": "temp_cache"},
            }),
            json.dumps({
                "action": "tool",
                "tool": "compose_incident_report",
                "arguments": {
                    "summary": "Helpdesk cache cleared after approval",
                    "severity": "low",
                    "category": "application",
                    "desired_outcome": "Clean cache",
                    "evidence": ["temp_cache listed noise.bin"],
                    "actions_taken": ["Approved clear_temp_cache"],
                    "verification": ["temp_cache empty after remediation"],
                    "next_steps": ["None"],
                    "outcome": "resolved",
                },
            }),
            json.dumps({
                "action": "final",
                "answer": "The cache was cleared and verified empty.",
                "output": {
                    "summary": "Helpdesk cache cleared after approval",
                    "severity": "low",
                    "category": "application",
                    "desired_outcome": "Clean cache",
                    "evidence": ["temp_cache listed noise.bin"],
                    "actions_taken": ["Approved clear_temp_cache"],
                    "verification": ["temp_cache empty after remediation"],
                    "next_steps": ["None"],
                    "outcome": "resolved",
                },
            }),
        ])
        desk = AgentDesk()
        # Replace tools by building a desk-like runner path through AgentDesk with custom registry.
        # AgentDesk always builds its own registry; exercise runner + public_view directly for tools.
        runner = AgentRunner(model, ToolRegistry(tools))
        task = runner.new_task(
            "IT support: clear the helpdesk temp cache after checking it",
        )
        self.assertTrue(looks_like_it_support(task.goal))
        runner.run(task)
        self.assertEqual(task.state.value, "awaiting_approval")
        pending = task.pending_approval
        assert pending is not None
        presentation = approval_presentation(pending.tool, pending.arguments, pending.reason)
        self.assertIn("helpdesk", presentation["system"].lower())
        view = public_view(task, runner.trace)
        self.assertEqual(view["pending_approval"]["what_changes"][:6], "Delete")
        runner.resolve_approval(
            task, approved=True, approver="console-user", call_id=pending.call_id,
        )
        self.assertEqual(task.execution.value, "completed")
        self.assertEqual(task.record.outcome, "resolved")
        self.assertEqual(task.final_output["outcome"], "resolved")
        final_view = public_view(task, runner.trace)
        self.assertIsNotNone(final_view["incident_report"])
        self.assertEqual(final_view["incident_report"]["outcome"], "resolved")
        self.assertFalse((cache / "noise.bin").exists())

    def test_desk_it_goal_gets_incident_schema(self) -> None:
        desk = AgentDesk()
        model = ScriptedModel([json.dumps({
            "action": "final",
            "answer": "Blocked until more detail arrives.",
            "output": {
                "summary": "Not enough information",
                "severity": "unknown",
                "evidence": ["User did not name the device"],
                "actions_taken": ["Asked for missing information was not needed"],
                "verification": ["Cannot verify yet"],
                "next_steps": ["Ask which computer is affected"],
                "outcome": "blocked",
            },
        })])
        view = desk.start("Helpdesk ticket: VPN will not connect", model)
        self.assertEqual(view["execution"], "completed")
        self.assertEqual(view["incident_report"]["outcome"], "blocked")
        self.assertIn("helpdesk", json.dumps(desk.connectors()).lower())


if __name__ == "__main__":
    unittest.main()
