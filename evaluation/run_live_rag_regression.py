#!/usr/bin/env python3
"""Bounded live RAG regression for the fictional demo corpus; prints no secrets."""
import json, os, sys, urllib.request, urllib.error
from pathlib import Path

BASE = os.environ.get("PLATFORM_GATEWAY_URL", "http://127.0.0.1:8010").rstrip("/")
KEYFILE = Path(os.environ.get("PLATFORM_API_KEY_FILE", "/tmp/platform-gateway.key"))
CASES = [
    ("P1", "By what deadline must staff turn in receipts for expenses?", "answered", "10 business days", "expenses-policy.md"),
    ("P2", "Who signs off an expense claim over 100 pounds?", "answered", "manager", "expenses-policy.md"),
    ("P3", "What type of train ticket should employees choose?", "answered", "standard", "expenses-policy.md"),
    ("P4", "What are the office hours from Monday to Friday?", "answered", "09:00", "employee-handbook.md"),
    ("N1", "What colour is the CEO's yacht?", "abstained", None, None),
    ("N2", "What is the company's VAT registration number?", "abstained", None, None),
]

def main():
    if not KEYFILE.is_file():
        print("FAIL: gateway key file is missing", file=sys.stderr); return 2
    key = KEYFILE.read_text(encoding="utf-8").strip()
    if len(key) < 32:
        print("FAIL: gateway key file is invalid", file=sys.stderr); return 2
    passed = 0
    for cid, question, expected_status, phrase, source in CASES:
        req = urllib.request.Request(
            BASE + "/v1/rag/ask",
            data=json.dumps({"question": question, "top_k": 4}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                status, body = resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            status, body = exc.code, {}
        except Exception as exc:
            print("[FAIL] %s request error: %s" % (cid, type(exc).__name__)); continue
        answer = str(body.get("answer", "")).casefold()
        sources = body.get("sources", [])
        filenames = [str(s.get("file", "")) for s in sources if isinstance(s, dict)]
        ok = status == 200 and body.get("status") == expected_status
        if phrase:
            ok = ok and phrase.casefold() in answer
        if source:
            ok = ok and source in filenames
        if expected_status == "abstained":
            ok = ok and not sources
        passed += int(ok)
        print("[%s] %s: HTTP %s status=%s phrase=%s source=%s no_sources=%s" % (
            "PASS" if ok else "FAIL", cid, status, body.get("status"),
            phrase is None or phrase.casefold() in answer,
            source is None or source in filenames, not sources))
    print("\nLive RAG regression: %d/%d passed. Small fictional demo only; not a production-quality estimate." % (passed, len(CASES)))
    return 0 if passed == len(CASES) else 1

if __name__ == "__main__":
    raise SystemExit(main())
