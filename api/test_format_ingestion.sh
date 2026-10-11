#!/usr/bin/env bash
# Isolated CSV/DOCX -> RAG HTTP API integration test.
# Starts a temporary loopback gateway on 8011; leaves the existing 8010 gateway and vLLM untouched.
set -euo pipefail

BASE=https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main
PYTHON=/tmp/vllm-clean-env/bin/python
KEY_FILE=/tmp/platform-gateway.key
APP_DIR=/tmp/platform-format-test-app
DOCS_DIR=/tmp/platform-format-test-docs
URL=http://127.0.0.1:8011
PID_FILE=/tmp/platform-format-test.pid
LOG_FILE=/tmp/platform-format-test.log
TEST_PID=""

cleanup() {
  status=$?
  if [[ -n "$TEST_PID" ]] && kill -0 "$TEST_PID" 2>/dev/null; then
    kill "$TEST_PID" 2>/dev/null || true
    for _ in $(seq 1 10); do
      if ! kill -0 "$TEST_PID" 2>/dev/null; then break; fi
      sleep 1
    done
  fi
  rm -f "$PID_FILE"
  rm -rf "$APP_DIR" "$DOCS_DIR"
  if [[ "$status" -eq 0 ]]; then
    echo "Temporary format-test gateway stopped; existing gateway at 127.0.0.1:8010 and vLLM remain untouched."
  else
    echo "Format test failed. Temporary gateway log (if any): $LOG_FILE" >&2
    tail -30 "$LOG_FILE" 2>/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT

if [[ ! -x "$PYTHON" ]]; then echo "ERROR: current Python environment not found; no installation attempted." >&2; exit 2; fi
if [[ ! -r "$KEY_FILE" ]]; then echo "ERROR: current temporary gateway key not found; existing service untouched." >&2; exit 3; fi
if curl -fsS http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then :; else echo "ERROR: vLLM is not responding at 127.0.0.1:8000." >&2; exit 4; fi
if curl -fsS "$URL/health" >/dev/null 2>&1; then echo "ERROR: port 8011 already has a responsive service. Refusing to replace it." >&2; exit 5; fi

mkdir -p "$APP_DIR" "$DOCS_DIR"
curl -fsSL "$BASE/api/local_gateway.py" -o "$APP_DIR/local_gateway.py"
curl -fsSL "$BASE/rag/rag_engine.py" -o "$APP_DIR/rag_engine.py"
curl -fsSL "$BASE/rag/document_loaders.py" -o "$APP_DIR/document_loaders.py"

cat > "$DOCS_DIR/visitor-rules.csv" <<'CSV'
rule,detail
visitor check-in,Visitors must check in at Gate C.
CSV

"$PYTHON" - "$DOCS_DIR/launch-review.docx" <<'PY'
import sys, zipfile
from pathlib import Path
path = Path(sys.argv[1])
xml = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:body>'
    '<w:p><w:r><w:t>Project Helios launch review is scheduled for 18 November.</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>The review owner is the Operations team.</w:t></w:r></w:p>'
    '</w:body></w:document>'
)
with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("word/document.xml", xml)
PY

"$PYTHON" -m py_compile "$APP_DIR/local_gateway.py" "$APP_DIR/rag_engine.py" "$APP_DIR/document_loaders.py"
API_KEY="$(cat "$KEY_FILE")"
PLATFORM_HOST=127.0.0.1 PLATFORM_PORT=8011 PLATFORM_API_KEY="$API_KEY" \
  VLLM_UPSTREAM_URL=http://127.0.0.1:8000/v1 RAG_DOCS_DIR="$DOCS_DIR" RAG_MIN_SCORE=0 \
  UV_CACHE_DIR=/tmp/uv-cache TMPDIR=/tmp \
  nohup "$PYTHON" "$APP_DIR/local_gateway.py" > "$LOG_FILE" 2>&1 </dev/null &
TEST_PID=$!
echo "$TEST_PID" > "$PID_FILE"

ready=0
for _ in $(seq 1 25); do
  if curl -fsS "$URL/health" >/tmp/platform-format-health.json 2>/dev/null; then ready=1; break; fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then echo "ERROR: isolated test gateway failed to start." >&2; exit 6; fi

echo "=== CSV INTEGRATION TEST ==="
csv_response="$(curl -fsS -X POST "$URL/v1/rag/ask" \
  -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' \
  -d '{"question":"At which gate must visitors check in?","top_k":2}')"
printf '%s' "$csv_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("Status:",d.get("status")); print("Answer:",d.get("answer")); print("Sources:",", ".join(x.get("file","?") for x in d.get("sources",[]))); assert d.get("status")=="answered"; assert "gate c" in d.get("answer","").casefold(); assert any(x.get("file")=="visitor-rules.csv" for x in d.get("sources",[]))'
echo "PASS: CSV was retrieved and its source was returned."

echo "=== DOCX INTEGRATION TEST ==="
docx_response="$(curl -fsS -X POST "$URL/v1/rag/ask" \
  -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' \
  -d '{"question":"When is the Project Helios launch review scheduled?","top_k":2}')"
printf '%s' "$docx_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("Status:",d.get("status")); print("Answer:",d.get("answer")); print("Sources:",", ".join(x.get("file","?") for x in d.get("sources",[]))); assert d.get("status")=="answered"; assert "18 november" in d.get("answer","").casefold(); assert any(x.get("file")=="launch-review.docx" for x in d.get("sources",[]))'
echo "PASS: DOCX was retrieved and its source was returned."

echo "ALL CSV/DOCX INTEGRATION TESTS PASSED."
