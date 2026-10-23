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

    def test_console_start_prepares_a_private_operator_store(self) -> None:
        text = LAUNCH.read_text(encoding="utf-8")
        prepare = text.index("operator_status || fail")
        console = text.index('OPERATOR_AUTH_DIR="$OPERATOR_AUTH_DIR"')
        self.assertLess(prepare, console)
        self.assertIn("operators-ready", text)
        self.assertIn("There is no default password.", text)
        self.assertLess(text.index("endpoint_status || fail"), console)
        self.assertIn('ENDPOINT_BACKUP_DIR="${ENDPOINT_BACKUP_DIR:-}"', text)
        self.assertIn('OPERATOR_BACKUP_DIR="${OPERATOR_BACKUP_DIR:-}"', text)
        deploy = Path(__file__).resolve().parent / "release" / "deploy-console-only.sh"
        deploy_text = deploy.read_text(encoding="utf-8")
        self.assertLess(deploy_text.index("ops.platform_state"), deploy_text.index('kill "$P8080"'))
        self.assertLess(deploy_text.index("--endpoint-backup"), deploy_text.index('kill "$P8080"'))
        self.assertIn('ENDPOINT_BACKUP_DIR="$ENDPOINT_BACKUP_DIR"', deploy_text)


if __name__ == "__main__":
    unittest.main()
