#!/usr/bin/env python3
"""Fix qwen archive version stamp and re-verify SHA256SUMS. Check Qwen still up."""
from __future__ import annotations

import importlib.metadata
import json
import subprocess
import urllib.request
from pathlib import Path

DEST = Path("/workspace/runtime-setup/qwen-vllm")


def main() -> int:
    # Prefer metadata version without importing CUDA-heavy vllm CLI.
    ver = importlib.metadata.version("vllm") if False else None
    try:
        # Use the qwen env's python
        out = subprocess.check_output(
            [
                "/tmp/vllm-qwen-env/bin/python",
                "-c",
                "import importlib.metadata as m; print(m.version('vllm'))",
            ],
            text=True,
            env={
                **dict(**{k: v for k, v in __import__("os").environ.items()}),
            },
        ).strip()
        ver = out
    except Exception as exc:  # noqa: BLE001
        ver = f"unknown ({type(exc).__name__})"
    (DEST / "vllm-version.txt").write_text(ver + "\n", encoding="utf-8")
    files = [
        "vllm-qwen-env.tar.zst",
        "requirements-frozen.txt",
        "runtime-manifest.txt",
        "vllm-version.txt",
    ]
    lines = []
    for name in files:
        digest = subprocess.check_output(
            ["sha256sum", str(DEST / name)], text=True
        ).split()[0]
        lines.append(f"{digest}  {name}")
    (DEST / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    check = subprocess.check_output(
        ["sha256sum", "-c", "SHA256SUMS"], cwd=DEST, text=True
    )
    qwen_up = False
    try:
        with urllib.request.urlopen("http://127.0.0.1:8002/v1/models", timeout=3) as r:
            qwen_up = r.status == 200
    except Exception:
        qwen_up = False
    print(
        json.dumps(
            {
                "vllm_version": ver,
                "sha256_check": check.strip().splitlines(),
                "archive_size": subprocess.check_output(
                    ["du", "-sh", str(DEST / "vllm-qwen-env.tar.zst")], text=True
                ).strip(),
                "qwen_8002_up": qwen_up,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
