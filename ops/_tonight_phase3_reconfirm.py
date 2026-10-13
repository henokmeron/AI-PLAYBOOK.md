#!/usr/bin/env python3
"""Phase 3: reconfirm Qwen live without restarting a healthy vLLM."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

OUT = Path("/workspace/platform-diagnostics/tonight/phase3-reconfirm.json")
KEY = Path("/tmp/platform-gateway.key")
MODEL = (
    "/workspace/models/Qwen3.5-27B/"
    "fc05daec18b0a78c049392ed2e771dde82bdf654"
)


def post(url: str, payload: dict, headers: dict | None = None, timeout: float = 180):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def get(url: str, headers: dict | None = None, timeout: float = 10):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main() -> int:
    out: dict = {}
    st, models = get("http://127.0.0.1:8002/v1/models")
    out["vllm_models_status"] = st
    out["vllm_model_ids"] = [
        item.get("id") for item in models.get("data", []) if isinstance(item, dict)
    ]
    st2, chat = post(
        "http://127.0.0.1:8002/v1/chat/completions",
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": "Reply with exactly: QWEN_OK"}],
            "max_tokens": 32,
            "temperature": 0,
        },
    )
    content = (
        chat.get("choices", [{}])[0].get("message", {}).get("content", "")
    )
    out["direct_chat"] = {"status": st2, "content": content}
    if KEY.is_file():
        key = KEY.read_text(encoding="utf-8").strip()
        headers = {"Authorization": f"Bearer {key}"}
        try:
            gst, gchat = post(
                "http://127.0.0.1:8013/v1/chat/completions",
                {
                    "model": "qwen3.5-27b",
                    "messages": [
                        {"role": "user", "content": "Reply with exactly: QWEN_OK"}
                    ],
                    "max_tokens": 32,
                    "temperature": 0,
                },
                headers=headers,
            )
            gcontent = (
                gchat.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            out["gateway_chat"] = {
                "status": gst,
                "content": gcontent,
                "platform_selection": gchat.get("platform_selection"),
            }
        except Exception as exc:  # noqa: BLE001
            out["gateway_chat"] = {"error": f"{type(exc).__name__}: {exc}"}
        try:
            pst, catalog = get(
                "http://127.0.0.1:8013/v1/platform/models", headers=headers
            )
            out["platform_models"] = {"status": pst, "body": catalog}
        except Exception as exc:  # noqa: BLE001
            out["platform_models"] = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        out["gateway_chat"] = {"error": "missing /tmp/platform-gateway.key"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2)[:4000])
    ok = "QWEN_OK" in (out.get("direct_chat", {}).get("content") or "")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
