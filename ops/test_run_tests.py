"""The sequential runner lists modules without starting servers."""
from __future__ import annotations

import unittest
from pathlib import Path

from ops.run_tests import discover_modules


class RunTestsDiscovery(unittest.TestCase):
    def test_discovers_gateway_and_microsoft_modules(self) -> None:
        root = Path(__file__).resolve().parents[1]
        modules = discover_modules(root)
        self.assertIn("api.test_gateway_reliability", modules)
        self.assertIn("integrations.tests.test_microsoft_oauth", modules)
        self.assertNotIn("windows_repair.test_device", modules)


if __name__ == "__main__":
    unittest.main()
