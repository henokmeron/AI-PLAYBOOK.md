#!/usr/bin/env python3
"""Start Qwen with minimal cu13 cudart path + V0 engine to avoid UVA/driver clash."""
from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path

ENV = Path("/tmp/vllm-qwen-env")
MODEL = Path(
    "/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654"
)
DIAG = Path("/workspace/platform-diagnostics/first-release")
LOG = DIAG / "qwen-vllm.log"
PIDF = DIAG / "qwen-vllm.pid"
CUDART = ENV / "lib/python3.12/site-packages/nvidia/cu13/lib"


def main() -> int:
    DIAG.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pkill", "-f", "vllm serve.*8002"], check=False)
    time.sleep(2)

    env = os.environ.copy()
    env["PATH"] = f"{ENV / 'bin'}:{env.get('PATH', '')}"
    env["TMPDIR"] = "/tmp"
    env["VLLM_RPC_BASE_PATH"] = "/tmp"
    env["VIRTUAL_ENV"] = str(ENV)
    # Provide cudart.13 for the extension, but prefer V0 engine path.
    env["LD_LIBRARY_PATH"] = str(CUDART)
    env["VLLM_USE_V1"] = "0"

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
        "4096",
        "--gpu-memory-utilization",
        "0.85",
        "--enforce-eager",
        "--default-chat-template-kwargs",
        '{"enable_thinking": false}',
    ]
    proc = subprocess.Popen(
        cmd, stdout=log_fh, stderr=subprocess.STDOUT, env=env, start_new_session=True
    )
    PIDF.write_text(str(proc.pid) + "\n", encoding="utf-8")
    print("STARTED", proc.pid, flush=True)

    for i in range(240):
        time.sleep(5)
        try:
            with urllib.request.urlopen("http://127.0.0.1:8002/v1/models", timeout=3) as r:
                if r.status == 200:
                    print("READY after", (i + 1) * 5, "s", flush=True)
                    return 0
        except Exception:
            pass
        if proc.poll() is not None:
            print("EXITED", proc.returncode, flush=True)
            print(LOG.read_text(encoding="utf-8", errors="replace")[-3000:], flush=True)
            return 1
    print("TIMEOUT", flush=True)
    print(LOG.read_text(encoding="utf-8", errors="replace")[-3000:], flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
