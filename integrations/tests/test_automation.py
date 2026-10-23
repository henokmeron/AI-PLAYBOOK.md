"""Durable automation status, idempotency, and the Power Automate boundary."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from integrations.automation import LIVE_POWER_AUTOMATE, AutomationStore


class AutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AutomationStore(Path(self.tmp.name), env={})

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_same_key_does_not_run_twice(self) -> None:
        calls: list[int] = []

        def runner(task: dict) -> dict:
            calls.append(task["attempt"])
            return {"ok": True}

        first = self.store.submit(
            action="documents.reindex",
            idempotency_key="reindex-my-docs-1",
            actor="operator",
            idempotent=True,
            payload={"collection": "my-docs"},
            agent_task_id="agent-task-1",
        )
        self.assertEqual(first["status"], "queued")
        self.assertFalse(first["duplicate"])
        again = self.store.submit(
            action="documents.reindex",
            idempotency_key="reindex-my-docs-1",
            actor="operator",
            idempotent=True,
        )
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["id"], first["id"])
        ran = self.store.run(first["id"], runner)
        self.assertTrue(ran["ran"])
        replay = self.store.run(first["id"], runner)
        self.assertFalse(replay["ran"])
        self.assertEqual(calls, [1])
        loaded = AutomationStore(Path(self.tmp.name), env={})
        self.assertEqual(loaded.get(first["id"])["status"], "completed")

    def test_sensitive_action_waits_for_a_person(self) -> None:
        calls: list[str] = []

        def runner(task: dict) -> dict:
            calls.append(task["action"])
            return {"ok": True}

        created = self.store.submit(
            action="repair.execute",
            idempotency_key="repair-1",
            actor="helpdesk",
            idempotent=True,
            agent_task_id="awaiting-approval-task",
        )
        self.assertEqual(created["status"], "awaiting_approval")
        blocked = self.store.run(created["id"], runner)
        self.assertFalse(blocked["ran"])
        self.assertEqual(blocked["repair_status"], "approval_required")
        self.assertEqual(calls, [])
        approved = self.store.approve(created["id"], "reviewer")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["approval"]["approver"], "reviewer")
        finished = self.store.run(created["id"], runner)
        self.assertTrue(finished["ran"])
        self.assertEqual(calls, ["repair.execute"])

    def test_retry_stops_for_a_non_idempotent_failure(self) -> None:
        def runner(task: dict) -> dict:
            raise RuntimeError("transient")

        created = self.store.submit(
            action="documents.note",
            idempotency_key="note-1",
            actor="operator",
            idempotent=False,
        )
        failed = self.store.run(created["id"], runner)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["attempts"], 1)
        again = self.store.run(created["id"], runner)
        self.assertFalse(again["ran"])
        self.assertEqual(again["attempts"], 1)

    def test_idempotent_failure_can_be_retried(self) -> None:
        state = {"n": 0}

        def runner(task: dict) -> dict:
            state["n"] += 1
            if state["n"] < 2:
                raise RuntimeError("transient")
            return {"ok": True}

        created = self.store.submit(
            action="documents.note",
            idempotency_key="note-retry",
            actor="operator",
            idempotent=True,
        )
        first = self.store.run(created["id"], runner)
        self.assertEqual(first["status"], "retrying")
        second = self.store.run(created["id"], runner)
        self.assertEqual(second["status"], "completed")
        self.assertEqual(state["n"], 2)

    def test_power_automate_is_not_tested_without_a_webhook(self) -> None:
        calls: list[str] = []

        def runner(task: dict) -> dict:
            calls.append("sent")
            return {"ok": True}

        created = self.store.submit(
            action="power_automate.run",
            idempotency_key="flow-1",
            actor="operator",
            idempotent=True,
            payload={"flow": "notify-helpdesk"},
        )
        self.assertEqual(created["live_power_automate"], LIVE_POWER_AUTOMATE)
        self.store.approve(created["id"], "reviewer")
        result = self.store.run(created["id"], runner)
        self.assertEqual(result["status"], "not_tested")
        self.assertEqual(result["live_power_automate"], "NOT TESTED")
        self.assertFalse(result["ran"])
        self.assertEqual(calls, [])

    def test_payload_rejects_a_secret(self) -> None:
        with self.assertRaises(Exception):
            self.store.submit(
                action="documents.note",
                idempotency_key="secret-1",
                actor="operator",
                idempotent=True,
                payload={"token": "must-not-store"},
            )


if __name__ == "__main__":
    unittest.main()
