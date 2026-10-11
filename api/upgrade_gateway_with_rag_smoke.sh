#!/usr/bin/env bash
# Safely upgrade the local gateway with POST /v1/rag/ask and test it.
# Preserves the existing API key and attempts to roll back on any failed check.
set -Eeuo pipefail

BASE=https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main
PYTHON=/tmp/vllm-clean-env/bin/python
KEY_FILE=/tmp/platform-gateway.key
GATEWAY=/tmp/platform_gateway.py
OLD_GATEWAY=/tmp/platform_gateway.py.pre-rag
NEXT_GATEWAY=/tmp/platform_gateway.py.next
ENGINE=/tmp/rag_engine.py
NEXT_ENGINE=/tmp/rag_engine.py.next
PID_FILE=/tmp/platform-gateway.pid
LOG_FILE=/tmp/platform-gateway.log
URL=http://127.0.0.1:8010
DOCS=/workspace/rag-demo-docs
UPGRADED=0
NEW_PID=""

rollback_on_failure() {
  status=$?
  if [[ "$status" -ne 0 && "$UPGRADED" == "1" && -f "$OLD_GATEWAY" ]]; then
    echo "ERROR: new gateway checks failed; restoring previous gateway version." >&2
    if [[ -n "$NEW_PID" ]] && kill -0 "$NEW_PID" 2>/dev/null; then
      kill "$NEW_PID" 2>/dev/null || true
      sleep 1
    fi
    cp "$OLD_GATEWAY" "$GATEWAY"
    PLATFORM_HOST=127.0.0.1 PLATFORM_PORT=8010 PLATFORM_API_KEY="$API_KEY" \
      UV_CACHE_DIR=/tmp/uv-cache TMPDIR=/tmp \
      nohup "$PYTHON" "$GATEWAY" > /tmp/platform-gateway-rollback.log 2>&1 </dev/null &
    rollback_pid=$!
    echo "$rollback_pid" > "$PID_FILE"
    for _ in $(seq 1 15); do
      if curl -fsS "$URL/health" >/dev/null 2>&1; then
        echo "Previous gateway restored at $URL; rollback PID $rollback_pid" >&2
        break
      fi
      sleep 1
    done
    echo "Rollback log: /tmp/platform-gateway-rollback.log" >&2
  fi
  exit "$status"
}
trap rollback_on_failure EXIT

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: working vLLM Python environment not found at $PYTHON; refusing to install anything." >&2
  exit 2
fi
if [[ ! -r "$KEY_FILE" ]]; then
  echo "ERROR: current temporary gateway key not found at $KEY_FILE; existing gateway was not changed." >&2
  exit 3
fi
API_KEY="$(cat "$KEY_FILE")"
if [[ "${#API_KEY}" -lt 32 ]]; then
  echo "ERROR: gateway key is missing/too short; existing gateway was not changed." >&2
  exit 4
fi
if [[ ! -d "$DOCS" ]]; then
  echo "ERROR: expected demo document folder missing at $DOCS; existing gateway was not changed." >&2
  exit 5
fi

echo "=== DOWNLOAD AND CHECK NEW FILES ==="
curl -fsSL "$BASE/api/local_gateway.py" -o "$NEXT_GATEWAY"
curl -fsSL "$BASE/rag/rag_engine.py" -o "$NEXT_ENGINE"
"$PYTHON" -m py_compile "$NEXT_GATEWAY" "$NEXT_ENGINE"
echo "New gateway and shared RAG engine passed Python syntax compilation."

if [[ -f "$GATEWAY" ]]; then
  cp "$GATEWAY" "$OLD_GATEWAY"
fi

# Stop only the process recorded by our previous gateway smoke script.
if [[ -r "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  OLD_CMD="$(ps -p "$OLD_PID" -o args= 2>/dev/null || true)"
  if [[ "$OLD_CMD" == *"/tmp/platform_gateway.py"* ]]; then
    echo "Stopping existing local gateway PID $OLD_PID (the vLLM model server is not touched)."
    kill "$OLD_PID"
    for _ in $(seq 1 15); do
      if ! kill -0 "$OLD_PID" 2>/dev/null; then
        break
      fi
      sleep 1
    done
    if kill -0 "$OLD_PID" 2>/dev/null; then
      echo "ERROR: previous gateway did not stop; refusing to force-kill it." >&2
      exit 6
    fi
  else
    echo "ERROR: PID file does not identify the expected gateway process. Existing service left unchanged." >&2
    exit 7
  fi
else
  echo "ERROR: gateway PID file is missing. Existing service left unchanged." >&2
  exit 8
fi

if curl -fsS "$URL/health" >/dev/null 2>&1; then
  echo "ERROR: port 8010 still responds after stopping the recorded gateway. Refusing to start a competing process." >&2
  exit 9
fi

UPGRADED=1
cp "$NEXT_GATEWAY" "$GATEWAY"
cp "$NEXT_ENGINE" "$ENGINE"

echo "=== START UPDATED LOOPBACK GATEWAY ==="
PLATFORM_HOST=127.0.0.1 PLATFORM_PORT=8010 PLATFORM_API_KEY="$API_KEY" \
  RAG_DOCS_DIR="$DOCS" RAG_MIN_SCORE=2.30 \
  UV_CACHE_DIR=/tmp/uv-cache TMPDIR=/tmp \
  nohup "$PYTHON" "$GATEWAY" > "$LOG_FILE" 2>&1 </dev/null &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

ready=0
for _ in $(seq 1 30); do
  if curl -fsS "$URL/health" > /tmp/platform-gateway-health.json 2>/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != "1" ]]; then
  echo "ERROR: upgraded gateway health check failed." >&2
  tail -30 "$LOG_FILE" >&2 || true
  exit 10
fi
echo "Health:"
cat /tmp/platform-gateway-health.json
echo

echo "=== UNAUTHENTICATED RAG REQUEST MUST BE REJECTED ==="
unauth_code="$(curl -sS -o /tmp/platform-gateway-rag-unauth.json -w '%{http_code}' \
  -X POST "$URL/v1/rag/ask" -H 'Content-Type: application/json' \
  -d '{"question":"How many business days are allowed?"}')"
cat /tmp/platform-gateway-rag-unauth.json
echo
if [[ "$unauth_code" != "401" ]]; then
  echo "FAIL: expected HTTP 401, received $unauth_code." >&2
  exit 11
fi
echo "PASS: unauthenticated RAG request rejected."

echo "=== AUTHENTICATED RAG REQUEST THROUGH GATEWAY ==="
response="$(curl -fsS -X POST "$URL/v1/rag/ask" \
  -H "Authorization: Bearer $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"question":"How many business days do employees have to submit expense receipts?","top_k":4}')"
printf '%s' "$response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("Status:",d.get("status")); print("Answer:",d.get("answer")); print("Sources:",", ".join(x.get("file","?") for x in d.get("sources",[]))); assert d.get("status") == "answered", "expected status answered"; assert "10 business days" in d.get("answer","").casefold(), "expected supported deadline"; assert any(x.get("file") == "expenses-policy.md" for x in d.get("sources",[])), "expected source metadata for expenses policy"'
echo "PASS: authenticated RAG endpoint generated answer and returned source metadata."

echo "=== LOW-RELEVANCE QUESTION MUST ABSTAIN ==="
response="$(curl -fsS -X POST "$URL/v1/rag/ask" \
  -H "Authorization: Bearer $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What colour is the CEO private yacht?","top_k":4}')"
printf '%s' "$response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("Status:",d.get("status")); print("Answer:",d.get("answer")); print("Retrieval:",d.get("retrieval")); assert d.get("status") == "abstained", "expected abstained status"; assert d.get("retrieval",{}).get("reason") == "below_min_score", "expected relevance gate to reject"; assert d.get("sources") == [], "abstained response should not return source chunks"'
echo "PASS: low-relevance question was blocked before generation."

echo
echo "ALL GATEWAY + RAG API TESTS PASSED."
echo "Gateway remains at $URL with loopback-only binding."
echo "Logs: $LOG_FILE; PID: $PID_FILE."
echo "Temporary API key remains in $KEY_FILE and was not printed or committed."
trap - EXIT
