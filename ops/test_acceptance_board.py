"""Acceptance board arithmetic. These tests do not contact the Pod."""
from __future__ import annotations

import unittest

from ops.acceptance_board import ACCEPTANCE_GATES, board, workstreams


class AcceptanceBoardTests(unittest.TestCase):
    def test_percentages_follow_completed_criteria_and_stay_no_go(self) -> None:
        payload = board()
        self.assertEqual(payload["decision"], "NO-GO")
        self.assertEqual(payload["microsoft_status"], "NOT CONFIGURED")
        failing = set(payload["failing_acceptance"])
        self.assertIn("deployed commit equals intended Git tip", failing)
        self.assertIn("fresh-environment recovery", failing)
        self.assertIn("second endpoint", failing)
        self.assertIn("Blackwell live acceptance", failing)
        self.assertIn("mail end-to-end", failing)
        rows = workstreams()
        self.assertEqual(len(rows), 10)
        for row in rows:
            total = len(row["completed"]) + len(row["remaining"])
            self.assertEqual(row["percent"], (100 * len(row["completed"])) // total)
            self.assertIn(row["blocker"], {"code", "hardware", "authorisation", "user approval"})
            self.assertTrue(row["evidence"])
            self.assertTrue(row["next_action"])
            self.assertTrue(row["bar"].startswith("["))
        self.assertEqual(
            payload["overall_percent"],
            sum(row["percent"] for row in rows) // len(rows),
        )
        live = next(row for row in rows if row["name"] == "Live acceptance")
        self.assertIn("Pod health URLs returned HTTP 200", live["completed"])
        self.assertFalse(any(passed for _name, passed in ACCEPTANCE_GATES))
        self.assertNotEqual(payload["decision"], "GO")


if __name__ == "__main__":
    unittest.main()
