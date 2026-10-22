"""The integration matrix may not promote a button or a runbook into a pass."""
from __future__ import annotations

import unittest
from pathlib import Path

MATRIX = Path(__file__).resolve().parents[1] / "docs" / "integrations" / "INTEGRATION_MATRIX.md"


class IntegrationMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = MATRIX.read_text(encoding="utf-8")

    def test_open_gates_are_not_marked_complete(self) -> None:
        self.assertIn("NO POSITIVE MATCH", self.text)
        self.assertIn("NOT EXECUTED", self.text)
        self.assertIn("NO EVIDENCE", self.text)
        self.assertIn("NOT TESTED", self.text)
        self.assertIn("GATE UNMET", self.text)
        self.assertIn("LOCAL FIXTURE ONLY", self.text)
        self.assertNotIn("END-TO-END VERIFIED", self.text)
        self.assertNotIn("second endpoint VERIFIED", self.text)
        self.assertNotIn("mailbox read succeeded", self.text)
        self.assertNotIn("fresh_recovery_ok", self.text)
        lowered = self.text.casefold()
        self.assertNotIn("production go", lowered)
        self.assertIn("a button, a registered tool, or a runbook is not a pass", lowered)
