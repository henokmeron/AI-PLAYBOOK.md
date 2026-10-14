#!/usr/bin/env python3
"""The Qwen launch line must put the restored env's bin directory on PATH.

A fresh RunPod image does not ship `ninja`. FlashInfer JIT fails without it.
The archived env provides `/tmp/vllm-qwen-env/bin/ninja`.
"""
from __future__ import annotations

import unittest
from pathlib import Path

LAUNCH = Path(__file__).resolve().parent / "start-first-release.sh"


class QwenLaunchPathTest(unittest.TestCase):
    def test_vllm_launch_puts_env_bin_on_path(self) -> None:
        text = LAUNCH.read_text(encoding="utf-8")
        launch_lines = [
            line for line in text.splitlines()
            if "vllm" in line and "serve" in line and "nohup" in line
        ]
        self.assertTrue(launch_lines, "Qwen vLLM launch line not found")
        for line in launch_lines:
            self.assertIn(
                'PATH="$QWEN_ENV/bin:${PATH:-}"',
                line,
                "Qwen launch must prefix PATH with the restored environment bin",
            )


if __name__ == "__main__":
    unittest.main()
