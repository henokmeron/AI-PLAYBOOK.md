#!/usr/bin/env python3
"""Start Gemma + main gateway/console when Qwen cannot load on this driver."""
from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path("/tmp/AI-PLAYBOOK")
ENV = Path("/tmp/vllm-clean-env")
MODEL = Path("/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it")
KEY = Path("/tmp/platform-gateway.key")
DIAG = Path("/workspace/platform-diagnostics/first-release")


def healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_key() -> str:
    if not KEY.is_file():
        key = subprocess.check_output(
            ["openssl", "rand", "-base64", "48"], text=True
        ).strip()
        KEY.write_text(key, encoding="utf-8")
        KEY.chmod(0o600)
    return KEY.read_text(encoding="utf-8").strip()


def main() -> int:
    DIAG.mkdir(parents=True, exist_ok=True)
    if not (ENV / "bin/vllm").is_file():
        script = REPO / "scripts/restore-vllm-environment.sh"
        data = script.read_bytes().replace(b"\r\n", b"\n")
        Path("/tmp/restore-vllm-environment.sh").write_bytes(data)
        subprocess.check_call(["bash", "/tmp/restore-vllm-environment.sh"])

    key = ensure_key()
    env = os.environ.copy()
    env["PATH"] = f"{ENV / 'bin'}:{env.get('PATH', '')}"
    env["TMPDIR"] = "/tmp"
    env["VLLM_RPC_BASE_PATH"] = "/tmp"
    env.pop("LD_LIBRARY_PATH", None)

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
        (DIAG / "gemma-vllm.pid").write_text(str(proc.pid) + "\n", encoding="utf-8")
        print("STARTED_GEMMA", proc.pid, flush=True)
        for i in range(240):
            time.sleep(5)
            if healthy("http://127.0.0.1:8000/v1/models"):
                print("GEMMA_READY", (i + 1) * 5, flush=True)
                break
            if proc.poll() is not None:
                print("GEMMA_EXIT", proc.returncode, flush=True)
                print((DIAG / "gemma-vllm.log").read_text(errors="replace")[-2000:])
                return 1
        else:
            print("GEMMA_TIMEOUT")
            return 1

    # PyYAML for registry: use gemma env python if system pip blocked
    gw_python = str(ENV / "bin/python")
    subprocess.call([gw_python, "-m", "pip", "install", "--quiet", "pyyaml"])

    if not healthy("http://127.0.0.1:8010/health"):
        gw_env = os.environ.copy()
        gw_env.update(
            {
                "PLATFORM_HOST": "127.0.0.1",
                "PLATFORM_PORT": "8010",
                "PLATFORM_API_KEY": key,
                "PLATFORM_API_KEY_FILE": str(KEY),
                "VLLM_UPSTREAM_URL": "http://127.0.0.1:8000/v1",
                "PLATFORM_MODEL_REGISTRY": str(REPO / "models/registry.yaml"),
                "PLATFORM_DEFAULT_MODEL_ID": "gemma-4-31b-it",
                "PYTHONPATH": f"{REPO / 'api'}:{REPO / 'models'}:{REPO / 'rag'}",
            }
        )
        log = (DIAG / "gateway.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [gw_python, str(REPO / "api/local_gateway.py")],
            cwd=str(REPO / "api"),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=gw_env,
            start_new_session=True,
        )
        (DIAG / "gateway.pid").write_text(str(proc.pid) + "\n", encoding="utf-8")
        time.sleep(2)
        if not healthy("http://127.0.0.1:8010/health"):
            print("GATEWAY_FAIL")
            print((DIAG / "gateway.log").read_text(errors="replace")[-1500:])
            return 1
        print("GATEWAY_OK", flush=True)

    if not healthy("http://127.0.0.1:8080/api/status"):
        web_env = os.environ.copy()
        web_env.update(
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
            env=web_env,
            start_new_session=True,
        )
        (DIAG / "console.pid").write_text(str(proc.pid) + "\n", encoding="utf-8")
        time.sleep(2)
        if not healthy("http://127.0.0.1:8080/api/status"):
            print("CONSOLE_FAIL")
            print((DIAG / "console.log").read_text(errors="replace")[-1500:])
            return 1
        print("CONSOLE_OK", flush=True)

    print("FALLBACK_STACK_READY :8000/:8010/:8080 gemma", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
