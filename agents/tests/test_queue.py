"""Serial async task queue on AgentDesk."""
from __future__ import annotations

import json
import tempfile
import time
import unittest

from agents.model import ScriptedModel
from agents.workspace import AgentDesk


class QueueTests(unittest.TestCase):
    def test_second_async_task_is_queued_then_runs(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        desk = AgentDesk(history_dir=tmp.name)
        slow = ScriptedModel([
            json.dumps({"action": "tool", "tool": "calculator", "arguments": {"expression": "1+1"}}),
            json.dumps({"action": "final", "answer": "2"}),
        ], delay_seconds=0.12)
        fast = ScriptedModel([
            json.dumps({"action": "final", "answer": "queued-then-done"}),
        ], delay_seconds=0.02)
        first = desk.start("Slow add", slow, wait=False, wall_seconds=30)
        second = desk.start("Quick finish", fast, wait=False, wall_seconds=30)
        self.assertTrue(first["running"] or first["execution"] in {"received", "investigating", "executing", "verifying", "completed"})
        self.assertEqual(second["execution"], "queued")
        self.assertFalse(second["running"])
        self.assertTrue(second["cancellable"])

        deadline = time.time() + 8
        final_second = second
        while time.time() < deadline:
            final_second = desk.get(second["task_id"])
            if not final_second.get("running") and final_second.get("execution") == "completed":
                break
            time.sleep(0.05)
        self.assertEqual(final_second["execution"], "completed")
        self.assertEqual(final_second["answer"], "queued-then-done")

        final_first = desk.get(first["task_id"])
        self.assertEqual(final_first["execution"], "completed")

    def test_cancel_queued_task_before_it_runs(self) -> None:
        desk = AgentDesk()
        blocker = ScriptedModel([
            json.dumps({"action": "tool", "tool": "calculator", "arguments": {"expression": "3+3"}}),
            json.dumps({"action": "final", "answer": "6"}),
        ], delay_seconds=0.15)
        waiting = ScriptedModel([
            json.dumps({"action": "final", "answer": "should not run"}),
        ])
        first = desk.start("Blocker", blocker, wait=False, wall_seconds=30)
        second = desk.start("Waiting", waiting, wait=False, wall_seconds=30)
        self.assertEqual(second["execution"], "queued")
        cancelled = desk.cancel(second["task_id"])
        self.assertEqual(cancelled["execution"], "cancelled")
        deadline = time.time() + 5
        while time.time() < deadline:
            done = desk.get(first["task_id"])
            if not done.get("running") and done.get("execution") == "completed":
                break
            time.sleep(0.05)
        still = desk.get(second["task_id"])
        self.assertEqual(still["execution"], "cancelled")
        self.assertNotEqual(still.get("answer"), "should not run")


if __name__ == "__main__":
    unittest.main()
