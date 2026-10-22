"""State which checks are local and which need the deployed H100.

``python -m ops.run_tests`` discovers unittest modules. Those are LOCAL/MOCK.
``windows_repair.tests.test_live_diagnostics`` is in that suite: it reads this
Windows PC and does not call Qwen. The scripts below talk to a loopback
gateway that exists only on a running pod. They are not part of the suite.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from ops.run_tests import discover_modules

LOCAL_MOCK = "LOCAL/MOCK"
REQUIRES_LIVE_H100 = "REQUIRES LIVE INFERENCE and REQUIRES DEPLOYED H100"

# Module name -> path. Each file calls the loopback gateway or Qwen.
LIVE_H100_SCRIPTS = {
    "agents.live_smoke": "agents/live_smoke.py",
    "agents.live_async_smoke": "agents/live_async_smoke.py",
    "evaluation.run_live_platform_smoke": "evaluation/run_live_platform_smoke.py",
    "evaluation.run_live_rag_regression": "evaluation/run_live_rag_regression.py",
}

THIS_PC_NOT_H100 = "windows_repair.tests.test_live_diagnostics"


def lane(module: str) -> str:
    if module in LIVE_H100_SCRIPTS:
        return REQUIRES_LIVE_H100
    return LOCAL_MOCK


class TestLanes(unittest.TestCase):
    def test_suite_is_local_and_live_scripts_stay_out(self) -> None:
        root = Path(__file__).resolve().parents[1]
        discovered = discover_modules(root)
        self.assertIn(THIS_PC_NOT_H100, discovered)
        self.assertEqual(lane(THIS_PC_NOT_H100), LOCAL_MOCK)
        for name in discovered:
            self.assertEqual(lane(name), LOCAL_MOCK, name)
            self.assertFalse(name.startswith("ops._"), name)
            self.assertNotIn(".__pycache__.", name)
        for module, relative in LIVE_H100_SCRIPTS.items():
            path = root / relative
            self.assertTrue(path.is_file(), relative)
            text = path.read_text(encoding="utf-8")
            self.assertIn("127.0.0.1", text, relative)
            self.assertNotIn(module, discovered, module)
            self.assertEqual(lane(module), REQUIRES_LIVE_H100)


if __name__ == "__main__":
    unittest.main()
