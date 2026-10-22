"""Windows file replacement retries a brief lock and still fails closed."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from integrations.state_guard import replace_file


class ReplaceFileTests(unittest.TestCase):
    def test_retries_a_brief_lock_then_replaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "row.tmp"
            destination = Path(tmp) / "row.json"
            source.write_text("new\n", encoding="utf-8")
            destination.write_text("old\n", encoding="utf-8")
            calls = {"n": 0}
            real = os.replace

            def flaky(src: str, dst: str) -> None:
                calls["n"] += 1
                if calls["n"] < 3:
                    raise PermissionError(5, "Access is denied")
                real(src, dst)

            with mock.patch("integrations.state_guard.os.replace", side_effect=flaky), \
                    mock.patch("integrations.state_guard.time.sleep"):
                replace_file(source, destination, attempts=5)
            self.assertEqual(destination.read_text(encoding="utf-8"), "new\n")
            self.assertEqual(calls["n"], 3)

    def test_a_persistent_denial_is_raised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "row.tmp"
            source.write_text("new\n", encoding="utf-8")
            with mock.patch(
                "integrations.state_guard.os.replace",
                side_effect=PermissionError(5, "Access is denied"),
            ), mock.patch("integrations.state_guard.time.sleep"):
                with self.assertRaises(PermissionError):
                    replace_file(source, Path(tmp) / "row.json", attempts=3)
