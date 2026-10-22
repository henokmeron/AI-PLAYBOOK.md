#!/usr/bin/env python3
"""Synthetic quiz regression. No handbook answers and no GPU."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval" / "rag"))
sys.path.insert(0, str(ROOT / "rag"))
sys.path.insert(0, str(ROOT / "api"))

import document_quiz_regression as quiz  # noqa: E402


class DocumentQuizRegressionTests(unittest.TestCase):
    def test_synthetic_quiz_measures_truncation_packing_and_abstention(self) -> None:
        report = quiz.evaluate()
        self.assertEqual(report["failures"], [], report)
        self.assertGreater(report["question_chars"], quiz.OLD_SILENT_CAP)
        self.assertLessEqual(report["question_chars"], report["current_cap_chars"])
        self.assertFalse(report["tail_marker_in_old_cap"])
        self.assertTrue(report["tail_marker_in_full"])
        self.assertTrue(report["current_cap_keeps_quiz"])
        self.assertGreater(report["parts"], 2)
        self.assertTrue(report["absent_part_abstains"])
        self.assertFalse(report["absent_terms_in_model_question"])
        self.assertEqual(report["answerable_parts_abstain"], [])
        self.assertTrue(report["standalone_absent_abstains"])
        self.assertFalse(report["standalone_tail_abstains"])
        self.assertGreater(report["after"]["packed"], report["before"]["packed"])
        self.assertGreater(report["after"]["ratio"], report["before"]["ratio"])
        self.assertFalse(report["before"]["tail_marker_packed"])
        self.assertTrue(report["after"]["tail_marker_packed"])
        self.assertTrue(report["citations"]["missing_label_withheld"])
        self.assertTrue(report["citations"]["grounded_quote_kept"])
        self.assertTrue(report["citations"]["ungrounded_quote_withheld"])
        self.assertNotIn("msfc", json_blob(report))
        self.assertNotIn("nasa", json_blob(report))

    def test_old_box_stores_a_prefix_and_the_current_box_refuses_it(self) -> None:
        question = quiz.build_quiz()
        cut = quiz.stored_question(question, quiz.OLD_SILENT_CAP, refuse_over=False)
        self.assertIsNotNone(cut)
        self.assertEqual(len(cut), quiz.OLD_SILENT_CAP)
        self.assertNotIn(quiz.TAIL_MARKER, cut)
        refused = quiz.stored_question(question, quiz.OLD_SILENT_CAP, refuse_over=True)
        self.assertIsNone(refused)
        kept = quiz.stored_question(question, 8000, refuse_over=True)
        self.assertEqual(kept, question)

    def test_question_box_does_not_silently_cut_at_2000(self) -> None:
        html = (ROOT / "web" / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
        gateway_source = (ROOT / "api" / "local_gateway.py").read_text(encoding="utf-8")
        self.assertIn('id="rag-question" rows="6" maxlength="8000"', html)
        self.assertNotIn('id="rag-question" rows="6" maxlength="2000"', html)
        self.assertIn("so it was not pasted and the end was not cut off.", script)
        self.assertNotIn("ragQuestion.value = incoming.slice", script)
        self.assertIn("len(question) > MAX_QUESTION_CHARS", gateway_source)
        self.assertNotIn("question[:2000]", gateway_source)


def json_blob(report: dict) -> str:
    return str(report).casefold()


if __name__ == "__main__":
    unittest.main()
