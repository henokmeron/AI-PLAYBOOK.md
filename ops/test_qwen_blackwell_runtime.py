#!/usr/bin/env python3
"""The Blackwell runtime must stay off the saved A100 environment."""
from __future__ import annotations

import unittest
from pathlib import Path

OPS = Path(__file__).resolve().parent
INSTALL = OPS / "install-qwen-blackwell-env.sh"
SERVE = OPS / "start-qwen-blackwell.sh"
A100_RESTORE = OPS / "restore-qwen-runtime.sh"
REGISTRY = OPS.parent / "models" / "registry.yaml"


class BlackwellRuntimeIsolationTest(unittest.TestCase):
    def test_install_uses_cuda_13_and_refuses_saved_environments(self) -> None:
        text = INSTALL.read_text(encoding="utf-8")
        self.assertIn("/tmp/vllm-qwen-blackwell-env", text)
        self.assertIn("--torch-backend=cu130", text)
        self.assertIn("download-kernels", text)
        self.assertIn('fail "refusing to install into $ENV_DIR"', text)
        self.assertIn("/tmp/vllm-qwen-env", text)
        self.assertIn("/tmp/vllm-clean-env", text)
        self.assertIn("compute capability", text)
        self.assertNotIn("rm -rf /workspace", text)
        self.assertNotIn("vllm-qwen-env.tar.zst", text)

    def test_serve_does_not_launch_gateway_or_the_a100_env(self) -> None:
        text = SERVE.read_text(encoding="utf-8")
        self.assertIn('PATH="$ENV_DIR/bin:${PATH:-}"', text)
        self.assertIn("--language-model-only", text)
        self.assertIn("--reasoning-parser qwen3", text)
        self.assertNotIn("local_gateway", text)
        self.assertNotIn("web/server.py", text)
        self.assertNotIn("START.sh", text)
        self.assertIn('fail "refusing to launch from $ENV_DIR"', text)

    def test_a100_restore_still_targets_the_saved_archive(self) -> None:
        text = A100_RESTORE.read_text(encoding="utf-8")
        self.assertIn("BACKUP_DIR=/workspace/runtime-setup/qwen-vllm", text)
        self.assertIn('ARCHIVE="$BACKUP_DIR/vllm-qwen-env.tar.zst"', text)
        self.assertIn("/tmp/vllm-qwen-env", text)
        self.assertNotIn("blackwell", text)

    def test_registry_keeps_the_profiles_separate(self) -> None:
        text = REGISTRY.read_text(encoding="utf-8")
        self.assertIn("qwen-vllm-blackwell-cu130:", text)
        self.assertIn("qwen-vllm-nightly-isolated:", text)
        self.assertIn('runtime_profile: qwen-vllm-nightly-isolated', text)
        self.assertLess(
            text.index("runtime_profile: qwen-vllm-nightly-isolated"),
            text.index("qwen-vllm-blackwell-cu130:"),
        )


if __name__ == "__main__":
    unittest.main()
