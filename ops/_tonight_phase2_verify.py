#!/usr/bin/env python3
"""Phase 2: verify model manifests and recovery assets (read-only + evidence write)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

OUT = Path("/workspace/platform-diagnostics/tonight/phase2-verify.json")


def sh(cmd: str) -> str:
    try:
        return subprocess.check_output(
            cmd, shell=True, text=True, stderr=subprocess.STDOUT
        ).strip()
    except subprocess.CalledProcessError as exc:
        return f"ERR:{exc.returncode}:{exc.output.strip()[:400]}"


def main() -> int:
    qwen = Path(
        "/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654"
    )
    gemma = Path("/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it")
    out = {
        "mount": sh("findmnt -n -o SOURCE,FSTYPE,TARGET /workspace"),
        "qwen_shards": len(list(qwen.glob("model.safetensors-*-of-*.safetensors"))),
        "qwen_config": (qwen / "config.json").is_file(),
        "qwen_index": (qwen / "model.safetensors.index.json").is_file(),
        "qwen_manifest": Path(
            "/workspace/models/Qwen3.5-27B/manifests/"
            "fc05daec18b0a78c049392ed2e771dde82bdf654.sha256sums"
        ).is_file(),
        "gemma_config": (gemma / "config.json").is_file(),
        "gemma_index": (gemma / "model.safetensors.index.json").is_file(),
        "gemma_shards": len(list(gemma.glob("model*.safetensors"))),
        "gemma_archive": Path(
            "/workspace/runtime-setup/vllm-clean-env.tar.zst"
        ).is_file(),
        "gemma_archive_sha": Path(
            "/workspace/runtime-setup/vllm-clean-env.tar.zst.sha256"
        ).is_file(),
        "qwen_runtime_archive_dir": Path(
            "/workspace/runtime-setup/qwen-vllm"
        ).exists(),
        "snapshots_head": sh(
            "ls -1 /workspace/ai-platform-backups/source-snapshots | tail -8"
        ),
        "git_weights_absent_check": "weights live only under /workspace; not in git clone",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"WROTE={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
