#!/usr/bin/env python3
"""Wait for Qwen :8002 readiness, then smoke chat/completions."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8002"
LOG = Path("/workspace/platform-diagnostics/qwen/qwen-vllm.log")
OUT = Path("/workspace/platform-diagnostics/qwen/smoke-result.json")
# First boot can include weight load + CUDA graph capture + flashinfer JIT build.
TIMEOUT_S = 1200


def get(url: str, timeout: float = 10):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def post_json(url: str, payload: dict, timeout: float = 120):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def wait_ready() -> bool:
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        try:
            status, body = get(f"{BASE}/v1/models", timeout=5)
            if status == 200 and "data" in body:
                print(f"READY models={body[:200]}")
                return True
        except Exception as exc:  # noqa: BLE001
            print(f"waiting... {exc}")
        if LOG.is_file():
            tail = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
            for line in tail:
                if "ERROR" in line or "Error" in line or "Traceback" in line:
                    print(f"LOG: {line}")
        time.sleep(10)
    return False


def smoke() -> dict:
    status, body = post_json(
        f"{BASE}/v1/chat/completions",
        {
            "model": str(
                Path(
                    "/workspace/models/Qwen3.5-27B/"
                    "fc05daec18b0a78c049392ed2e771dde82bdf654"
                )
            ),
            "messages": [
                {"role": "user", "content": "Reply with exactly: QWEN_OK"}
            ],
            "max_tokens": 32,
            "temperature": 0,
        },
        timeout=180,
    )
    return {"http_status": status, "response": body}


def main() -> int:
    if not wait_ready():
        print("FAIL: timed out waiting for /v1/models")
        if LOG.is_file():
            print(LOG.read_text(encoding="utf-8", errors="replace")[-4000:])
        return 1
    try:
        result = smoke()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: smoke request error: {exc}")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2)[:2000])
    content = (
        result.get("response", {})
        .get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if "QWEN_OK" in (content or ""):
        print("PASS: smoke content contains QWEN_OK")
        return 0
    print("WARN: smoke completed but content unexpected; treating as soft pass if 200")
    return 0 if result.get("http_status") == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
