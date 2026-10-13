#!/usr/bin/env bash
# Start Qwen3.5-27B on isolated loopback :8002 ONLY when the GPU is free.
# Never touches Gemma :8000, gateway :8010, or console :8080.
#
# Usage:
#   bash ops/start-qwen-isolated.sh --check
#   bash ops/start-qwen-isolated.sh --start   # refuses if GPU already occupied
#   bash ops/start-qwen-isolated.sh --stop    # stops only the Qwen pid recorded here
set -Eeuo pipefail
umask 077

VOL=/workspace
REVISION=fc05daec18b0a78c049392ed2e771dde82bdf654
MODEL="$VOL/models/Qwen3.5-27B/$REVISION"
ENV_DIR="${QWEN_VLLM_ENV:-/tmp/vllm-qwen-env}"
HOST=127.0.0.1
PORT=8002
DIAG="$VOL/platform-diagnostics/qwen"
PIDFILE="$DIAG/qwen-vllm.pid"
LOG="$DIAG/qwen-vllm.log"
MODE="${1:---check}"
# If used memory exceeds this many MiB, assume another model (Gemma) owns the GPU.
MAX_USED_MIB_BEFORE_START="${QWEN_MAX_USED_MIB_BEFORE_START:-8192}"

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
healthy() { curl -fsS --max-time 3 "http://$HOST:$PORT/v1/models" >/dev/null 2>&1; }

mkdir -p "$DIAG"

gpu_used_mib() {
  nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -d ' '
}

assert_ports_safe() {
  # Refuse if main Gemma inference port is the target (should never happen).
  [[ "$PORT" != "8000" && "$PORT" != "8010" && "$PORT" != "8080" ]] || fail "refusing to bind a main-stack port"
}

case "$MODE" in
  --help|-h)
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  --check)
    assert_ports_safe
    printf 'Model path: '; [[ -f "$MODEL/config.json" ]] && echo OK || echo MISSING
    printf 'Isolated env: '; [[ -x "$ENV_DIR/bin/vllm" ]] && echo PRESENT || echo MISSING
    printf 'Qwen API :%s: ' "$PORT"; healthy && echo HEALTHY || echo NOT_HEALTHY
    printf 'Gemma API :8000: '; curl -fsS --max-time 3 http://127.0.0.1:8000/v1/models >/dev/null 2>&1 && echo HEALTHY || echo NOT_HEALTHY
    printf 'GPU memory.used MiB: '; gpu_used_mib || echo UNKNOWN
    exit 0
    ;;
  --stop)
    if [[ -f "$PIDFILE" ]]; then
      pid=$(cat "$PIDFILE")
      if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
        log "Stopping Qwen pid $pid"
        kill "$pid" || true
        for _ in $(seq 1 30); do
          kill -0 "$pid" 2>/dev/null || break
          sleep 1
        done
        if kill -0 "$pid" 2>/dev/null; then
          fail "Qwen pid $pid did not exit; inspect $LOG"
        fi
      fi
      rm -f "$PIDFILE"
    fi
    log "Qwen stop complete (main Gemma services were not targeted)."
    exit 0
    ;;
  --start)
    assert_ports_safe
    [[ -f "$MODEL/config.json" ]] || fail "Qwen weights missing at $MODEL; run ops/download-qwen3.5-27b.sh first"
    [[ -x "$ENV_DIR/bin/vllm" ]] || fail "Isolated env missing; run ops/install-qwen-vllm-env.sh first"
    if healthy; then
      log "Qwen already healthy on :$PORT; reusing."
      exit 0
    fi
    if curl -fsS --max-time 3 http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then
      fail "Gemma/vLLM is healthy on :8000. Do not start Qwen concurrently. Stop Gemma only with explicit approval, then retry."
    fi
    used=$(gpu_used_mib || echo 999999)
    if [[ "$used" =~ ^[0-9]+$ ]] && (( used > MAX_USED_MIB_BEFORE_START )); then
      fail "GPU memory.used=${used}MiB exceeds ${MAX_USED_MIB_BEFORE_START}MiB; another model may still own the GPU."
    fi
    export PATH="$ENV_DIR/bin:$PATH"
    export TMPDIR=/tmp
    export VLLM_RPC_BASE_PATH=/tmp
    # CUDA 13 libs live under the venv nvidia packages; without this, libcudart.so.13 may be missing.
    if [[ -d "$ENV_DIR/lib/python3.12/site-packages/nvidia" ]]; then
      _qwen_ld=$(find "$ENV_DIR/lib/python3.12/site-packages/nvidia" -type f -name 'lib*.so*' -printf '%h\n' 2>/dev/null | sort -u | paste -sd: -)
      export LD_LIBRARY_PATH="${_qwen_ld}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
      unset _qwen_ld
    fi
    log "Starting isolated Qwen on ${HOST}:${PORT} from $MODEL"
    nohup "$ENV_DIR/bin/python" "$ENV_DIR/bin/vllm" serve "$MODEL" \
      --host "$HOST" \
      --port "$PORT" \
      --trust-remote-code \
      --language-model-only \
      --reasoning-parser qwen3 \
      --max-model-len "${QWEN_MAX_MODEL_LEN:-8192}" \
      --gpu-memory-utilization "${QWEN_GPU_MEM_UTIL:-0.90}" \
      --default-chat-template-kwargs '{"enable_thinking": false}' \
      >>"$LOG" 2>&1 </dev/null &
    echo $! >"$PIDFILE"
    ready=0
    for _ in $(seq 1 240); do
      if healthy; then ready=1; break; fi
      sleep 2
    done
    [[ "$ready" == 1 ]] || fail "Qwen did not become ready; inspect $LOG (process may still be running)"
    log "Qwen healthy at http://${HOST}:${PORT}/v1/models"
    exit 0
    ;;
  *)
    echo "Usage: bash ops/start-qwen-isolated.sh [--check|--start|--stop|--help]" >&2
    exit 2
    ;;
esac
