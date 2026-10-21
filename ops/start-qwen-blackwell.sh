#!/usr/bin/env bash
# Serve Qwen3.5-27B from the Blackwell environment only.
# Does not restore or replace the A100 archive, and does not start the gateway or console.
#
# Usage: start-qwen-blackwell.sh [--check|--serve|--infer]
set -Eeuo pipefail

REPO_ROOT="${REPO_ROOT:-/tmp/AI-PLAYBOOK}"
ENV_DIR="${QWEN_BLACKWELL_ENV:-/tmp/vllm-qwen-blackwell-env}"
A100_ENV=/tmp/vllm-qwen-env
MODEL="${QWEN_MODEL:-/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654}"
PORT="${QWEN_PORT:-8002}"
DIAG="${PLATFORM_DIAG_DIR:-/workspace/platform-diagnostics/blackwell}"
READY_TIMEOUT_S="${QWEN_READY_TIMEOUT_S:-2700}"
MODE="${1:---check}"
URL="http://127.0.0.1:${PORT}/v1/models"

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
healthy() { curl -fsS --max-time 3 "$URL" >/dev/null 2>&1; }

[[ "$ENV_DIR" != "$A100_ENV" && "$ENV_DIR" != /tmp/vllm-clean-env ]] || fail "refusing to launch from $ENV_DIR"
[[ -x "$ENV_DIR/bin/vllm" ]] || fail "Blackwell runtime missing. Run ops/install-qwen-blackwell-env.sh first."
bash "$REPO_ROOT/ops/install-qwen-blackwell-env.sh" --check

if [[ "$MODE" == "--check" ]]; then
  log "Blackwell runtime check passed. Model was not loaded."
  exit 0
fi

[[ "$MODE" == "--serve" || "$MODE" == "--infer" ]] || fail "usage: $0 [--check|--serve|--infer]"
[[ -f "$MODEL/config.json" ]] || fail "Qwen weights missing at $MODEL"

if ! healthy; then
  if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${PORT}\$"; then
    fail "port $PORT is already in use by something that is not a healthy Qwen server"
  fi
  read -r GPU_TOTAL GPU_USED <<<"$(nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits | head -n1 | tr ',' ' ')"
  [[ "${GPU_USED:-0}" =~ ^[0-9]+$ && "$GPU_USED" -le 2048 ]] || fail "GPU already has ${GPU_USED} MiB in use"
  if [[ "$GPU_TOTAL" -lt 90000 ]]; then UTIL=0.90; else UTIL=0.92; fi
  mkdir -p "$DIAG"
  log "Starting Qwen from $ENV_DIR on 127.0.0.1:$PORT gpu_mem_util=$UTIL"
  nohup env PATH="$ENV_DIR/bin:${PATH:-}" VLLM_DO_NOT_TRACK=1 \
    "$ENV_DIR/bin/python" "$ENV_DIR/bin/vllm" serve "$MODEL" \
    --host 127.0.0.1 --port "$PORT" \
    --trust-remote-code \
    --language-model-only \
    --reasoning-parser qwen3 \
    --max-model-len 8192 \
    --max-num-seqs 256 \
    --gpu-memory-utilization "$UTIL" \
    --default-chat-template-kwargs '{"enable_thinking": false}' \
    >"$DIAG/qwen-vllm.log" 2>&1 </dev/null &
  echo $! >"$DIAG/qwen-vllm.pid"
  waited=0
  until healthy; do
    kill -0 "$(cat "$DIAG/qwen-vllm.pid")" 2>/dev/null || fail "Qwen exited; see $DIAG/qwen-vllm.log"
    (( waited >= READY_TIMEOUT_S )) && fail "Qwen not ready after ${READY_TIMEOUT_S}s"
    sleep 10
    waited=$((waited + 10))
  done
  log "Qwen ready after ~${waited}s"
fi

[[ "$MODE" == "--infer" ]] || exit 0
curl -fsS --max-time 120 "http://127.0.0.1:${PORT}/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen","messages":[{"role":"user","content":"Reply with the single word pong."}],"max_tokens":16,"temperature":0}'
echo
