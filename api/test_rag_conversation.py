#!/usr/bin/env python3
"""Unit tests for Document Q&A history validation and calculation prompting."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


def load_gateway_module():
    """Load local_gateway.py without importing rag document modules from PATH."""
    api_dir = Path(__file__).resolve().parent
    rag_dir = api_dir.parent / "rag"
    for path in (str(api_dir), str(rag_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)
    module_path = api_dir / "local_gateway.py"
    spec = importlib.util.spec_from_file_location("local_gateway_under_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load local_gateway.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gateway = load_gateway_module()


class RagConversationTests(unittest.TestCase):
    def test_history_defaults_and_accepts_bounded_turns(self) -> None:
        self.assertEqual(gateway.validate_rag_history(None), [])
        cleaned = gateway.validate_rag_history([
            {"role": "user", "content": " How many days? "},
            {"role": "assistant", "content": "10 business days"},
        ])
        self.assertEqual(cleaned, [
            {"role": "user", "content": "How many days?"},
            {"role": "assistant", "content": "10 business days"},
        ])

    def test_history_rejects_invalid_shapes(self) -> None:
        cases = [
            "not-a-list",
            [{"role": "assistant", "content": "starts wrong"}],
            [{"role": "user", "content": "only user"}],
            [
                {"role": "user", "content": "q1"},
                {"role": "user", "content": "q2"},
            ],
            [{"role": "system", "content": "nope"}],
            [{"role": "user", "content": ""}],
            [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a" * 2001}],
            [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}] * 7,
        ]
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    gateway.validate_rag_history(value)

    def test_build_messages_includes_history_and_calculation_prompt(self) -> None:
        history = [
            {"role": "user", "content": "What is the daily fee for ages 0-4?"},
            {"role": "assistant", "content": "The daily fee is 100 [Source 1]."},
        ]
        messages = gateway.build_rag_completion_messages(
            "What is the weekly fee?",
            ["[Source 1: file=fees.xlsx; chunk=1]\nage 0-4 daily=100"],
            history,
        )
        self.assertEqual(messages[0]["role"], "system")
        prompt = messages[0]["content"].casefold()
        self.assertIn("daily rate × 7", messages[0]["content"])
        self.assertIn("derived values", prompt)
        self.assertIn("age bands", prompt)
        self.assertIn("placement type", prompt)
        self.assertIn("untrusted", prompt)
        self.assertIn("do not invent", prompt)
        self.assertEqual(messages[1], history[0])
        self.assertEqual(messages[2], history[1])
        self.assertEqual(messages[3]["role"], "user")
        self.assertIn("QUESTION\nWhat is the weekly fee?", messages[3]["content"])
        self.assertIn("fees.xlsx", messages[3]["content"])
        self.assertIn("formula", messages[3]["content"].casefold())
        self.assertIn("derived", messages[3]["content"].casefold())

    def test_build_messages_without_history(self) -> None:
        messages = gateway.build_rag_completion_messages(
            "How many days?",
            ["[Source 1]\n10 business days"],
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")


if __name__ == "__main__":
    unittest.main()
