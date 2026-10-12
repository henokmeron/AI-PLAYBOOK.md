#!/usr/bin/env python3
"""Small live API smoke test for the existing loopback gateway.

Reads the bearer key from a file without printing it. This checks the running
service; it does not claim broad RAG quality or production readiness.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

GATEWAY = os.environ.get("PLATFORM_GATEWAY_URL", "http://127.0.0.1:8010").rstrip("/")
KEY_FILE = Path(os.environ.get("PLATFORM_API_KEY_FILE", "/tmp/platform-gateway.key"))
VLLM = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")


def request(url: str, payload: dict | None = None, key: str | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=data, headers=headers, method="GET" if payload is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {"body": raw[:500].decode("utf-8", "replace")}
        return exc.code, body


def main() -> int:
    if not KEY_FILE.is_file():
        print(f"FAIL: key file missing: {KEY_FILE}", file=sys.stderr)
        return 2
    key = KEY_FILE.read_text(encoding="utf-8").strip()
    if len(key) < 32:
        print("FAIL: gateway key is missing or unexpectedly short", file=sys.stderr)
        return 2

    failures = 0

    status, health = request(f"{GATEWAY}/health")
    ok = status == 200 and health.get("status") == "ok" and health.get("upstream") == "ok"
    print(f"[{'PASS' if ok else 'FAIL'}] gateway health: HTTP {status}, status={health.get('status')}, upstream={health.get('upstream')}")
    failures += not ok

    status, models = request(f"{VLLM}/models")
    model_rows = models.get("data", []) if isinstance(models, dict) else []
    model_id = model_rows[0].get("id") if model_rows else None
    ok = status == 200 and bool(model_id)
    print(f"[{'PASS' if ok else 'FAIL'}] model API: HTTP {status}, model_discovered={bool(model_id)}")
    failures += not ok

    status, unauth = request(f"{GATEWAY}/v1/rag/ask", {"question": "How many business days do employees have to submit expense receipts?", "top_k": 4})
    ok = status == 401
    print(f"[{'PASS' if ok else 'FAIL'}] unauthenticated RAG is rejected: HTTP {status}")
    failures += not ok

    status, rag = request(f"{GATEWAY}/v1/rag/ask", {
        "question": "How many business days do employees have to submit expense receipts?",
        "top_k": 4,
    }, key)
    answer = str(rag.get("answer", ""))
    sources = rag.get("sources", [])
    source_files = [str(row.get("file", "")) for row in sources if isinstance(row, dict)]
    ok = (
        status == 200
        and rag.get("status") == "answered"
        and "10 business days" in answer.casefold()
        and "expenses-policy.md" in source_files
    )
    print(f"[{'PASS' if ok else 'FAIL'}] answerable RAG: HTTP {status}, status={rag.get('status')}, expected_phrase={'10 business days' in answer.casefold()}, correct_source={'expenses-policy.md' in source_files}")
    if not ok:
        print("  Returned status/answer/source files:", rag.get("status"), answer[:300], source_files)
    failures += not ok

    status, no_answer = request(f"{GATEWAY}/v1/rag/ask", {
        "question": "What colour is the CEO's private yacht?",
        "top_k": 4,
    }, key)
    ok = status == 200 and no_answer.get("status") == "abstained" and no_answer.get("sources") == []
    print(f"[{'PASS' if ok else 'FAIL'}] unanswerable RAG abstains: HTTP {status}, status={no_answer.get('status')}, no_sources={no_answer.get('sources') == []}")
    if not ok:
        print("  Returned status:", no_answer.get("status"), "retrieval:", no_answer.get("retrieval"))
    failures += not ok

    if model_id:
        status, chat = request(f"{GATEWAY}/v1/chat/completions", {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with exactly: gateway works"}],
            "temperature": 0,
            "max_tokens": 12,
        }, key)
        choices = chat.get("choices", [])
        answer = str(choices[0].get("message", {}).get("content", "")) if choices else ""
        ok = status == 200 and "gateway works" in answer.casefold()
        print(f"[{'PASS' if ok else 'FAIL'}] authenticated chat: HTTP {status}, expected_phrase={'gateway works' in answer.casefold()}")
        if not ok:
            print("  Returned answer:", answer[:300])
        failures += not ok

    print(f"\nResult: {'PASS' if failures == 0 else 'FAIL'} ({failures} failed checks)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
