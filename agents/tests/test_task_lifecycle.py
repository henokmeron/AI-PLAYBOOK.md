"""Task submission, cancellation, and failed-tool outcome.

Scripted model only. No network and no live Qwen.
"""
from __future__ import annotations

import json
import threading
import time
import unittest

from agents.model import ScriptedModel
from agents.runtime import AgentRunner
from agents.state import Budget, ExecutionStatus, TaskState
from agents.tests.test_runtime import final, runner_for, tool_call
from agents.tools import Tool, ToolTransientError
from agents.workspace import AgentDesk


def _lookup(failures: int) -> tuple[Tool, dict]:
    state = {"calls": 0}

    def handler(arguments: dict) -> dict:
        state["calls"] += 1
        if state["calls"] <= failures:
            raise ToolTransientError("temporary backend failure")
        return {"value": str(arguments["key"]).upper()}

    tool = Tool(
        name="lookup",
        description="test lookup",
        input_schema={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        handler=handler,
        idempotent=True,
        max_retries=2,
    )
    return tool, state


class DuplicateSubmissionTests(unittest.TestCase):
    def test_same_task_id_does_not_run_the_tool_twice(self) -> None:
        desk = AgentDesk()
        model = ScriptedModel([
            json.dumps({
                "action": "tool",
                "tool": "calculator",
                "arguments": {"expression": "1+1"},
            }),
            json.dumps({"action": "final", "answer": "2"}),
        ])
        first = desk.start("Add one and one.", model, task_id="task-dup-1")
        second = desk.start("Add one and one again.", model, task_id="task-dup-1")
        self.assertEqual(second["task_id"], "task-dup-1")
        self.assertEqual(second["task_id"], first["task_id"])
        self.assertEqual(second["answer"], "2")
        tool_results = [item for item in second["activity"] if item["kind"] == "tool_result"]
        self.assertEqual(len(tool_results), 1)
        self.assertEqual(len(model.calls), 2)

    def test_concurrent_approval_runs_the_tool_once(self) -> None:
        calls: list[int] = []

        def handler(arguments: dict) -> dict:
            calls.append(1)
            time.sleep(0.25)
            return {"sent": True}

        tool = Tool(
            name="send_message",
            description="consequential test action",
            input_schema={
                "type": "object",
                "properties": {"to": {"type": "string"}, "body": {"type": "string"}},
                "required": ["to", "body"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {"sent": {"type": "boolean"}},
                "required": ["sent"],
            },
            handler=handler,
            idempotent=False,
            requires_approval=True,
        )
        runner, _model = runner_for(
            [tool_call("send_message", to="ops@example.com", body="hello"), final("sent")],
            tools=[tool],
        )
        task = runner.run(runner.new_task("notify ops"))
        self.assertEqual(task.state, TaskState.AWAITING_APPROVAL)
        call_id = task.pending_approval.call_id
        errors: list[BaseException] = []
        gate = threading.Barrier(2)

        def approve() -> None:
            gate.wait(2)
            try:
                runner.resolve_approval(
                    task, approved=True, approver="reviewer@example.com", call_id=call_id,
                )
            except BaseException as exc:  # noqa: BLE001 — the duplicate must not execute
                errors.append(exc)

        threads = [threading.Thread(target=approve) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
        self.assertEqual(calls, [1])
        self.assertTrue(any(isinstance(item, RuntimeError) for item in errors))


class CancellationTests(unittest.TestCase):
    def test_cancel_reaches_cancelled_terminal_state(self) -> None:
        started = threading.Event()

        def block(messages: list) -> str:
            started.set()
            time.sleep(0.6)
            return json.dumps({"action": "final", "answer": "should not complete"})

        desk = AgentDesk()
        model = ScriptedModel([block])
        view = desk.start("Work that can be cancelled.", model, wait=False, wall_seconds=30)
        self.assertTrue(started.wait(2))
        cancelled = desk.cancel(view["task_id"])
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertEqual(cancelled["execution"], "cancelled")
        self.assertEqual(cancelled["record"]["outcome"], "cancelled")
        deadline = time.time() + 3
        final_view = cancelled
        while time.time() < deadline:
            final_view = desk.get(view["task_id"])
            if not final_view.get("running"):
                break
            time.sleep(0.02)
        self.assertFalse(final_view["running"])
        self.assertEqual(final_view["state"], "cancelled")
        self.assertEqual(final_view["execution"], "cancelled")
        self.assertEqual(final_view["record"]["outcome"], "cancelled")
        self.assertNotEqual(final_view.get("answer"), "should not complete")

    def test_cancel_before_terminal_state_overrides_completed_execution(self) -> None:
        runner, _model = runner_for([final("done")])
        task = runner.new_task("x")
        task.set_execution(ExecutionStatus.INVESTIGATING)
        task.set_execution(ExecutionStatus.COMPLETED)
        runner.cancel(task)
        self.assertEqual(task.state, TaskState.CANCELLED)
        self.assertEqual(task.execution, ExecutionStatus.CANCELLED)
        self.assertEqual(task.record.outcome, "cancelled")


class FailedToolRetryTests(unittest.TestCase):
    def test_retry_after_failed_tool_does_not_claim_success(self) -> None:
        tool, state = _lookup(failures=5)
        runner, _model = runner_for([
            tool_call("lookup", key="a"),
            final("The lookup succeeded.", {"outcome": "resolved"}),
        ], tools=[tool])
        task = runner.run(runner.new_task("lookup a", budget=Budget(max_consecutive_errors=5)))
        self.assertGreaterEqual(state["calls"], 2)
        self.assertFalse(any(item.get("ok") for item in task.record.results))
        self.assertNotEqual(task.execution, ExecutionStatus.COMPLETED)
        self.assertNotEqual(task.record.outcome, "completed")
        self.assertNotEqual(task.record.outcome, "resolved")
        self.assertNotEqual(task.state, TaskState.FINAL)
        blob = json.dumps(task.record.to_dict())
        self.assertNotIn('"outcome": "resolved"', blob)


if __name__ == "__main__":
    unittest.main()
