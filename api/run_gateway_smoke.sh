#!/usr/bin/env bash
# Fresh local deployment and smoke test for the loopback-only chat + RAG gateway.
# This does not install packages or stop the vLLM model server.
set -euo pipefail
API_BASE=https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/api
RAG_BASE=https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/rag
PYTHON=/tmp/vllm-clean-env/bin/python
GATEWAY_FILE=/tmp/platform_gateway.py
ENGINE_FILE=/tmp/rag_engine.py
LOADER_FILE=/tmp/document_loaders.py
LIBRARY_FILE=/tmp/document_library.py
LOG_FILE=/tmp/platform-gateway.log
PID_FILE=/tmp/platform-gateway.pid
KEY_FILE=/tmp/platform-gateway.key
DOCS=/workspace/rag-demo-docs
URL=http://127.0.0.1:8010
RAG_DEPS=/tmp/rag-deps
MODEL=/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: expected working Python at $PYTHON; do not reinstall automatically." >&2
  exit 2
fi
if [[ ! -d "$DOCS" ]]; then
  echo "ERROR: demo documents not found at $DOCS; fetch the sample documents using rag/README.md first." >&2
  exit 3
fi
if ! PYTHONPATH="$RAG_DEPS" "$PYTHON" -c 'import importlib.metadata as m, pypdf, openpyxl, et_xmlfile, defusedxml; assert m.version("pypdf")=="6.20.0"; assert m.version("openpyxl")=="3.1.5"; assert m.version("et-xmlfile")=="2.0.0"; assert m.version("defusedxml")=="0.7.1"; print("Verified PDF/XLSX parser versions")'; then
  echo "ERROR: PDF/XLSX dependencies missing or wrong. Run rag/setup_pdf_support.sh and rag/setup_xlsx_support.sh first." >&2
  exit 4
fi
if curl -fsS "$URL/health" >/dev/null 2>&1; then
  echo "ERROR: a gateway already responds at $URL. Reuse it or use the guarded upgrade script; do not start a competing process." >&2
  exit 4
fi

echo "=== DOWNLOAD AND CHECK GATEWAY COMPONENTS ==="
curl -fsSL "$API_BASE/local_gateway.py" -o "$GATEWAY_FILE"
curl -fsSL "$RAG_BASE/rag_engine.py" -o "$ENGINE_FILE"
curl -fsSL "$RAG_BASE/document_loaders.py" -o "$LOADER_FILE"
curl -fsSL "$RAG_BASE/document_library.py" -o "$LIBRARY_FILE"
"$PYTHON" -m py_compile "$GATEWAY_FILE" "$ENGINE_FILE" "$LOADER_FILE" "$LIBRARY_FILE"
echo "Python syntax checks passed."

umask 077
"$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(40))' > "$KEY_FILE"
PYTHONPATH="$RAG_DEPS" PLATFORM_HOST=127.0.0.1 PLATFORM_PORT=8010 PLATFORM_API_KEY="$(cat "$KEY_FILE")" \
  RAG_DOCS_DIR="$DOCS" RAG_MANAGED_DOCS_DIR=/workspace/rag-managed-docs RAG_MIN_SCORE=2.30 RAG_MANAGED_MIN_SCORE=0.0 \
  UV_CACHE_DIR=/tmp/uv-cache TMPDIR=/tmp \
  nohup "$PYTHON" "$GATEWAY_FILE" > "$LOG_FILE" 2>&1 </dev/null &
echo "$!" > "$PID_FILE"

ready=0
for _ in $(seq 1 30); do
  if curl -fsS "$URL/health" >/tmp/platform-gateway-health.json 2>/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  echo "ERROR: gateway health check failed. Recent logs:" >&2
  tail -30 "$LOG_FILE" >&2 || true
  exit 5
fi

echo "=== HEALTH ==="
cat /tmp/platform-gateway-health.json
echo

echo "=== UNAUTHENTICATED RAG REQUEST MUST BE REJECTED ==="
unauth_code="$(curl -sS -o /tmp/platform-gateway-rag-unauth.json -w '%{http_code}' \
  -X POST "$URL/v1/rag/ask" -H 'Content-Type: application/json' \
  -d '{"question":"How many business days are allowed?"}')"
cat /tmp/platform-gateway-rag-unauth.json
echo
if [[ "$unauth_code" != "401" ]]; then
  echo "FAIL: unauthenticated RAG request returned $unauth_code, expected 401" >&2
  exit 6
fi
echo "PASS: unauthenticated RAG request rejected"

echo "=== AUTHENTICATED CHAT COMPLETION ==="
chat_response="$(curl -fsS -X POST "$URL/v1/chat/completions" \
  -H "Authorization: Bearer $(cat "$KEY_FILE")" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: gateway works\"}],\"temperature\":0,\"max_tokens\":12}")"
printf '%s' "$chat_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); a=d.get("choices",[{}])[0].get("message",{}).get("content",""); print("Answer:",a); assert "gateway works" in a.casefold(), "expected phrase not found"'
echo "PASS: authenticated chat request"

echo "=== AUTHENTICATED RAG QUESTION ==="
rag_response="$(curl -fsS -X POST "$URL/v1/rag/ask" \
  -H "Authorization: Bearer $(cat "$KEY_FILE")" \
  -H 'Content-Type: application/json' \
  -d '{"question":"How many business days do employees have to submit expense receipts?","top_k":4}')"
printf '%s' "$rag_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("Status:",d.get("status")); print("Answer:",d.get("answer")); print("Sources:",", ".join(x.get("file","?") for x in d.get("sources",[]))); assert d.get("status") == "answered"; assert "10 business days" in d.get("answer","").casefold(); assert any(x.get("file")=="expenses-policy.md" for x in d.get("sources",[]))'
echo "PASS: RAG answered and returned source metadata"

echo "=== LOW-RELEVANCE QUESTION MUST ABSTAIN ==="
low_response="$(curl -fsS -X POST "$URL/v1/rag/ask" \
  -H "Authorization: Bearer $(cat "$KEY_FILE")" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What colour is the CEO private yacht?","top_k":4}')"
printf '%s' "$low_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("Status:",d.get("status")); print("Answer:",d.get("answer")); print("Retrieval:",d.get("retrieval")); assert d.get("status")=="abstained"; assert d.get("retrieval",{}).get("reason")=="below_min_score"; assert d.get("sources")==[]'
echo "PASS: low-relevance question was rejected before generation"

echo
echo "ALL GATEWAY + RAG API SMOKE TESTS PASSED."
echo "Gateway remains on $URL (loopback only)."
echo "Log: $LOG_FILE"
echo "PID: $PID_FILE"
echo "Temporary API key: $KEY_FILE (not printed or committed)."
