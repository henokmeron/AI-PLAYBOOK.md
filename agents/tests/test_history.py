"""Task history store and async AgentDesk progress."""
from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from agents.history import TaskHistoryStore
from agents.model import ScriptedModel
from agents.workspace import AgentDesk


class HistoryStoreTests(unittest.TestCase):
    def test_save_list_get_and_prune(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = TaskHistoryStore(tmp.name, max_tasks=2)
        store.save({"task_id": "a1", "execution": "completed", "goal": "one"})
        time.sleep(0.02)
        store.save({"task_id": "b2", "execution": "failed", "goal": "two"})
        time.sleep(0.02)
        store.save({"task_id": "c3", "execution": "completed", "goal": "three"})
        rows = store.list(limit=10)
        self.assertEqual(len(rows), 2)
        ids = {row["task_id"] for row in rows}
        self.assertIn("c3", ids)
        self.assertNotIn("a1", ids)
        got = store.get("b2")
        self.assertIsNotNone(got)
        self.assertEqual(got["goal"], "two")
        self.assertIn("created_at", got)
        self.assertIn("updated_at", got)

    def test_rejects_unsafe_task_ids(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = TaskHistoryStore(tmp.name)
        with self.assertRaises(ValueError):
            store.save({"task_id": "../escape", "goal": "no"})


class AsyncDeskTests(unittest.TestCase):
    def test_async_run_persists_progress_and_history(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        desk = AgentDesk(history_dir=tmp.name)
        model = ScriptedModel([
            json.dumps({"action": "tool", "tool": "calculator", "arguments": {"expression": "2+2"}}),
            json.dumps({"action": "final", "answer": "4"}),
        ], delay_seconds=0.05)
        view = desk.start("Add two and two.", model, wait=False)
        self.assertTrue(view["running"] or view["execution"] in {"received", "investigating", "executing", "verifying", "completed"})
        deadline = time.time() + 5
        final = None
        while time.time() < deadline:
            final = desk.get(view["task_id"])
            if not final.get("running") and final.get("execution") == "completed":
                break
            time.sleep(0.05)
        self.assertIsNotNone(final)
        self.assertEqual(final["execution"], "completed")
        self.assertEqual(final["answer"], "4")
        self.assertFalse(final["running"])
        history = desk.history_list(limit=5)
        self.assertTrue(any(row["task_id"] == view["task_id"] for row in history))
        on_disk = Path(tmp.name) / f"{view['task_id']}.json"
        self.assertTrue(on_disk.exists())

    def test_cancel_while_running_stops_cooperatively(self) -> None:
        desk = AgentDesk()
        # Many slow model turns so cancel can land mid-run.
        replies = [
            json.dumps({"action": "tool", "tool": "calculator", "arguments": {"expression": f"{i}+1"}})
            for i in range(8)
        ] + [json.dumps({"action": "final", "answer": "done"})]
        model = ScriptedModel(replies, delay_seconds=0.08)
        view = desk.start("Keep calculating.", model, wait=False, wall_seconds=30)
        time.sleep(0.05)
        cancelled = desk.cancel(view["task_id"])
        deadline = time.time() + 5
        final = cancelled
        while time.time() < deadline:
            final = desk.get(view["task_id"])
            if not final.get("running") and final.get("execution") in {"cancelled", "completed", "failed"}:
                break
            time.sleep(0.05)
        self.assertEqual(final["execution"], "cancelled")
        self.assertEqual(final["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()
