#!/usr/bin/env python3
"""Fresh Qwen venv matched to this Pod's CUDA 12.8 / torch 2.8 host stack.

Removes incompatible extracted archives from /tmp only (Global Volume archives kept).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

ENV = Path("/tmp/vllm-qwen-env")
DIAG = Path("/workspace/platform-diagnostics/first-release")


def main() -> int:
    DIAG.mkdir(parents=True, exist_ok=True)
    # Free overlay space; do not touch /workspace archives or weights.
    for path in (Path("/tmp/vllm-qwen-env"), Path("/tmp/vllm-clean-env")):
        if path.exists():
            print("removing", path, flush=True)
            shutil.rmtree(path)

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = "/tmp/uv-cache"
    env["TMPDIR"] = "/tmp"
    Path("/tmp/uv-cache").mkdir(parents=True, exist_ok=True)

    log_path = DIAG / "qwen-env-install.log"
    with log_path.open("w", encoding="utf-8") as log:
        def run(cmd: list[str]) -> None:
            print("+", " ".join(cmd), flush=True)
            subprocess.check_call(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)

        run(["uv", "venv", str(ENV)])
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(ENV / "bin/python"),
                "-U",
                "vllm",
                "--torch-backend=auto",
                "--extra-index-url",
                "https://wheels.vllm.ai/nightly",
            ]
        )
        run(
            [
                str(ENV / "bin/python"),
                "-c",
                "import torch,vllm; print('torch', torch.__version__, 'cuda', torch.version.cuda, "
                "'avail', torch.cuda.is_available(), 'vllm', vllm.__version__, "
                "'gpu', torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)",
            ]
        )
    print("INSTALL_OK", flush=True)
    print(log_path.read_text(encoding="utf-8", errors="replace")[-1500:], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
