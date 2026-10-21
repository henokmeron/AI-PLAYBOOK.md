"""IT support playbook and incident schema wiring."""
from __future__ import annotations

import json
import unittest

from agents.it_support import INCIDENT_OUTPUT_SCHEMA, looks_like_it_support, playbook_for
from agents.model import ScriptedModel
from agents.runtime import AgentRunner
from agents.schema import validate
from agents.tools import ToolRegistry
from agents.builtin.calculator import calculator_tool


class ItSupportTests(unittest.TestCase):
    def test_detects_it_goals(self) -> None:
        self.assertTrue(looks_like_it_support("VPN will not connect for a laptop"))
        self.assertTrue(looks_like_it_support("Helpdesk ticket: disk full"))
        self.assertFalse(looks_like_it_support("What is 2 + 2?"))
        self.assertIsNotNone(playbook_for("Investigate the printer outage"))
        self.assertIn("windows_repair_plan", playbook_for("Investigate the printer outage") or "")
        self.assertIsNone(playbook_for("Calculate 9 * 9"))

    def test_windows_plan_selects_a_procedure_and_rejects_a_shell(self) -> None:
        from windows_repair.agent_tools import windows_repair_tools

        tools = {tool.name: tool for tool in windows_repair_tools()}
        planned = tools["windows_repair_plan"].handler({"symptom": "printer queue is stuck"})
        self.assertIn("print.diagnose", planned["procedure_ids"])
        self.assertFalse(planned["problem_resolved"])
        with self.assertRaises(Exception):
            tools["windows_repair_diagnose"].handler({"procedure_id": "powershell -enc AA=="})

    def test_incident_schema_validates(self) -> None:
        validate(
            {
                "summary": "VPN fails after sleep",
                "severity": "medium",
                "evidence": ["User report"],
                "actions_taken": ["Searched documents"],
                "verification": ["No device enrolled"],
                "next_steps": ["Ask operator for device enrolment"],
                "outcome": "blocked",
            },
            INCIDENT_OUTPUT_SCHEMA,
        )

    def test_runner_attaches_incident_schema_for_it_goal(self) -> None:
        model = ScriptedModel([
            json.dumps({
                "action": "final",
                "answer": "Blocked until a device is enrolled.",
                "output": {
                    "summary": "No endpoint report available",
                    "severity": "unknown",
                    "evidence": ["No enrolled device"],
                    "actions_taken": ["Checked available tools"],
                    "verification": ["Cannot verify without diagnostics"],
                    "next_steps": ["Enrol the computer with the read-only worker"],
                    "outcome": "blocked",
                },
            }),
        ])
        runner = AgentRunner(model, ToolRegistry([calculator_tool()]))
        task = runner.new_task("IT support: diagnose slow laptop")
        self.assertEqual(task.output_schema, INCIDENT_OUTPUT_SCHEMA)
        self.assertIn("IT helpdesk mode", task.messages[0]["content"])
        runner.run(task)
        self.assertEqual(task.execution.value, "completed")
        self.assertEqual(task.final_output["outcome"], "blocked")


if __name__ == "__main__":
    unittest.main()
