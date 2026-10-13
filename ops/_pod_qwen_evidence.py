#!/usr/bin/env python3
"""Collect durable Qwen stack evidence under platform-diagnostics."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

DIAG = Path("/workspace/platform-diagnostics/qwen")
MODEL = Path(
    "/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654"
)
OUT = DIAG / "live-stack-evidence.json"


def http_code(url: str) -> int:
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=5) as resp:
            return int(resp.status)
    except Exception:  # noqa: BLE001
        return 0


def main() -> int:
    shards = sorted(MODEL.glob("model.safetensors-*-of-*.safetensors"))
    legacy = sorted(MODEL.glob("model-*.safetensors"))
    snap_dir = Path("/workspace/ai-platform-backups/source-snapshots")
    snaps = sorted(p.name for p in snap_dir.glob("*.tar.gz")) if snap_dir.is_dir() else []
    pid_text = (DIAG / "qwen-vllm.pid").read_text().strip() if (DIAG / "qwen-vllm.pid").is_file() else ""
    ps = ""
    if pid_text.isdigit():
        r = subprocess.run(
            ["ps", "-p", pid_text, "-o", "pid,etime,cmd", "--no-headers"],
            capture_output=True,
            text=True,
        )
        ps = r.stdout.strip()
    smoke = {}
    smoke_path = DIAG / "smoke-result.json"
    if smoke_path.is_file():
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    gw_smoke = {}
    gw_path = DIAG / "gateway-smoke-result.json"
    if gw_path.is_file():
        gw_smoke = json.loads(gw_path.read_text(encoding="utf-8"))
    evidence = {
        "model_path": str(MODEL),
        "shard_count_new_layout": len(shards),
        "shard_count_legacy_layout": len(legacy),
        "config_present": (MODEL / "config.json").is_file(),
        "index_present": (MODEL / "model.safetensors.index.json").is_file(),
        "manifest_present": Path(
            "/workspace/models/Qwen3.5-27B/manifests/"
            "fc05daec18b0a78c049392ed2e771dde82bdf654.sha256sums"
        ).is_file(),
        "ports": {
            "qwen_8002": http_code("http://127.0.0.1:8002/v1/models"),
            "gateway_8013": http_code("http://127.0.0.1:8013/health"),
            "console_8083": http_code("http://127.0.0.1:8083/api/status"),
            "gemma_8000": http_code("http://127.0.0.1:8000/v1/models"),
            "main_gateway_8010": http_code("http://127.0.0.1:8010/health"),
            "main_console_8080": http_code("http://127.0.0.1:8080/api/status"),
        },
        "qwen_pid": pid_text,
        "qwen_ps": ps,
        "smoke_http_status": smoke.get("http_status"),
        "smoke_content": (
            smoke.get("response", {})
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        ),
        "gateway_smoke_http_status": gw_smoke.get("http_status"),
        "gateway_smoke_content": (
            gw_smoke.get("response", {})
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        ),
        "source_snapshots_tail": snaps[-5:],
        "notes": [
            "Qwen served isolated on :8002; gateway :8013; console :8083.",
            "Production default remains Gemma; ports :8010/:8080 not started by this stack.",
            "Global Volume remains attached at /workspace; pod not destroyed.",
        ],
    }
    OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
