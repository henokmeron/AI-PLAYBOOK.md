#!/usr/bin/env python3
"""Small, dependency-free baseline evaluation for an OpenAI-compatible vLLM API.

Defaults to localhost:8000. This does not modify the server or its configuration.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE_URL = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
MODEL_OVERRIDE = os.environ.get("VLLM_MODEL_ID")
TIMEOUT_SECONDS = int(os.environ.get("VLLM_EVAL_TIMEOUT", "120"))


def request_json(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail[:1000]}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not reach {url}: {exc}") from exc
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Endpoint did not return valid JSON: {url}") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"Expected a JSON object from {url}")
    return result


def chat(model: str, prompt: str, max_tokens: int = 64) -> tuple[str, float]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Follow the user's instructions carefully. Do not add extra text when exact output is requested."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    started = time.perf_counter()
    result = request_json(f"{BASE_URL}/chat/completions", payload)
    elapsed = time.perf_counter() - started
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"Chat API response has no choices: {json.dumps(result)[:1000]}")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not isinstance(content, str):
        raise RuntimeError(f"Expected text response, got: {type(content).__name__}")
    return content.strip(), elapsed


def main() -> int:
    print("=== Gemma / vLLM baseline evaluation ===")
    print(f"API: {BASE_URL}")
    try:
        models = request_json(f"{BASE_URL}/models").get("data", [])
        if not isinstance(models, list) or not models:
            raise RuntimeError("GET /models returned no model entries")
        available_ids = [entry.get("id") for entry in models if isinstance(entry, dict) and entry.get("id")]
        if not available_ids:
            raise RuntimeError("GET /models did not include a model ID")
        model = MODEL_OVERRIDE or available_ids[0]
        print(f"Model: {model}")

        cases = [
            {
                "name": "instruction following",
                "prompt": "Reply with exactly this one word and nothing else: PASS",
                "check": lambda s: s.strip() == "PASS",
                "expect": "exactly PASS",
            },
            {
                "name": "basic arithmetic",
                "prompt": "Calculate 17 times 19. Reply with digits only, no words or punctuation.",
                "check": lambda s: re.fullmatch(r"\s*323\s*", s) is not None,
                "expect": "323 only",
            },
            {
                "name": "use supplied information",
                "prompt": "Use only this note: The office opens at 09:30 on Tuesday. What time does it open on Tuesday? Reply exactly: 09:30",
                "check": lambda s: s.strip() == "09:30",
                "expect": "exactly 09:30",
            },
            {
                "name": "structured JSON",
                "prompt": 'Return only a valid JSON object with exactly these values: {"status":"ok","count":3}. No markdown or explanation.',
                "check": lambda s: _is_expected_json(s),
                "expect": 'JSON {"status":"ok","count":3}',
            },
        ]

        results: list[bool] = []
        for case in cases:
            try:
                output, elapsed = chat(model, case["prompt"])
                passed = bool(case["check"](output))
                results.append(passed)
                print(f"\n[{'PASS' if passed else 'FAIL'}] {case['name']} ({elapsed:.2f}s; expected {case['expect']})")
                print(f"  Output: {output[:500]!r}")
            except Exception as exc:
                results.append(False)
                print(f"\n[FAIL] {case['name']}: {exc}")

        passed_count = sum(results)
        total = len(results)
        print(f"\nRESULT: {passed_count}/{total} checks passed")
        print("Note: this is a small smoke/baseline suite, not proof of broad model quality or regulatory compliance.")
        return 0 if passed_count == total else 1
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2


def _is_expected_json(value: str) -> bool:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return False
    return parsed == {"status": "ok", "count": 3}


if __name__ == "__main__":
    raise SystemExit(main())
