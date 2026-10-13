#!/usr/bin/env python3
"""Phase 1 live state probe — read-only."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path


def sh(cmd: str) -> str:
    try:
        return subprocess.check_output(
            cmd, shell=True, text=True, stderr=subprocess.STDOUT
        ).strip()
    except subprocess.CalledProcessError as exc:
        return f"ERR:{exc.returncode}:{exc.output.strip()[:500]}"


def http(url: str):
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return {"up": True, "status": resp.status}
    except Exception as exc:  # noqa: BLE001
        return {"up": False, "error": type(exc).__name__}


def model_info(path: str) -> dict:
    p = Path(path)
    info: dict = {"path": path, "exists": p.is_dir()}
    if not p.is_dir():
        return info
    info["config"] = (p / "config.json").is_file()
    info["index"] = (p / "model.safetensors.index.json").is_file()
    shards = list(p.glob("model*.safetensors"))
    info["shard_count"] = len(shards)
    info["du_h"] = sh(f"du -sh {path} | cut -f1")
    return info


def main() -> int:
    out = {
        "hostname": sh("hostname"),
        "df_workspace": sh("df -h /workspace | tail -1"),
        "df_root": sh("df -h / | tail -1"),
        "df_tmp": sh("df -h /tmp | tail -1"),
        "mount_workspace": sh("findmnt -n -o SOURCE,FSTYPE,TARGET /workspace"),
        "nvidia": sh(
            "nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu "
            "--format=csv,noheader"
        ),
        "free_ram": sh("free -h | awk '/Mem:/ {print}'"),
        "gemma": model_info(
            "/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it"
        ),
        "qwen": model_info(
            "/workspace/models/Qwen3.5-27B/"
            "fc05daec18b0a78c049392ed2e771dde82bdf654"
        ),
        "ports": {
            "qwen_8002": http("http://127.0.0.1:8002/v1/models"),
            "qwen_gw_8013": http("http://127.0.0.1:8013/health"),
            "qwen_ui_8083": http("http://127.0.0.1:8083/api/status"),
            "gemma_8000": http("http://127.0.0.1:8000/v1/models"),
            "main_gw_8010": http("http://127.0.0.1:8010/health"),
            "main_ui_8080": http("http://127.0.0.1:8080/api/status"),
            "test_gw_8012": http("http://127.0.0.1:8012/health"),
            "test_ui_8082": http("http://127.0.0.1:8082/api/status"),
        },
        "venv_qwen": Path("/tmp/vllm-qwen-env/bin/vllm").is_file(),
        "venv_gemma": Path("/tmp/vllm-clean-env/bin/vllm").is_file(),
        "snapshots": sh(
            "ls -1dt /workspace/ai-platform-backups/source-snapshots/* 2>/dev/null | head -5"
        ),
    }
    Path("/workspace/platform-diagnostics/tonight").mkdir(parents=True, exist_ok=True)
    dest = Path("/workspace/platform-diagnostics/tonight/phase1-state.json")
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"WROTE={dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
