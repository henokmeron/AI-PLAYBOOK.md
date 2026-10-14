#!/usr/bin/env bash
# Start/stop an ISOLATED test gateway for the RAG benchmark on the Pod.
#
#   bash pod_test_gateway.sh prepare            # parser deps + test key (once)
#   bash pod_test_gateway.sh start <src-dir>    # src-dir contains api/ rag/ models/
#   bash pod_test_gateway.sh stop
#
# Never touches the live gateway (:8010), console (:8080) or other agents'
# ports; reuses the shared Qwen vLLM on :8002 read-only. Uses its own random
# key file, so the live key is never read.
set -euo pipefail

ROOT="${RAGDEV_ROOT:-/tmp/ragdev}"
PORT="${RAGDEV_GATEWAY_PORT:-8014}"
PY="${RAGDEV_PYTHON:-/tmp/vllm-qwen-env/bin/python}"
DEPS="$ROOT/rag-deps"
KEY="$ROOT/test-gateway.key"
PID_FILE="$ROOT/gateway-$PORT.pid"
LOG="$ROOT/gateway-$PORT.log"

case "$PORT" in 8010|8080|8000|8002|8013|8083) echo "refusing reserved port $PORT" >&2; exit 2;; esac

prepare() {
  mkdir -p "$ROOT"
  if ! PYTHONPATH="$DEPS" "$PY" -c 'import pypdf, openpyxl' 2>/dev/null; then
    REPO="${1:-$ROOT/current}"
    RAG_SETUP_PYTHON="$PY" RAG_DEPS_DIR="$DEPS" bash "$REPO/rag/setup_pdf_support.sh" >"$ROOT/rag-deps.log" 2>&1
    RAG_SETUP_PYTHON="$PY" RAG_DEPS_DIR="$DEPS" bash "$REPO/rag/setup_xlsx_support.sh" >>"$ROOT/rag-deps.log" 2>&1
  fi
  PYTHONPATH="$DEPS" "$PY" -c 'import importlib.metadata as m; print("pypdf", m.version("pypdf"), "openpyxl", m.version("openpyxl"))'
  if [[ ! -s "$KEY" ]]; then
    (umask 077; "$PY" -c 'import secrets; print(secrets.token_urlsafe(48))' >"$KEY")
  fi
  echo "test key file: $KEY (not printed)"
}

stop() {
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null && tr '\0' ' ' <"/proc/$pid/cmdline" | grep -q "local_gateway.py"; then
      kill "$pid"
      for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    fi
    rm -f "$PID_FILE"
  fi
  echo "stopped test gateway on :$PORT"
}

start() {
  SRC="$(cd "$1" && pwd)"
  stop >/dev/null
  if ss -ltn | awk '{print $4}' | grep -q ":$PORT\$"; then
    echo "port $PORT is busy and not ours; aborting" >&2
    exit 3
  fi
  LABEL="$(basename "$SRC")"
  MANAGED="$ROOT/managed-$LABEL"
  mkdir -p "$ROOT/demo-docs" "$MANAGED"
  cp -f "$SRC/rag/sample_docs/"*.md "$ROOT/demo-docs/" 2>/dev/null || true
  nohup env \
    PLATFORM_HOST=127.0.0.1 \
    PLATFORM_PORT="$PORT" \
    PLATFORM_API_KEY="$(cat "$KEY")" \
    VLLM_UPSTREAM_URL="http://127.0.0.1:8002/v1" \
    RAG_DOCS_DIR="$ROOT/demo-docs" \
    RAG_MANAGED_DOCS_DIR="$MANAGED" \
    PYTHONPATH="$SRC/api:$SRC/models:$SRC/rag:$DEPS" \
    "$PY" "$SRC/api/local_gateway.py" >"$LOG" 2>&1 </dev/null &
  echo $! >"$PID_FILE"
  for _ in $(seq 1 40); do
    if curl -fsS -m 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      echo "test gateway ($LABEL) healthy on :$PORT pid $(cat "$PID_FILE")"
      return 0
    fi
    sleep 0.5
  done
  echo "test gateway failed to become healthy; tail of log:" >&2
  tail -n 20 "$LOG" >&2
  exit 4
}

case "${1:-}" in
  prepare) prepare "${2:-}";;
  start) start "${2:?source dir required}";;
  stop) stop;;
  *) echo "usage: $0 prepare|start <src>|stop" >&2; exit 2;;
esac
