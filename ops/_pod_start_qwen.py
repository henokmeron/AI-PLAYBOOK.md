#!/usr/bin/env python3
"""Start isolated Qwen vLLM on :8002 with CUDA 13 library path."""
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
DIAG = Path("/workspace/platform-diagnostics/qwen")
PID_FILE = DIAG / "qwen-vllm.pid"
LOG_FILE = DIAG / "qwen-vllm.log"
LD_FILE = DIAG / "ld_library_path.txt"
PORT = 8002


def build_ld_path() -> str:
    dirs: set[str] = set()
    nvidia = ENV / "lib/python3.12/site-packages/nvidia"
    if nvidia.is_dir():
        for so in nvidia.rglob("lib*.so*"):
            dirs.add(str(so.parent))
    for so in ENV.rglob("libcudart.so.13"):
        dirs.add(str(so.parent))
    path = ":".join(sorted(dirs))
    DIAG.mkdir(parents=True, exist_ok=True)
    LD_FILE.write_text(path + "\n", encoding="utf-8")
    return path


def stop_prior() -> None:
    if PID_FILE.is_file():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            time.sleep(2)
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    subprocess.run(["pkill", "-f", f"vllm serve.*{PORT}"], check=False)


def main() -> int:
    if not MODEL.is_dir():
        print(f"FAIL: model missing at {MODEL}")
        return 1
    if not (ENV / "bin/vllm").is_file():
        print(f"FAIL: vllm missing in {ENV}")
        return 1

    ld = build_ld_path()
    stop_prior()
    DIAG.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PATH"] = f"{ENV / 'bin'}:{env.get('PATH', '')}"
    env["LD_LIBRARY_PATH"] = f"{ld}:{env.get('LD_LIBRARY_PATH', '')}"
    env["TMPDIR"] = "/tmp"
    env["VLLM_RPC_BASE_PATH"] = "/tmp"
    env["VIRTUAL_ENV"] = str(ENV)

    cmd = [
        str(ENV / "bin/python"),
        str(ENV / "bin/vllm"),
        "serve",
        str(MODEL),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
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
    log_fh = LOG_FILE.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid) + "\n", encoding="utf-8")
    print(f"STARTED_PID={proc.pid}")
    print(f"LOG={LOG_FILE}")

    # Wait briefly and show early log
    time.sleep(8)
    if LOG_FILE.is_file():
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-50:]:
            print(line)
    if proc.poll() is not None:
        print(f"FAIL: vLLM exited early with code {proc.returncode}")
        return 1
    print("OK: vLLM still running after startup window")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
