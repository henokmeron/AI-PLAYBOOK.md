#!/usr/bin/env python3
"""Final mission baseline inspect — read-only."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

OUT = Path("/workspace/platform-diagnostics/final-mission/inspect.json")


def sh(cmd: str) -> str:
    try:
        return subprocess.check_output(
            cmd, shell=True, text=True, stderr=subprocess.STDOUT
        ).strip()
    except subprocess.CalledProcessError as exc:
        return f"ERR:{exc.returncode}:{exc.output.strip()[:400]}"


def http(url: str):
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return {"up": True, "status": resp.status}
    except Exception as exc:  # noqa: BLE001
        return {"up": False, "error": type(exc).__name__}


def main() -> int:
    out = {
        "mount": sh("findmnt -n -o SOURCE,FSTYPE,TARGET /workspace"),
        "nvidia": sh(
            "nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu "
            "--format=csv,noheader"
        ),
        "df_tmp": sh("df -h /tmp | tail -1"),
        "df_root": sh("df -h / | tail -1"),
        "ports": {
            k: http(u)
            for k, u in {
                "8000": "http://127.0.0.1:8000/v1/models",
                "8002": "http://127.0.0.1:8002/v1/models",
                "8010": "http://127.0.0.1:8010/health",
                "8013": "http://127.0.0.1:8013/health",
                "8080": "http://127.0.0.1:8080/api/status",
                "8083": "http://127.0.0.1:8083/api/status",
            }.items()
        },
        "envs": {
            "qwen": Path("/tmp/vllm-qwen-env/bin/vllm").is_file(),
            "gemma": Path("/tmp/vllm-clean-env/bin/vllm").is_file(),
        },
        "models": {
            "gemma_config": Path(
                "/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it/config.json"
            ).is_file(),
            "qwen_config": Path(
                "/workspace/models/Qwen3.5-27B/"
                "fc05daec18b0a78c049392ed2e771dde82bdf654/config.json"
            ).is_file(),
        },
        "archives": {
            "gemma_sha": sh(
                "cd /workspace/runtime-setup && "
                "grep vllm-clean-env.tar.zst SHA256SUMS | sha256sum -c - 2>&1"
            ),
            "qwen_sha": sh(
                "cd /workspace/runtime-setup/qwen-vllm && sha256sum -c SHA256SUMS 2>&1"
            ),
            "qwen_archive": Path(
                "/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst"
            ).is_file(),
        },
        "snapshots": {
            "128bc97": Path(
                "/workspace/ai-platform-backups/source-snapshots/"
                "AI-PLAYBOOK.md-128bc97aaa4c5168550bd06a3ad937f2aeb7b509.tar.gz"
            ).is_file(),
            "7072cab": Path(
                "/workspace/ai-platform-backups/source-snapshots/"
                "AI-PLAYBOOK.md-7072cab31b93e5c27abffb2e14a96a1b67e685a1.tar.gz"
            ).is_file(),
            "head": sh(
                "ls -1t /workspace/ai-platform-backups/source-snapshots | head -6"
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
