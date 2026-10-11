#!/usr/bin/env bash
# Test document upload/list/ask/delete on an isolated local gateway.
# Existing gateway :8010, vLLM :8000, and the Global Volume are not modified.
set -Eeuo pipefail

BASE=https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main
PYTHON=/tmp/vllm-clean-env/bin/python
KEY_FILE=/tmp/platform-gateway.key
APP_DIR=/tmp/platform-document-management-app
MANAGED_DIR=/tmp/platform-document-management-store
DOCS_DIR=/workspace/rag-demo-docs
URL=http://127.0.0.1:8012
LOG_FILE=/tmp/platform-document-management-test.log
KEY=""
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
  rm -rf "$APP_DIR" "$MANAGED_DIR"
  if [[ "$status" -eq 0 ]]; then
    echo "Temporary document-management gateway and files cleaned up; main gateway and vLLM untouched."
  else
    echo "Document-management test failed; recent temporary gateway log:" >&2
    tail -30 "$LOG_FILE" 2>/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT

if [[ ! -x "$PYTHON" ]]; then echo "ERROR: expected vLLM Python environment missing; no install attempted." >&2; exit 2; fi
if [[ ! -r "$KEY_FILE" ]]; then echo "ERROR: temporary API key missing at $KEY_FILE; current service untouched." >&2; exit 3; fi
if ! PYTHONPATH=/tmp/rag-deps "$PYTHON" -c 'import pypdf, openpyxl, et_xmlfile, defusedxml'; then echo "ERROR: document parser dependencies missing; existing services untouched." >&2; exit 4; fi
if ! curl -fsS http://127.0.0.1:8000/v1/models >/dev/null; then echo "ERROR: vLLM is not responding at 127.0.0.1:8000." >&2; exit 5; fi
if curl -fsS "$URL/health" >/dev/null 2>&1; then echo "ERROR: port 8012 already serves a gateway; refusing to replace it." >&2; exit 6; fi

mkdir -p "$APP_DIR"
curl -fsSL "$BASE/api/local_gateway.py" -o "$APP_DIR/local_gateway.py"
curl -fsSL "$BASE/rag/rag_engine.py" -o "$APP_DIR/rag_engine.py"
curl -fsSL "$BASE/rag/document_loaders.py" -o "$APP_DIR/document_loaders.py"
curl -fsSL "$BASE/rag/document_library.py" -o "$APP_DIR/document_library.py"
"$PYTHON" -m py_compile "$APP_DIR/local_gateway.py" "$APP_DIR/rag_engine.py" "$APP_DIR/document_loaders.py" "$APP_DIR/document_library.py"
echo "All gateway modules compiled."

KEY="$(cat "$KEY_FILE")"
mkdir -p "$MANAGED_DIR"
PYTHONPATH=/tmp/rag-deps PLATFORM_HOST=127.0.0.1 PLATFORM_PORT=8012 PLATFORM_API_KEY="$KEY" \
  VLLM_UPSTREAM_URL=http://127.0.0.1:8000/v1 RAG_DOCS_DIR="$DOCS_DIR" \
  RAG_MANAGED_DOCS_DIR="$MANAGED_DIR" RAG_MIN_SCORE=2.30 RAG_MANAGED_MIN_SCORE=0.0 \
  UV_CACHE_DIR=/tmp/uv-cache TMPDIR=/tmp \
  nohup "$PYTHON" "$APP_DIR/local_gateway.py" > "$LOG_FILE" 2>&1 </dev/null &
TEST_PID=$!

ready=0
for _ in $(seq 1 25); do
  if curl -fsS "$URL/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then echo "ERROR: isolated gateway did not start." >&2; exit 7; fi

echo "=== UNAUTHENTICATED UPLOAD MUST BE REJECTED ==="
unauth_code="$(curl -sS -o /tmp/doc-mgmt-unauth.json -w '%{http_code}' -X POST "$URL/v1/rag/documents" -H 'Content-Type: application/json' -d '{}')"
if [[ "$unauth_code" != "401" ]]; then echo "FAIL: expected 401, received $unauth_code" >&2; cat /tmp/doc-mgmt-unauth.json >&2; exit 8; fi
echo "PASS: unauthenticated upload rejected."

echo "=== UPLOAD DOCUMENT ==="
upload_payload="$("$PYTHON" -c 'import base64,json; data=b"Project Nimbus finance note. The finance escalation contact is ap-team@example.invalid."; print(json.dumps({"collection":"finance-smoke","filename":"finance-notice.md","content_base64":base64.b64encode(data).decode("ascii")}))')"
upload_code="$(curl -sS -o /tmp/doc-mgmt-upload.json -w '%{http_code}' -X POST "$URL/v1/rag/documents" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d "$upload_payload")"
cat /tmp/doc-mgmt-upload.json
echo
if [[ "$upload_code" != "201" ]]; then echo "FAIL: expected upload HTTP 201, got $upload_code" >&2; exit 9; fi
echo "PASS: upload returned 201."

echo "=== LIST COLLECTION ==="
list_json="$(curl -fsS -G "$URL/v1/rag/documents" -H "Authorization: Bearer $KEY" --data-urlencode "collection=finance-smoke")"
printf '%s' "$list_json" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print(d); assert d.get("collection")=="finance-smoke"; assert any(x.get("filename")=="finance-notice.md" for x in d.get("documents",[]))'
echo "PASS: list returned uploaded document metadata."

echo "=== DUPLICATE UPLOAD MUST NOT OVERWRITE BY DEFAULT ==="
duplicate_code="$(curl -sS -o /tmp/doc-mgmt-duplicate.json -w '%{http_code}' -X POST "$URL/v1/rag/documents" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d "$upload_payload")"
if [[ "$duplicate_code" != "409" ]]; then echo "FAIL: expected duplicate HTTP 409, got $duplicate_code" >&2; cat /tmp/doc-mgmt-duplicate.json >&2; exit 10; fi
echo "PASS: duplicate upload did not overwrite existing file."

echo "=== PATH TRAVERSAL MUST BE REJECTED ==="
bad_payload="$("$PYTHON" -c 'import base64,json; print(json.dumps({"collection":"finance-smoke","filename":"../outside.md","content_base64":base64.b64encode(b"unsafe").decode()}))')"
bad_code="$(curl -sS -o /tmp/doc-mgmt-traversal.json -w '%{http_code}' -X POST "$URL/v1/rag/documents" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d "$bad_payload")"
if [[ "$bad_code" != "400" ]]; then echo "FAIL: expected traversal HTTP 400, got $bad_code" >&2; cat /tmp/doc-mgmt-traversal.json >&2; exit 11; fi
echo "PASS: path traversal rejected."

echo "=== ASK USING THE UPLOADED COLLECTION ==="
ask_response="$(curl -fsS -X POST "$URL/v1/rag/ask" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d '{"collection":"finance-smoke","question":"What is the finance escalation contact?","top_k":2}')"
printf '%s' "$ask_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("Status:",d.get("status")); print("Answer:",d.get("answer")); print("Sources:",d.get("sources")); assert d.get("status")=="answered"; assert "ap-team@example.invalid" in d.get("answer","").casefold(); assert any(x.get("file")=="finance-notice.md" for x in d.get("sources",[]))'
echo "PASS: query returned answer and uploaded source."

echo "=== DELETE UPLOADED DOCUMENT ==="
delete_code="$(curl -sS -o /tmp/doc-mgmt-delete.json -w '%{http_code}' -X DELETE "$URL/v1/rag/documents?collection=finance-smoke&filename=finance-notice.md" -H "Authorization: Bearer $KEY")"
cat /tmp/doc-mgmt-delete.json
echo
if [[ "$delete_code" != "200" ]]; then echo "FAIL: expected delete HTTP 200, got $delete_code" >&2; exit 12; fi
list_after="$(curl -fsS -G "$URL/v1/rag/documents" -H "Authorization: Bearer $KEY" --data-urlencode "collection=finance-smoke")"
printf '%s' "$list_after" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); assert d.get("documents")==[]; print("PASS: deleted document no longer listed.")'

echo "ALL DOCUMENT-MANAGEMENT API TESTS PASSED."
