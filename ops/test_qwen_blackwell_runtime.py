#!/usr/bin/env python3
"""The Blackwell runtime must stay off the saved A100 environment."""
from __future__ import annotations

import unittest
from pathlib import Path

OPS = Path(__file__).resolve().parent
INSTALL = OPS / "install-qwen-blackwell-env.sh"
SERVE = OPS / "start-qwen-blackwell.sh"
LOCK = OPS / "blackwell-runtime.lock"
A100_RESTORE = OPS / "restore-qwen-runtime.sh"
REGISTRY = OPS.parent / "models" / "registry.yaml"
WHEEL = (
    "https://github.com/vllm-project/vllm/releases/download/v0.32.0/"
    "vllm-0.32.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl"
)
WHEEL_SHA256 = "9918be806fb2808c406547ff4f9f43870ac6ff28dc4b179291fcf532145bb50b"


def _lock_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key] = value.strip().strip('"')
    return fields


class BlackwellRuntimeIsolationTest(unittest.TestCase):
    def test_install_pins_cuda_129_and_refuses_saved_environments(self) -> None:
        text = INSTALL.read_text(encoding="utf-8")
        lock = LOCK.read_text(encoding="utf-8")
        fields = _lock_fields(lock)
        self.assertIn("/tmp/vllm-qwen-blackwell-env", text)
        self.assertIn("--torch-backend=cu129", text)
        self.assertNotIn("--torch-backend=cu130", text)
        self.assertIn("2.13.0+cu126", text)
        self.assertIn("download-kernels", text)
        self.assertIn("sha256sum -c -", text)
        self.assertIn('fail "refusing to install into $ENV_DIR"', text)
        self.assertIn("/tmp/vllm-qwen-env", text)
        self.assertIn("/tmp/vllm-clean-env", text)
        self.assertIn("compute capability", text)
        self.assertNotIn("rm -rf /workspace", text)
        self.assertNotIn("vllm-qwen-env.tar.zst", text)
        self.assertEqual(fields["vllm"], "0.32.0+cu129")
        self.assertEqual(fields["vllm_wheel_url"], WHEEL)
        self.assertEqual(fields["vllm_wheel_sha256"], WHEEL_SHA256)
        self.assertEqual(fields["torch"], "2.13.0+cu129")
        self.assertEqual(fields["torch_backend"], "cu129")
        self.assertEqual(fields["rejected_torch"], "2.13.0+cu126")
        self.assertEqual(fields["cu130_vllm_wheel"], "absent")
        self.assertEqual(fields["minimum_driver_major"], "575")
        self.assertEqual(fields["minimum_compute_capability"], "12")
        self.assertEqual(fields["python_spec"], ">=3.11,<3.15")
        self.assertRegex(fields["vllm_wheel_sha256"], r"^[0-9a-f]{64}$")

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
        self.assertIn("qwen-vllm-blackwell-cu129:", text)
        self.assertNotIn("qwen-vllm-blackwell-cu130:", text)
        self.assertIn('torch: "2.13.0+cu129"', text)
        self.assertIn("qwen-vllm-nightly-isolated:", text)
        self.assertIn('runtime_profile: qwen-vllm-nightly-isolated', text)
        self.assertLess(
            text.index("runtime_profile: qwen-vllm-nightly-isolated"),
            text.index("qwen-vllm-blackwell-cu129:"),
        )


if __name__ == "__main__":
    unittest.main()
