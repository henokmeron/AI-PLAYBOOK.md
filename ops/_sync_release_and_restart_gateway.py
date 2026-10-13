#!/usr/bin/env python3
"""Sync local fixes onto the Pod repo + volume release folder; bounce gateway/console only."""
from __future__ import annotations

import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path("/tmp/AI-PLAYBOOK")
RELEASE = Path("/workspace/ai-platform-release")
ENV = Path("/tmp/vllm-qwen-env")
KEY = Path("/tmp/platform-gateway.key")
DIAG = Path("/workspace/platform-diagnostics/complete")


def healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def stop_pidfile(name: str) -> None:
    path = DIAG / name
    if not path.is_file():
        return
    try:
        pid = int(path.read_text().strip())
    except Exception:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def main() -> int:
    DIAG.mkdir(parents=True, exist_ok=True)
    # Overlay was already SCP'd into /tmp/stage; copy into repo + release.
    stage = Path("/tmp/stage-release")
    for rel in (
        "api/local_gateway.py",
        "ops/_complete_bringup.py",
        "ops/start-first-release.sh",
        "ops/start-qwen-isolated.sh",
        "ops/_pod_e2e_verify.py",
        "docs/first-release-recovery.md",
    ):
        src = stage / rel
        if not src.is_file():
            print("MISSING", src)
            continue
        dest = REPO / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        dest.write_bytes(data)
        print("SYNC", dest)

    # Refresh volume release package via bring-up helper write path.
    subprocess.check_call(
        [
            "/usr/bin/python3",
            "-c",
            "import importlib.util; "
            "spec=importlib.util.spec_from_file_location('b','/tmp/AI-PLAYBOOK/ops/_complete_bringup.py'); "
            "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
            "m.write_release_launcher()",
        ]
    )

    key = KEY.read_text().strip()
    stop_pidfile("gateway.pid")
    stop_pidfile("console.pid")
    time.sleep(1)
    subprocess.call(["pkill", "-f", "local_gateway.py"])
    subprocess.call(["pkill", "-f", "web/server.py"])
    time.sleep(1)

    gw_env = os.environ.copy()
    gw_env.update(
        {
            "PLATFORM_HOST": "127.0.0.1",
            "PLATFORM_PORT": "8010",
            "PLATFORM_API_KEY": key,
            "PLATFORM_API_KEY_FILE": str(KEY),
            "VLLM_UPSTREAM_URL": "http://127.0.0.1:8002/v1",
            "PLATFORM_MODEL_REGISTRY": str(REPO / "models/registry.yaml"),
            "PLATFORM_DEFAULT_MODEL_ID": "qwen3.5-27b",
            "PYTHONPATH": f"{REPO / 'api'}:{REPO / 'models'}:{REPO / 'rag'}",
            "RAG_DOCS_DIR": "/workspace/rag-demo-docs",
            "RAG_MANAGED_DOCS_DIR": "/workspace/rag-managed-docs",
        }
    )
    py = str(ENV / "bin/python") if (ENV / "bin/python").is_file() else "/usr/bin/python3"
    subprocess.call([py, "-m", "pip", "install", "--quiet", "pyyaml"])
    log = (DIAG / "gateway.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [py, str(REPO / "api/local_gateway.py")],
        cwd=str(REPO / "api"),
        stdout=log,
        stderr=subprocess.STDOUT,
        env=gw_env,
        start_new_session=True,
    )
    (DIAG / "gateway.pid").write_text(str(proc.pid) + "\n", encoding="utf-8")

    web_env = os.environ.copy()
    web_env.update(
        {
            "WEB_HOST": "127.0.0.1",
            "WEB_PORT": "8080",
            "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010",
            "PLATFORM_API_KEY_FILE": str(KEY),
            "PLATFORM_MODEL_ID": "qwen3.5-27b",
        }
    )
    clog = (DIAG / "console.log").open("w", encoding="utf-8")
    cproc = subprocess.Popen(
        ["/usr/bin/python3", str(REPO / "web/server.py")],
        cwd=str(REPO / "web"),
        stdout=clog,
        stderr=subprocess.STDOUT,
        env=web_env,
        start_new_session=True,
    )
    (DIAG / "console.pid").write_text(str(cproc.pid) + "\n", encoding="utf-8")

    for _ in range(30):
        if healthy("http://127.0.0.1:8010/health") and healthy(
            "http://127.0.0.1:8080/api/status"
        ):
            print("GATEWAY_CONSOLE_READY")
            return 0
        time.sleep(1)
    print("RESTART_FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
