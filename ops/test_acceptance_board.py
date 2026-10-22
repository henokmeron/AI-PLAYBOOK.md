"""Acceptance board arithmetic. These tests do not contact the Pod."""
from __future__ import annotations

import unittest

from ops.acceptance_board import ACCEPTANCE_GATES, board, workstreams


class AcceptanceBoardTests(unittest.TestCase):
    def test_percentages_follow_completed_criteria_and_stay_no_go(self) -> None:
        payload = board()
        self.assertEqual(payload["decision"], "NO-GO")
        self.assertEqual(payload["production_decision"], "NO-GO")
        self.assertTrue(payload["offline_is_not_production_go"])
        self.assertEqual(payload["microsoft_status"], "NOT CONFIGURED")
        self.assertIn("not a production GO", payload["note"])
        failing = set(payload["failing_acceptance"])
        self.assertIn("deployed commit equals intended Git tip", failing)
        self.assertIn("fresh-environment recovery", failing)
        self.assertIn("second endpoint", failing)
        self.assertIn("Blackwell live acceptance", failing)
        self.assertIn("mail end-to-end", failing)
        rows = workstreams()
        offline = [row for row in rows if row["lane"] == "offline"]
        live = [row for row in rows if row["lane"] == "live"]
        self.assertGreaterEqual(len(offline), 1)
        self.assertGreaterEqual(len(live), 1)
        self.assertEqual(len(rows), len(offline) + len(live))
        for row in rows:
            total = len(row["completed"]) + len(row["remaining"])
            self.assertEqual(row["percent"], (100 * len(row["completed"])) // total)
            self.assertIn(row["lane"], {"offline", "live"})
            self.assertIn(row["blocker"], {"code", "hardware", "authorisation", "user approval"})
            self.assertTrue(row["evidence"])
            self.assertTrue(row["next_action"])
            self.assertTrue(row["bar"].startswith("["))
            if row["lane"] == "live":
                self.assertEqual(row["completed"], [])
                self.assertLess(row["percent"], 100)
        self.assertEqual(payload["offline_percent"], sum(row["percent"] for row in offline) // len(offline))
        self.assertEqual(payload["live_acceptance_percent"], sum(row["percent"] for row in live) // len(live))
        self.assertEqual(payload["overall_percent"], payload["live_acceptance_percent"])
        self.assertLess(payload["live_acceptance_percent"], 100)
        self.assertNotEqual(payload["overall_percent"], payload["offline_percent"])
        self.assertFalse(any(passed for _name, passed in ACCEPTANCE_GATES))
        self.assertNotEqual(payload["decision"], "GO")
        if payload["offline_percent"] == 100:
            self.assertEqual(payload["decision"], "NO-GO")
            self.assertLess(payload["live_acceptance_percent"], 100)
        joined = " ".join(row["evidence"] for row in rows)
        self.assertIn("temp extract", joined)
        self.assertIn("not a fresh machine", joined)
        self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", joined)


if __name__ == "__main__":
    unittest.main()
