#!/usr/bin/env bash
# Isolated test gateway :8013 + optional console :8083 pointed at Qwen :8002.
# Leaves main :8010/:8080 and Gemma :8000 untouched.
set -Eeuo pipefail
umask 077

REPO="${REPO_ROOT:-/tmp/AI-PLAYBOOK}"
RUNTIME="${QWEN_VLLM_ENV:-/tmp/vllm-qwen-env}"
# Prefer Gemma python for gateway code if present; else fall back to Qwen/system python.
if [[ -z "${GATEWAY_PYTHON:-}" ]]; then
  if [[ -x /tmp/vllm-clean-env/bin/python ]]; then
    GW_PYTHON=/tmp/vllm-clean-env/bin/python
  elif [[ -x "$RUNTIME/bin/python" ]]; then
    GW_PYTHON="$RUNTIME/bin/python"
  else
    GW_PYTHON=/usr/bin/python3
  fi
else
  GW_PYTHON="$GATEWAY_PYTHON"
fi
KEY="${PLATFORM_API_KEY_FILE:-/tmp/platform-gateway.key}"
DIAG=/workspace/platform-diagnostics/qwen
MODE="${1:---start}"

fail() { echo "ERROR: $*" >&2; exit 1; }
healthy() { curl -fsS --max-time 3 "$1" >/dev/null 2>&1; }

mkdir -p "$DIAG"

if [[ "$MODE" == "--check" ]]; then
  printf 'Qwen upstream :8002: '; healthy http://127.0.0.1:8002/v1/models && echo HEALTHY || echo NOT_HEALTHY
  printf 'Test gateway :8013: '; healthy http://127.0.0.1:8013/health && echo HEALTHY || echo NOT_HEALTHY
  printf 'Test console :8083: '; healthy http://127.0.0.1:8083/api/status && echo HEALTHY || echo NOT_HEALTHY
  exit 0
fi

if [[ ! -f "$KEY" ]]; then
  # Ephemeral loopback key only; never commit or copy into source snapshots.
  umask 077
  openssl rand -base64 48 | tr -d '\n' >"$KEY"
  chmod 600 "$KEY"
  log_note="created ephemeral $KEY"
else
  log_note="reusing $KEY"
fi
[[ -f "$REPO/api/local_gateway.py" ]] || fail "gateway source missing under $REPO"
healthy http://127.0.0.1:8002/v1/models || fail "Qwen upstream :8002 is not healthy"
echo "Using GATEWAY_PYTHON=$GW_PYTHON ($log_note)"

if ! healthy http://127.0.0.1:8013/health; then
  nohup env \
    PLATFORM_HOST=127.0.0.1 \
    PLATFORM_PORT=8013 \
    PLATFORM_API_KEY="$(cat "$KEY")" \
    VLLM_UPSTREAM_URL=http://127.0.0.1:8002/v1 \
    PLATFORM_DEFAULT_MODEL_ID=qwen3.5-27b \
    PLATFORM_MODEL_REGISTRY="$REPO/models/registry.yaml" \
    PYTHONPATH="$REPO/api:$REPO/rag:$REPO/models:${PYTHONPATH:-}" \
    "$GW_PYTHON" "$REPO/api/local_gateway.py" \
    >>"$DIAG/gateway-8013.log" 2>&1 </dev/null &
  echo $! >"$DIAG/gateway-8013.pid"
  for _ in $(seq 1 60); do
    healthy http://127.0.0.1:8013/health && break
    sleep 1
  done
  healthy http://127.0.0.1:8013/health || fail "test gateway :8013 failed to start"
fi

if [[ -f "$REPO/web/server.py" ]] && ! healthy http://127.0.0.1:8083/api/status; then
  nohup env \
    WEB_HOST=127.0.0.1 \
    WEB_PORT=8083 \
    PLATFORM_GATEWAY_URL=http://127.0.0.1:8013 \
    PLATFORM_API_KEY_FILE="$KEY" \
    PLATFORM_MODEL_ID=/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654 \
    "$GW_PYTHON" "$REPO/web/server.py" \
    >>"$DIAG/console-8083.log" 2>&1 </dev/null &
  echo $! >"$DIAG/console-8083.pid"
fi

bash "$0" --check
echo "Main services :8000/:8010/:8080 were not modified by this script."
