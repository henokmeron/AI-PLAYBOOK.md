#!/usr/bin/env python3
"""Serve Gemma with cu128 env + cudart.13 on LD_LIBRARY_PATH, then main gateway/console."""
from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path

ENV = Path("/tmp/vllm-gemma-cu128")
REPO = Path("/tmp/AI-PLAYBOOK")
MODEL = Path("/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it")
KEY = Path("/tmp/platform-gateway.key")
DIAG = Path("/workspace/platform-diagnostics/first-release")
CU13 = ENV / "lib/python3.12/site-packages/nvidia/cu13/lib"
CU12 = ENV / "lib/python3.12/site-packages/nvidia/cuda_runtime/lib"


def healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> int:
    DIAG.mkdir(parents=True, exist_ok=True)
    if not KEY.is_file():
        key = subprocess.check_output(["openssl", "rand", "-base64", "48"], text=True).strip()
        KEY.write_text(key, encoding="utf-8")
        KEY.chmod(0o600)
    key = KEY.read_text().strip()

    env = os.environ.copy()
    env["PATH"] = f"{ENV / 'bin'}:{env.get('PATH', '')}"
    env["LD_LIBRARY_PATH"] = f"{CU13}:{CU12}"
    env["TMPDIR"] = "/tmp"
    env["VLLM_RPC_BASE_PATH"] = "/tmp"

    if not healthy("http://127.0.0.1:8000/v1/models"):
        log = (DIAG / "gemma-vllm.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [
                str(ENV / "bin/python"),
                str(ENV / "bin/vllm"),
                "serve",
                str(MODEL),
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--gpu-memory-utilization",
                "0.90",
                "--max-model-len",
                "8192",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        (DIAG / "gemma-vllm.pid").write_text(str(proc.pid) + "\n")
        print("STARTED", proc.pid, flush=True)
        for i in range(300):
            time.sleep(5)
            if healthy("http://127.0.0.1:8000/v1/models"):
                print("READY", (i + 1) * 5, flush=True)
                break
            if proc.poll() is not None:
                print("EXIT", proc.returncode, flush=True)
                print((DIAG / "gemma-vllm.log").read_text(errors="replace")[-2500:])
                return 1
        else:
            print("TIMEOUT")
            print((DIAG / "gemma-vllm.log").read_text(errors="replace")[-2500:])
            return 1

    # Prefer gemma env python for gateway (has pyyaml installable)
    subprocess.call([str(ENV / "bin/python"), "-m", "pip", "install", "--quiet", "pyyaml"])
    if not healthy("http://127.0.0.1:8010/health"):
        gw = os.environ.copy()
        gw.update(
            {
                "PLATFORM_HOST": "127.0.0.1",
                "PLATFORM_PORT": "8010",
                "PLATFORM_API_KEY": key,
                "VLLM_UPSTREAM_URL": "http://127.0.0.1:8000/v1",
                "PLATFORM_MODEL_REGISTRY": str(REPO / "models/registry.yaml"),
                "PLATFORM_DEFAULT_MODEL_ID": "gemma-4-31b-it",
                "PYTHONPATH": f"{REPO/'api'}:{REPO/'models'}:{REPO/'rag'}",
            }
        )
        log = (DIAG / "gateway.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [str(ENV / "bin/python"), str(REPO / "api/local_gateway.py")],
            cwd=str(REPO / "api"),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=gw,
            start_new_session=True,
        )
        (DIAG / "gateway.pid").write_text(str(proc.pid) + "\n")
        time.sleep(2)
        assert healthy("http://127.0.0.1:8010/health"), "gateway failed"
        print("GATEWAY_OK", flush=True)

    if not healthy("http://127.0.0.1:8080/api/status"):
        web = os.environ.copy()
        web.update(
            {
                "WEB_HOST": "127.0.0.1",
                "WEB_PORT": "8080",
                "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010",
                "PLATFORM_API_KEY_FILE": str(KEY),
                "PLATFORM_MODEL_ID": "gemma-4-31b-it",
            }
        )
        log = (DIAG / "console.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            ["/usr/bin/python3", str(REPO / "web/server.py")],
            cwd=str(REPO / "web"),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=web,
            start_new_session=True,
        )
        (DIAG / "console.pid").write_text(str(proc.pid) + "\n")
        time.sleep(2)
        assert healthy("http://127.0.0.1:8080/api/status"), "console failed"
        print("CONSOLE_OK", flush=True)

    print("STACK_READY gemma :8000/:8010/:8080", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
