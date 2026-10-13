#!/usr/bin/env python3
"""One-shot Pod helper: normalize download script CRLF, verify shards, fix CUDA 13 libs."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEST = Path("/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654")
SRC = Path("/tmp/AI-PLAYBOOK/ops/download-qwen3.5-27b.sh")
OUT = Path("/tmp/download-qwen3.5-27b.sh")


def main() -> int:
    raw = SRC.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"")
    OUT.write_bytes(raw)
    OUT.chmod(0o755)
    print("normalized", OUT)

    shards = list(DEST.glob("model.safetensors-*-of-*.safetensors")) + list(
        DEST.glob("model-*.safetensors")
    )
    print("shard_count", len(shards))
    print("has_config", (DEST / "config.json").is_file())
    print("has_index", (DEST / "model.safetensors.index.json").is_file())
    if len(shards) < 11 or not (DEST / "config.json").is_file():
        print("DOWNLOAD_INCOMPLETE", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["PATH"] = "/tmp/hf-tools/bin:" + env.get("PATH", "")
    subprocess.run(
        ["bash", str(OUT), "--check"],
        check=False,
        env=env,
    )

    py = "/tmp/vllm-qwen-env/bin/python"
    print("Installing CUDA 13 runtime packages into qwen env...")
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "-p",
            py,
            "-q",
            "nvidia-cuda-runtime-cu13",
            "nvidia-cublas-cu13",
            "nvidia-cuda-nvrtc-cu13",
        ],
        check=False,
    )

    cudart = list(Path("/tmp/vllm-qwen-env").rglob("libcudart.so.13"))
    print("cudart_hits", [str(p) for p in cudart[:5]])
    if not cudart:
        print("NO_CUDART13", file=sys.stderr)
        return 3

    libdir = str(cudart[0].parent)
    env["LD_LIBRARY_PATH"] = libdir + ":" + env.get("LD_LIBRARY_PATH", "")
    # Also collect other nvidia lib dirs under the env
    extra = {
        str(p.parent)
        for p in Path("/tmp/vllm-qwen-env").rglob("lib*.so*")
        if "nvidia" in str(p).lower()
    }
    env["LD_LIBRARY_PATH"] = ":".join([libdir, *sorted(extra), env.get("LD_LIBRARY_PATH", "")])
    Path("/workspace/platform-diagnostics/qwen/ld_library_path.txt").write_text(
        env["LD_LIBRARY_PATH"], encoding="utf-8"
    )
    r = subprocess.run(
        [py, "-c", "import vllm; print('vllm', vllm.__version__)"],
        env=env,
        capture_output=True,
        text=True,
    )
    print(r.stdout)
    print(r.stderr, file=sys.stderr)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
