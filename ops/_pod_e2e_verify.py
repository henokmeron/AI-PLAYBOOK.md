#!/usr/bin/env python3
"""Post-bring-up E2E verification against the first-release stack."""
from __future__ import annotations

import base64
import json
import os
import traceback
import urllib.error
import urllib.request
from pathlib import Path

KEY = Path(os.environ.get("PLATFORM_API_KEY_FILE", "/tmp/platform-gateway.key")).read_text(encoding="utf-8").strip()
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
OUT = Path(os.environ.get("E2E_OUT", "/workspace/platform-diagnostics/complete/manual-e2e.json"))
# Defaults target the main stack; override to test an isolated stack on other ports.
GATEWAY_BASE = os.environ.get("E2E_GATEWAY_URL", "http://127.0.0.1:8010").rstrip("/")
CONSOLE_BASE = os.environ.get("E2E_CONSOLE_URL", "http://127.0.0.1:8080").rstrip("/")


def req(method: str, url: str, payload: dict | None = None, timeout: float = 180):
    data = None if payload is None else json.dumps(payload).encode()
    url = url.replace("http://127.0.0.1:8010", GATEWAY_BASE, 1).replace(
        "http://127.0.0.1:8080", CONSOLE_BASE, 1
    )
    headers = H if url.startswith(GATEWAY_BASE) else {}
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(body) if body else {}, None
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(err)
        except Exception:
            parsed = {"raw": err[:2000]}
        return e.code, parsed, str(e)
    except Exception as e:
        return 0, {}, f"{type(e).__name__}: {e}"


def main() -> int:
    results: dict = {}

    st, chat, err = req(
        "POST",
        "http://127.0.0.1:8010/v1/chat/completions",
        {
            "model": "qwen3.5-27b",
            "messages": [{"role": "user", "content": "Reply with exactly: PLATFORM_OK"}],
            "max_tokens": 32,
            "temperature": 0,
        },
    )
    content = (chat.get("choices") or [{}])[0].get("message", {}).get("content", "")
    results["chat"] = {
        "status": st,
        "content": content,
        "selection": chat.get("platform_selection"),
        "pass": st == 200 and "PLATFORM_OK" in (content or ""),
        "error": err,
    }

    st, models, err = req("GET", "http://127.0.0.1:8010/v1/platform/models")
    results["gateway_models"] = {
        "status": st,
        "default": models.get("default_model_id"),
        "count": len(models.get("models") or []),
        "ids": [m.get("id") for m in (models.get("models") or [])],
        "pass": st == 200
        and bool(models.get("models"))
        and (
            models.get("default_model_id") in {None, "qwen3.5-27b"}
            or any(
                m.get("id") == "qwen3.5-27b" and m.get("is_active_default")
                for m in (models.get("models") or [])
            )
        ),
        "error": err,
    }

    st, cmodels, err = req("GET", "http://127.0.0.1:8080/api/platform/models")
    results["console_models"] = {
        "status": st,
        "default": cmodels.get("default_model_id"),
        "pass": st == 200 and bool(cmodels.get("models")),
        "error": err,
        "snippet": {k: cmodels.get(k) for k in ("default_model_id", "selected_model_id", "runtime_model_id")},
    }

    st, status, err = req("GET", "http://127.0.0.1:8080/api/status")
    results["console_status"] = {
        "status": st,
        "connection": status.get("connection"),
        "pass": st == 200 and status.get("connection") == "ready",
        "error": err,
    }

    # Picker path: chat with Gemma while Qwen is the live upstream must 409.
    st, sel, err = req(
        "POST",
        "http://127.0.0.1:8010/v1/chat/completions",
        {
            "model": "gemma-4-31b-it",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 8,
        },
    )
    results["select_gemma_while_qwen"] = {
        "status": st,
        "body": {k: sel.get(k) for k in ("error", "selection", "detail")}
        if isinstance(sel, dict)
        else sel,
        "pass": st == 409,
        "error": err,
    }

    coll = "manual-e2e-check"
    doc = b"The durable release keyword is CEDAR-RIVER-42 for verification only.\n"
    st, up, err = req(
        "POST",
        "http://127.0.0.1:8010/v1/rag/documents",
        {
            "collection": coll,
            "filename": "release-note.txt",
            "content_base64": base64.b64encode(doc).decode(),
            "overwrite": True,
        },
    )
    results["rag_upload"] = {"status": st, "body": up, "pass": st in (200, 201), "error": err}

    st, ask, err = req(
        "POST",
        "http://127.0.0.1:8010/v1/rag/ask",
        {
            "collection": coll,
            "question": "What is the durable release keyword?",
            "top_k": 4,
        },
    )
    answer = ask.get("answer") or ""
    results["rag_ask"] = {
        "status": st,
        "answer": answer[:400],
        "pass": st == 200 and "CEDAR-RIVER-42" in answer,
        "error": err,
        "citations": ask.get("citations") or ask.get("sources"),
    }

    st, delete, err = req(
        "DELETE",
        f"http://127.0.0.1:8010/v1/rag/documents?collection={coll}&filename=release-note.txt",
    )
    results["rag_delete"] = {
        "status": st,
        "body": delete,
        "pass": st == 200,
        "error": err,
    }

    st, follow, err = req(
        "POST",
        "http://127.0.0.1:8010/v1/rag/ask",
        {
            "collection": coll,
            "question": "What is the durable release keyword?",
            "top_k": 4,
            "history": [
                {"role": "user", "content": "What is the durable release keyword?"},
                {"role": "assistant", "content": answer},
            ],
        },
    )
    follow_ans = follow.get("answer") or ""
    results["rag_follow_after_delete"] = {
        "status": st,
        "answer": follow_ans[:400],
        "body": follow if st != 200 else {k: follow.get(k) for k in ("answer", "status", "error")},
        "pass": st == 200
        and ("CEDAR-RIVER-42" not in follow_ans or follow.get("status") == "abstained"),
        "error": err,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    fails = [k for k, v in results.items() if isinstance(v, dict) and not v.get("pass")]
    print("FAILS:", fails if fails else "NONE")
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
