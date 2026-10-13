#!/usr/bin/env python3
"""Retry Qwen start without CUDA-13-preferring LD_LIBRARY_PATH (driver is 12.8)."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

ENV = Path("/tmp/vllm-qwen-env")
MODEL = Path(
    "/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654"
)
DIAG = Path("/workspace/platform-diagnostics/first-release")
LOG = DIAG / "qwen-vllm.log"
PIDF = DIAG / "qwen-vllm.pid"


def main() -> int:
    DIAG.mkdir(parents=True, exist_ok=True)
    # Stop leftovers
    subprocess.run(["pkill", "-f", "vllm serve.*8002"], check=False)
    time.sleep(2)

    # Prefer torch/cu12 libs; do NOT prepend nvidia/cu13 (breaks driver 570 / CUDA 12.8).
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    env["PATH"] = f"{ENV / 'bin'}:{env.get('PATH', '')}"
    env["TMPDIR"] = "/tmp"
    env["VLLM_RPC_BASE_PATH"] = "/tmp"
    env["VIRTUAL_ENV"] = str(ENV)

    # Import check
    chk = subprocess.run(
        [str(ENV / "bin/python"), "-c", "import vllm; print(vllm.__version__)"],
        env=env,
        capture_output=True,
        text=True,
    )
    print("import_rc", chk.returncode, "out", chk.stdout.strip(), "err", chk.stderr[-400:])
    if chk.returncode != 0:
        return 1

    log_fh = LOG.open("w", encoding="utf-8")
    cmd = [
        str(ENV / "bin/python"),
        str(ENV / "bin/vllm"),
        "serve",
        str(MODEL),
        "--host",
        "127.0.0.1",
        "--port",
        "8002",
        "--trust-remote-code",
        "--language-model-only",
        "--reasoning-parser",
        "qwen3",
        "--max-model-len",
        "8192",
        "--gpu-memory-utilization",
        "0.90",
        "--default-chat-template-kwargs",
        '{"enable_thinking": false}',
    ]
    proc = subprocess.Popen(
        cmd, stdout=log_fh, stderr=subprocess.STDOUT, env=env, start_new_session=True
    )
    PIDF.write_text(str(proc.pid) + "\n", encoding="utf-8")
    print("STARTED", proc.pid)

    for i in range(180):
        time.sleep(5)
        try:
            import urllib.request

            with urllib.request.urlopen("http://127.0.0.1:8002/v1/models", timeout=3) as r:
                if r.status == 200:
                    print("READY after", (i + 1) * 5, "s")
                    return 0
        except Exception:
            pass
        if proc.poll() is not None:
            print("EXITED", proc.returncode)
            print(LOG.read_text(encoding="utf-8", errors="replace")[-2500:])
            return 1
    print("TIMEOUT")
    print(LOG.read_text(encoding="utf-8", errors="replace")[-2500:])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
