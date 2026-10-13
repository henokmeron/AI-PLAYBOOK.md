#!/usr/bin/env python3
"""Install Gemma-compatible vLLM against CUDA 12.8 host (driver 570)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ENV = Path("/tmp/vllm-gemma-cu128")
DIAG = Path("/workspace/platform-diagnostics/first-release")


def main() -> int:
    DIAG.mkdir(parents=True, exist_ok=True)
    if ENV.exists():
        shutil.rmtree(ENV)
    # Free space if old broken envs remain
    for path in (Path("/tmp/vllm-qwen-env"), Path("/tmp/vllm-clean-env")):
        if path.exists():
            print("removing", path, flush=True)
            shutil.rmtree(path)

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = "/tmp/uv-cache"
    env["TMPDIR"] = "/tmp"
    Path("/tmp/uv-cache").mkdir(exist_ok=True)
    log = DIAG / "gemma-cu128-install.log"
    with log.open("w", encoding="utf-8") as fh:
        def run(cmd: list[str]) -> None:
            print("+", " ".join(cmd), flush=True)
            subprocess.check_call(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT)

        run(["uv", "venv", str(ENV)])
        # Pin to the previously validated Gemma major line, but resolve torch for this driver.
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(ENV / "bin/python"),
                "vllm==0.31.0",
                "--torch-backend=auto",
            ]
        )
        run(
            [
                str(ENV / "bin/python"),
                "-c",
                "import torch,vllm; print(torch.__version__, torch.version.cuda, "
                "torch.cuda.is_available(), vllm.__version__, "
                "torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)",
            ]
        )
    print("INSTALL_OK", flush=True)
    print(log.read_text(errors="replace")[-800:], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
