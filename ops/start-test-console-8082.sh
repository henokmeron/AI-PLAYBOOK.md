#!/usr/bin/env bash
# Start isolated test gateway :8012 and web console :8082.
# Does not touch main gateway :8010, main console :8080, /tmp/AI-PLAYBOOK,
# /tmp/platform-gateway-runtime, or the model server.
set -euo pipefail

ROOT="${1:-/tmp/AI-PLAYBOOK-upload-test}"
PYTHON=/tmp/vllm-clean-env/bin/python
TEST_GW_DIR=/tmp/platform-gateway-runtime-8082
TEST_GW_PORT=8012
TEST_WEB_PORT=8082

cd "$ROOT"
test -x "$PYTHON"
test -f /tmp/platform-gateway.key

# Reuse a healthy isolated stack instead of killing it.
if curl -fsS --max-time 3 "http://127.0.0.1:${TEST_GW_PORT}/health" >/tmp/platform-gateway-8082-health.json \
  && STATUS_JSON="$(curl -fsS --max-time 3 "http://127.0.0.1:${TEST_WEB_PORT}/api/status")" \
  && echo "$STATUS_JSON" | grep -q "http://127.0.0.1:${TEST_GW_PORT}" \
  && echo "$STATUS_JSON" | grep -q '"connection":"ready"'; then
  echo "Reusing healthy test gateway :${TEST_GW_PORT} and console :${TEST_WEB_PORT}; no restart."
  echo "Test gateway health:"
  cat /tmp/platform-gateway-8082-health.json
  echo
  echo "Test console status:"
  echo "$STATUS_JSON"
  echo
  echo "DEPLOY_VERIFIED test gateway :${TEST_GW_PORT} console :${TEST_WEB_PORT}"
  echo "Main services on :8010 / :8080 were not modified by this script."
  exit 0
fi

bash "$ROOT/rag/setup_pdf_support.sh" >/tmp/setup-pdf-8082.log
bash "$ROOT/rag/setup_xlsx_support.sh" >/tmp/setup-xlsx-8082.log
PYTHONPATH=/tmp/rag-deps "$PYTHON" -c 'import importlib.metadata as m; assert m.version("pypdf")=="6.20.0"; assert m.version("openpyxl")=="3.1.5"'

mkdir -p "$TEST_GW_DIR"
cp -f "$ROOT/api/local_gateway.py" "$TEST_GW_DIR/platform_gateway.py"
cp -f "$ROOT/rag/rag_engine.py" "$ROOT/rag/document_loaders.py" "$ROOT/rag/document_library.py" "$TEST_GW_DIR/"

# Stop previous test processes only (never 8010/8080).
if [[ -f /tmp/web-console-8082.pid ]]; then
  kill "$(cat /tmp/web-console-8082.pid)" 2>/dev/null || true
  rm -f /tmp/web-console-8082.pid
fi
if [[ -f /tmp/platform-gateway-8082.pid ]]; then
  kill "$(cat /tmp/platform-gateway-8082.pid)" 2>/dev/null || true
  rm -f /tmp/platform-gateway-8082.pid
fi
fuser -k "${TEST_WEB_PORT}/tcp" 2>/dev/null || true
fuser -k "${TEST_GW_PORT}/tcp" 2>/dev/null || true
sleep 1

cd "$TEST_GW_DIR"
PYTHONPATH=/tmp/rag-deps \
PLATFORM_HOST=127.0.0.1 \
PLATFORM_PORT="$TEST_GW_PORT" \
PLATFORM_API_KEY="$(cat /tmp/platform-gateway.key)" \
VLLM_UPSTREAM_URL=http://127.0.0.1:8000/v1 \
RAG_DOCS_DIR=/workspace/rag-demo-docs \
RAG_MANAGED_DOCS_DIR=/workspace/rag-managed-docs \
RAG_MIN_SCORE=2.30 \
RAG_MANAGED_MIN_SCORE=0.0 \
UV_CACHE_DIR=/tmp/uv-cache \
TMPDIR=/tmp \
nohup "$PYTHON" platform_gateway.py >/tmp/platform-gateway-8082.log 2>&1 </dev/null &
echo $! >/tmp/platform-gateway-8082.pid

ready=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${TEST_GW_PORT}/health" >/tmp/platform-gateway-8082-health.json; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  echo "ERROR: test gateway health failed" >&2
  tail -40 /tmp/platform-gateway-8082.log >&2 || true
  exit 5
fi
echo "Test gateway health:"
cat /tmp/platform-gateway-8082-health.json
echo

cd "$ROOT"
PLATFORM_GATEWAY_URL="http://127.0.0.1:${TEST_GW_PORT}" \
PLATFORM_MODEL_ID=/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it \
PLATFORM_API_KEY_FILE=/tmp/platform-gateway.key \
WEB_HOST=127.0.0.1 \
WEB_PORT="$TEST_WEB_PORT" \
nohup "$PYTHON" web/server.py >/tmp/web-console-8082.log 2>&1 </dev/null &
echo $! >/tmp/web-console-8082.pid
sleep 1

echo "Test console status:"
curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/status"
echo
STATUS_JSON="$(curl -fsS "http://127.0.0.1:${TEST_WEB_PORT}/api/status")"
echo "$STATUS_JSON" | grep -q "http://127.0.0.1:${TEST_GW_PORT}"
echo "$STATUS_JSON" | grep -q '"connection":"ready"'
echo "DEPLOY_VERIFIED test gateway :${TEST_GW_PORT} console :${TEST_WEB_PORT}"
echo "Main services on :8010 / :8080 were not modified by this script."
