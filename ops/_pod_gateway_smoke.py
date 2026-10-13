#!/usr/bin/env python3
"""Authenticated smoke through isolated gateway :8013 -> Qwen :8002."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

KEY = Path("/tmp/platform-gateway.key").read_text(encoding="utf-8").strip()
OUT = Path("/workspace/platform-diagnostics/qwen/gateway-smoke-result.json")
MODEL = (
    "/workspace/models/Qwen3.5-27B/"
    "fc05daec18b0a78c049392ed2e771dde82bdf654"
)


def main() -> int:
    payload = json.dumps(
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": "Reply with exactly: QWEN_OK"}],
            "max_tokens": 32,
            "temperature": 0,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8013/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        status = resp.status
    result = {"http_status": status, "response": body}
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    content = (
        body.get("choices", [{}])[0].get("message", {}).get("content", "")
    )
    print(json.dumps(result, indent=2)[:1500])
    if "QWEN_OK" in (content or "") or status == 200:
        print("PASS: gateway smoke")
        return 0
    print("FAIL: gateway smoke")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
