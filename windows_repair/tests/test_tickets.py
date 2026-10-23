"""Ticket severity, device link, and the approval gate before repair."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from windows_repair.tickets import FIXTURE_LABEL, TicketError, TicketStore


def _device() -> dict:
    return {
        "device_id": "fixture-not-second",
        "counts_as_second_endpoint": False,
        "fixture_label": FIXTURE_LABEL,
    }


class TicketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TicketStore(Path(self.tmp.name), clock=lambda: 1000.0)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_model_cannot_downgrade_severity(self) -> None:
        created = self.store.create(
            title="Users cannot print",
            detail="The queue is stuck.",
            actor="helpdesk",
            device=_device(),
            evidence_ref="job:fixture-evidence-1",
            requested_severity="low",
        )
        self.assertEqual(created["severity"], "high")
        self.assertEqual(created["severity_floor"], "high")
        self.assertTrue(created["severity_downgrade_blocked"])
        self.assertEqual(created["model_requested_severity"], "low")
        self.assertFalse(created["device"]["counts_as_second_endpoint"])
        self.assertEqual(created["device"]["fixture_label"], FIXTURE_LABEL)
        self.assertIsNone(created["ai_recommendation"])
        self.assertIsNone(created["verified_diagnosis"])

    def test_recommendation_is_not_a_verified_diagnosis(self) -> None:
        created = self.store.create(
            title="Disk looks slow",
            detail="Intermittent pauses.",
            actor="helpdesk",
            device=_device(),
            evidence_ref="collection:my-docs:file:notes.md",
        )
        recommended = self.store.recommend(
            created["id"], "model", "Try clearing space.", requested_severity="low",
        )
        self.assertEqual(recommended["ai_recommendation"], "Try clearing space.")
        self.assertIsNone(recommended["verified_diagnosis"])
        self.assertEqual(recommended["severity"], "medium")
        self.assertTrue(recommended["severity_downgrade_blocked"])
        verified = self.store.verify_diagnosis(created["id"], "operator", "The disk is nearly full.")
        self.assertEqual(verified["verified_diagnosis"], "The disk is nearly full.")
        self.assertEqual(verified["ai_recommendation"], "Try clearing space.")
        self.assertNotEqual(verified["ai_recommendation"], verified["verified_diagnosis"])
        actions = [item["action"] for item in verified["activity"]]
        self.assertIn("ai_recommendation", actions)
        self.assertIn("verified_diagnosis", actions)

    def test_repair_does_not_run_before_approval(self) -> None:
        created = self.store.create(
            title="Printer queue",
            detail="One job is waiting.",
            actor="helpdesk",
            device=_device(),
            evidence_ref="job:fixture-evidence-2",
        )
        calls: list[str] = []

        def executor(ticket: dict) -> dict:
            calls.append(ticket["id"])
            return {"executed": True, "changed_device": False}

        proposed = self.store.request_repair(created["id"], "helpdesk")
        self.assertEqual(proposed["status"], "awaiting_approval")
        blocked = self.store.execute_repair(created["id"], "helpdesk", executor)
        self.assertEqual(blocked["repair_status"], "approval_required")
        self.assertFalse(blocked["executed"])
        self.assertFalse(blocked["changed_device"])
        self.assertEqual(calls, [])
        approved = self.store.approve(created["id"], "reviewer")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["approval"]["approver"], "reviewer")
        finished = self.store.execute_repair(created["id"], "helpdesk", executor)
        self.assertEqual(calls, [created["id"]])
        self.assertTrue(finished["executed"])
        self.assertFalse(finished["changed_device"])
        self.assertEqual(finished["status"], "completed")

    def test_second_endpoint_flag_and_public_url_are_refused(self) -> None:
        with self.assertRaises(TicketError):
            self.store.create(
                title="Office PC",
                detail="Check-in.",
                actor="helpdesk",
                device={"device_id": "real-pc", "counts_as_second_endpoint": True},
                evidence_ref="job:nope",
            )
        with self.assertRaises(TicketError):
            self.store.create(
                title="Office PC",
                detail="Check-in.",
                actor="helpdesk",
                device=_device(),
                evidence_ref="https://files.example/secret.pdf",
            )
        reloaded = TicketStore(Path(self.tmp.name), clock=lambda: 1000.0)
        self.assertEqual(reloaded.list_tickets(), [])

    def test_store_reloads_the_same_ticket(self) -> None:
        created = self.store.create(
            title="Slow login",
            detail="Intermittent.",
            actor="helpdesk",
            device=_device(),
            evidence_ref="job:fixture-evidence-3",
        )
        reloaded = TicketStore(Path(self.tmp.name), clock=lambda: 1001.0)
        again = reloaded.get(created["id"])
        self.assertEqual(again["title"], "Slow login")
        self.assertEqual(again["status"], "open")
        self.assertGreaterEqual(len(again["activity"]), 1)


if __name__ == "__main__":
    unittest.main()
