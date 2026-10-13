#!/usr/bin/env python3
"""Read-only post-acceptance inspection: services, GPU, archives, snapshots."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

OUT = Path("/workspace/platform-diagnostics/tonight/post-acceptance-inspect.json")


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


def main() -> int:
    gemma_archive = Path("/workspace/runtime-setup/vllm-clean-env.tar.zst")
    sha_sums = Path("/workspace/runtime-setup/SHA256SUMS")
    out = {
        "mount": sh("findmnt -n -o SOURCE,FSTYPE,TARGET /workspace"),
        "nvidia": sh(
            "nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu "
            "--format=csv,noheader"
        ),
        "df_workspace": sh("df -h /workspace | tail -1"),
        "df_tmp": sh("df -h /tmp | tail -1"),
        "ports": {
            "8000": http("http://127.0.0.1:8000/v1/models"),
            "8002": http("http://127.0.0.1:8002/v1/models"),
            "8010": http("http://127.0.0.1:8010/health"),
            "8013": http("http://127.0.0.1:8013/health"),
            "8080": http("http://127.0.0.1:8080/api/status"),
            "8083": http("http://127.0.0.1:8083/api/status"),
        },
        "envs": {
            "qwen_venv": Path("/tmp/vllm-qwen-env/bin/vllm").is_file(),
            "gemma_venv": Path("/tmp/vllm-clean-env/bin/vllm").is_file(),
            "qwen_venv_du": sh("du -sh /tmp/vllm-qwen-env 2>/dev/null || true"),
            "gemma_venv_du": sh("du -sh /tmp/vllm-clean-env 2>/dev/null || true"),
        },
        "models_present": {
            "gemma_config": Path(
                "/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it/config.json"
            ).is_file(),
            "qwen_config": Path(
                "/workspace/models/Qwen3.5-27B/"
                "fc05daec18b0a78c049392ed2e771dde82bdf654/config.json"
            ).is_file(),
        },
        "archives": {
            "gemma_tar_exists": gemma_archive.is_file(),
            "gemma_tar_size": sh(f"du -sh {gemma_archive} 2>/dev/null || true"),
            "gemma_zstd_t": sh(f"zstd -t {gemma_archive} 2>&1 || true"),
            "sha256sums_exists": sha_sums.is_file(),
            "sha256sums_head": sh(f"head -n 20 {sha_sums} 2>/dev/null || true"),
            "sha256_check_gemma": sh(
                f"cd /workspace/runtime-setup && "
                f"grep 'vllm-clean-env.tar.zst' SHA256SUMS | sha256sum -c - 2>&1 || true"
            ),
            "qwen_runtime_dir": Path("/workspace/runtime-setup/qwen-vllm").exists(),
            "qwen_runtime_listing": sh(
                "ls -la /workspace/runtime-setup/qwen-vllm 2>/dev/null || echo ABSENT"
            ),
        },
        "snapshots": {
            "7072cab": Path(
                "/workspace/ai-platform-backups/source-snapshots/"
                "AI-PLAYBOOK.md-7072cab31b93e5c27abffb2e14a96a1b67e685a1.tar.gz"
            ).is_file(),
            "534a891": Path(
                "/workspace/ai-platform-backups/source-snapshots/"
                "AI-PLAYBOOK.md-534a891d2c3220d99e057ea614ac86d251407db0.tar.gz"
            ).is_file(),
            "latest": sh(
                "ls -1t /workspace/ai-platform-backups/source-snapshots | head -5"
            ),
        },
        "recovery_scripts_on_volume_or_tmp": {
            "restore_script_repo": Path(
                "/tmp/AI-PLAYBOOK/scripts/restore-vllm-environment.sh"
            ).is_file(),
            "start_platform": Path("/tmp/AI-PLAYBOOK/ops/start-platform.sh").is_file(),
            "preflight": Path("/tmp/AI-PLAYBOOK/ops/preflight-recovery.sh").is_file(),
            "switch_gpu": Path("/tmp/AI-PLAYBOOK/ops/switch-gpu-model.sh").is_file(),
        },
        "tmp_free_gb_approx": sh(
            "df -BG /tmp | awk 'NR==2 {print $4}'"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"WROTE={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
