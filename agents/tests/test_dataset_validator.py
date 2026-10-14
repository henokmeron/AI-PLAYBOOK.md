"""Tests for the fine-tuning dataset JSONL validator (no training, no GPU)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agents.dataset_validator import validate_file


def record(rid: str, split: str = "train", user: str = "What is annual leave?", **overrides):
    base = {
        "id": rid, "split": split, "source": "synthetic:handbook-v1", "license": "internal-owned",
        "contains_personal_data": False,
        "messages": [
            {"role": "system", "content": "Answer from the handbook."},
            {"role": "user", "content": user},
            {"role": "assistant", "content": "25 days [employee-handbook.md]."},
        ],
    }
    base.update(overrides)
    return base


class DatasetValidatorTests(unittest.TestCase):
    def write(self, rows) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
        with tmp:
            for row in rows:
                tmp.write((row if isinstance(row, str) else json.dumps(row)) + "\n")
        self.addCleanup(Path(tmp.name).unlink)
        return Path(tmp.name)

    def test_valid_dataset(self) -> None:
        report = validate_file(self.write([
            record("a1"), record("a2", "validation", "Expense limit?"), record("a3", "test", "Notice period?"),
        ]))
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.splits, {"train": 1, "validation": 1, "test": 1})

    def test_structural_errors(self) -> None:
        bad_roles = record("b1")
        bad_roles["messages"] = [{"role": "assistant", "content": "x"}, {"role": "user", "content": "y"}]
        report = validate_file(self.write([
            "not json", record("b0", split="dev"), bad_roles,
            {k: v for k, v in record("b2").items() if k != "license"},
        ]))
        joined = "\n".join(report.errors)
        self.assertIn("not valid UTF-8 JSON", joined)
        self.assertIn("split must be one of", joined)
        self.assertIn("alternate", joined)
        self.assertIn("missing fields ['license']", joined)

    def test_duplicates_and_split_leakage(self) -> None:
        report = validate_file(self.write([record("c1"), record("c1"), record("c2", "test")]))
        joined = "\n".join(report.errors)
        self.assertIn("duplicate id", joined)
        self.assertIn("split leakage", joined)

    def test_secrets_and_personal_data(self) -> None:
        report = validate_file(self.write([
            record("d1", user="my key is sk-" + "a" * 30),
            record("d2", user="email jane@example.com about leave"),
            record("d3", contains_personal_data=True),
        ]))
        joined = "\n".join(report.errors)
        self.assertIn("credential", joined)
        self.assertIn("consent_basis", joined)
        self.assertTrue(any("personal data" in w for w in report.warnings))

    def test_context_limit(self) -> None:
        report = validate_file(self.write([record("e1", user="x " * 20000)]), max_tokens=8192)
        self.assertIn("exceeds the 8192-token", "\n".join(report.errors))


if __name__ == "__main__":
    unittest.main()
