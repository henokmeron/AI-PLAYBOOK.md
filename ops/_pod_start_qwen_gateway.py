#!/usr/bin/env python3
"""Start isolated Qwen gateway :8013 and console :8083 on the Pod.

Leaves Gemma main ports :8010/:8080 untouched. Upstream is Qwen :8002 only.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(os.environ.get("REPO_ROOT", "/tmp/AI-PLAYBOOK"))
DIAG = Path("/workspace/platform-diagnostics/qwen")
KEY = Path(os.environ.get("PLATFORM_API_KEY_FILE", "/tmp/platform-gateway.key"))
QWEN_ENV = Path("/tmp/vllm-qwen-env")
CLEAN_ENV = Path("/tmp/vllm-clean-env")


def pick_python() -> Path:
    for candidate in (
        CLEAN_ENV / "bin/python",
        QWEN_ENV / "bin/python",
        Path("/usr/bin/python3"),
    ):
        if candidate.is_file():
            return candidate
    raise SystemExit("FAIL: no usable python for gateway")


def healthy(url: str, timeout: float = 3.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:  # noqa: BLE001
        return False


def ensure_key() -> str:
    if KEY.is_file() and len(KEY.read_text(encoding="utf-8").strip()) >= 32:
        return KEY.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    KEY.write_text(value + "\n", encoding="utf-8")
    KEY.chmod(0o600)
    print(f"WROTE_EPHEMERAL_KEY={KEY}")
    return value


def ensure_pyyaml(py: Path) -> None:
    code = "import yaml; print(yaml.__version__)"
    probe = subprocess.run([str(py), "-c", code], capture_output=True, text=True)
    if probe.returncode == 0:
        print(f"PyYAML OK ({probe.stdout.strip()})")
        return
    print("Installing PyYAML into selected interpreter...")
    subprocess.run([str(py), "-m", "pip", "install", "-q", "pyyaml"], check=True)


def start_proc(name: str, env: dict[str, str], cmd: list[str], log: Path, pidfile: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    fh = log.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        stdout=fh,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    pidfile.write_text(str(proc.pid) + "\n", encoding="utf-8")
    print(f"STARTED_{name}_PID={proc.pid} LOG={log}")


def wait_url(url: str, seconds: int = 60) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if healthy(url):
            return True
        time.sleep(1)
    return False


def main() -> int:
    DIAG.mkdir(parents=True, exist_ok=True)
    if not healthy("http://127.0.0.1:8002/v1/models"):
        print("FAIL: Qwen upstream :8002 not healthy")
        return 1
    if not (REPO / "api/local_gateway.py").is_file():
        print(f"FAIL: gateway missing under {REPO}")
        return 1

    py = pick_python()
    print(f"GATEWAY_PYTHON={py}")
    ensure_pyyaml(py)
    api_key = ensure_key()

    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = f"{REPO / 'api'}:{REPO / 'rag'}:{REPO / 'models'}:{base_env.get('PYTHONPATH', '')}"

    if not healthy("http://127.0.0.1:8013/health"):
        gw_env = base_env.copy()
        gw_env.update(
            {
                "PLATFORM_HOST": "127.0.0.1",
                "PLATFORM_PORT": "8013",
                "PLATFORM_API_KEY": api_key,
                "VLLM_UPSTREAM_URL": "http://127.0.0.1:8002/v1",
                "PLATFORM_DEFAULT_MODEL_ID": "qwen3.5-27b",
                "PLATFORM_MODEL_REGISTRY": str(REPO / "models/registry.yaml"),
            }
        )
        start_proc(
            "GATEWAY",
            gw_env,
            [str(py), str(REPO / "api/local_gateway.py")],
            DIAG / "gateway-8013.log",
            DIAG / "gateway-8013.pid",
        )
        if not wait_url("http://127.0.0.1:8013/health", 60):
            print((DIAG / "gateway-8013.log").read_text(encoding="utf-8", errors="replace")[-3000:])
            print("FAIL: gateway :8013 did not become healthy")
            return 1
    else:
        print("GATEWAY_ALREADY_HEALTHY")

    if (REPO / "web/server.py").is_file() and not healthy("http://127.0.0.1:8083/api/status"):
        ui_env = base_env.copy()
        ui_env.update(
            {
                "WEB_HOST": "127.0.0.1",
                "WEB_PORT": "8083",
                "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8013",
                "PLATFORM_API_KEY_FILE": str(KEY),
                "PLATFORM_MODEL_ID": (
                    "/workspace/models/Qwen3.5-27B/"
                    "fc05daec18b0a78c049392ed2e771dde82bdf654"
                ),
            }
        )
        start_proc(
            "CONSOLE",
            ui_env,
            [str(py), str(REPO / "web/server.py")],
            DIAG / "console-8083.log",
            DIAG / "console-8083.pid",
        )
        if not wait_url("http://127.0.0.1:8083/api/status", 60):
            print((DIAG / "console-8083.log").read_text(encoding="utf-8", errors="replace")[-3000:])
            print("WARN: console :8083 not healthy yet")
    else:
        print("CONSOLE_SKIP_OR_HEALTHY")

    status = {
        "qwen_8002": healthy("http://127.0.0.1:8002/v1/models"),
        "gateway_8013": healthy("http://127.0.0.1:8013/health"),
        "console_8083": healthy("http://127.0.0.1:8083/api/status"),
        "gemma_8000": healthy("http://127.0.0.1:8000/v1/models"),
        "main_gateway_8010": healthy("http://127.0.0.1:8010/health"),
        "main_console_8080": healthy("http://127.0.0.1:8080/api/status"),
    }
    out = DIAG / "gateway-status.json"
    import json

    out.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2))
    print("Main services :8000/:8010/:8080 were not modified.")
    return 0 if status["gateway_8013"] and status["qwen_8002"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
