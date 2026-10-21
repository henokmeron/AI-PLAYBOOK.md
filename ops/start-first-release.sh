#!/usr/bin/env bash
# First-release bring-up: Qwen3.5-27B (only auto-started model) + gateway + console.
# Does not download weights. Never starts Gemma. Does not create paid resources.
# Idempotent: healthy services are reused; a start already in progress is not duplicated.
#
# Usage: start-first-release.sh [--start|--check|--preflight]
# Ports/paths can be overridden for isolated testing (defaults are the main stack):
#   QWEN_PORT=8002 GATEWAY_PORT=8010 CONSOLE_PORT=8080
#   REPO_ROOT QWEN_VLLM_ENV PLATFORM_API_KEY_FILE PLATFORM_DIAG_DIR RAG_DEPS_DIR RAG_MANAGED_DOCS_DIR
set -Eeuo pipefail

REPO_ROOT="${REPO_ROOT:-/tmp/AI-PLAYBOOK}"
VOL=/workspace
QWEN_ARCHIVE_DIR="$VOL/runtime-setup/qwen-vllm"
QWEN_ENV="${QWEN_VLLM_ENV:-/tmp/vllm-qwen-env}"
QWEN_REVISION=fc05daec18b0a78c049392ed2e771dde82bdf654
MODEL="$VOL/models/Qwen3.5-27B/$QWEN_REVISION"
KEY="${PLATFORM_API_KEY_FILE:-/tmp/platform-gateway.key}"
DIAG="${PLATFORM_DIAG_DIR:-$VOL/platform-diagnostics/first-release}"
QWEN_PORT="${QWEN_PORT:-8002}"
GATEWAY_PORT="${GATEWAY_PORT:-8010}"
CONSOLE_PORT="${CONSOLE_PORT:-8080}"
GEMMA_PORT=8000
RAG_DEPS="${RAG_DEPS_DIR:-/tmp/rag-deps}"
RAG_MANAGED="${RAG_MANAGED_DOCS_DIR:-$VOL/rag-managed-docs}"
QWEN_MAX_MODEL_LEN="${QWEN_MAX_MODEL_LEN:-8192}"
QWEN_MAX_NUM_SEQS="${QWEN_MAX_NUM_SEQS:-256}"
QWEN_READY_TIMEOUT_S="${QWEN_READY_TIMEOUT_S:-2700}"
CONSOLE_PYTHON="${CONSOLE_PYTHON:-/usr/bin/python3}"
OPERATOR_AUTH_DIR="${OPERATOR_AUTH_DIR:-/tmp/console-operators}"
MIN_GPU_TOTAL_MIB=79000      # A100 80GB reports 81920 MiB; H100 NVL ~95830 MiB
MAX_GPU_USED_BEFORE_START_MIB=2048
MIN_DRIVER_MAJOR=580
MIN_TMP_FREE_KB_RESTORE=12582912 # 12 GiB
MODE="${1:---start}"

QWEN_URL="http://127.0.0.1:${QWEN_PORT}/v1/models"
GATEWAY_URL="http://127.0.0.1:${GATEWAY_PORT}/health"
CONSOLE_URL="http://127.0.0.1:${CONSOLE_PORT}/api/status"
GEMMA_URL="http://127.0.0.1:${GEMMA_PORT}/v1/models"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
fail() {
  echo "ERROR: $*" >&2
  echo "Rollback: nothing on /workspace was deleted or overwritten. Fix the cause above and re-run; healthy services are reused." >&2
  exit 1
}
healthy() { curl -fsS --max-time 3 "$1" >/dev/null 2>&1; }
port_listening() { ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"; }
vllm_pid_for_port() { pgrep -f "vllm serve .*--port $1( |\$)" | head -n1 || true; }

gpu_query() {
  # Prints "total_mib used_mib" for GPU 0, or nothing if nvidia-smi is unavailable.
  nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits 2>/dev/null \
    | head -n1 | tr -d ' ' | tr ',' ' '
}

driver_major() {
  local ver
  ver="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1 || true)"
  echo "${ver%%.*}"
}

qwen_on_port_is_expected() {
  curl -fsS --max-time 3 "$QWEN_URL" 2>/dev/null | grep -q "$QWEN_REVISION"
}

# --- preflight checks (shared by --preflight and --start) -------------------
PREFLIGHT_FAILS=()
rc() { "$@" >/dev/null 2>&1 && echo 0 || echo 1; }
check() { # name, ok(0/1), detail
  if [[ "$2" == 0 ]]; then printf '  PASS  %-28s %s\n' "$1" "$3"; else printf '  FAIL  %-28s %s\n' "$1" "$3"; PREFLIGHT_FAILS+=("$1: $3"); fi
}

operator_status() {
  # $1 is "--check" or empty. Stdout is one JSON object and contains no secrets.
  local backup=()
  local mode=()
  if [[ -n "${1:-}" ]]; then
    mode=("$1")
  fi
  if [[ -n "${OPERATOR_BACKUP_DIR:-}" ]]; then
    backup=(--backup-dir "$OPERATOR_BACKUP_DIR")
  elif findmnt -n -o FSTYPE /workspace 2>/dev/null | grep -qx fuse.geesefs; then
    backup=(--backup-dir /workspace/platform-state/operator-backups)
  fi
  PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" "$CONSOLE_PYTHON" -m ops.platform_state "${mode[@]}" --live-dir "$OPERATOR_AUTH_DIR" "${backup[@]}"
}

run_preflight() {
  local need_restore=0 need_qwen_start=0 total used drv free_kb
  [[ -x "$QWEN_ENV/bin/vllm" ]] || need_restore=1
  if ! healthy "$QWEN_URL"; then need_qwen_start=1; fi

  check "global-volume-mounted" "$(rc findmnt -n /workspace)" "/workspace"
  check "qwen-weights" "$(rc test -f "$MODEL/model.safetensors-00011-of-00011.safetensors")" "$MODEL"
  check "qwen-runtime-archive" "$(rc test -f "$QWEN_ARCHIVE_DIR/vllm-qwen-env.tar.zst" -a -f "$QWEN_ARCHIVE_DIR/SHA256SUMS")" "$QWEN_ARCHIVE_DIR"
  check "rag-parser-wheels" "$(rc test -f /workspace/runtime-setup/rag-wheelhouse/XLSX-SHA256SUMS)" "/workspace/runtime-setup/rag-wheelhouse"

  drv="$(driver_major)"
  if [[ "$drv" =~ ^[0-9]+$ ]] && (( drv >= MIN_DRIVER_MAJOR )); then check "nvidia-driver>=${MIN_DRIVER_MAJOR}" 0 "major $drv"
  else check "nvidia-driver>=${MIN_DRIVER_MAJOR}" 1 "found '${drv:-none}'. Archived runtime needs CUDA-13-capable driver. Deploy on a host with driver >=580 (RunPod CUDA 13 filter)."; fi

  read -r total used <<<"$(gpu_query)" || true
  if [[ "${total:-}" =~ ^[0-9]+$ ]] && (( total >= MIN_GPU_TOTAL_MIB )); then check "gpu-vram>=80GB" 0 "${total} MiB total"
  else check "gpu-vram>=80GB" 1 "found '${total:-none}' MiB; Qwen3.5-27B BF16 needs an 80GB-class GPU"; fi

  if (( need_qwen_start )); then
    if [[ -n "$(vllm_pid_for_port "$QWEN_PORT")" ]]; then
      check "qwen-not-already-starting" 1 "a vLLM process for :$QWEN_PORT exists but is not healthy yet (still loading?). Wait and re-run; see $DIAG/qwen-vllm.log"
    else
      check "qwen-not-already-starting" 0 "no vLLM process on :$QWEN_PORT"
    fi
    if [[ "${used:-}" =~ ^[0-9]+$ ]] && (( used <= MAX_GPU_USED_BEFORE_START_MIB )); then check "gpu-free-before-start" 0 "${used} MiB used"
    else check "gpu-free-before-start" 1 "${used:-?} MiB already used on the GPU (Gemma or another vLLM?). Only one model may use the GPU. Inspect: nvidia-smi --query-compute-apps=pid,used_memory --format=csv"; fi
    if port_listening "$QWEN_PORT"; then check "qwen-port-free" 1 ":$QWEN_PORT is occupied by something that is not a healthy Qwen"
    else check "qwen-port-free" 0 ":$QWEN_PORT"; fi
  else
    if qwen_on_port_is_expected; then check "qwen-on-port-is-qwen" 0 ":$QWEN_PORT serves revision $QWEN_REVISION (reuse)"
    else check "qwen-on-port-is-qwen" 1 ":$QWEN_PORT answers but does not serve $QWEN_REVISION"; fi
  fi

  if healthy "$GEMMA_URL"; then check "gemma-not-loaded" 1 "Gemma is serving on :$GEMMA_PORT; stop it first (one GPU model at a time)"
  else check "gemma-not-loaded" 0 ":$GEMMA_PORT down"; fi

  for pair in "gateway:$GATEWAY_PORT:$GATEWAY_URL" "console:$CONSOLE_PORT:$CONSOLE_URL"; do
    IFS=: read -r name port _ <<<"$pair"
    url="${pair#*:*:}"
    if healthy "$url"; then check "${name}-port" 0 ":$port healthy (reuse)"
    elif port_listening "$port"; then check "${name}-port" 1 ":$port is occupied by an unhealthy or foreign process"
    else check "${name}-port" 0 ":$port free"; fi
  done

  if (( need_restore )); then
    mkdir -p "$(dirname "$QWEN_ENV")"
    free_kb=$(df -Pk "$(dirname "$QWEN_ENV")" | awk 'END {print $4}')
    if [[ "$free_kb" =~ ^[0-9]+$ ]] && (( free_kb >= MIN_TMP_FREE_KB_RESTORE )); then check "local-disk-for-restore" 0 "$((free_kb/1048576)) GiB free"
    else check "local-disk-for-restore" 1 "need >=12 GiB free under $(dirname "$QWEN_ENV") to restore the runtime"; fi
  else
    check "qwen-runtime-present" 0 "$QWEN_ENV"
  fi

  if operator_status --check >/dev/null; then
    check "operators-ready" 0 "a private administrator can be loaded or restored. There is no default password."
  else
    check "operators-ready" 1 "operator store is missing or not private. Provision with scripts/provision_console_operator.py into $OPERATOR_AUTH_DIR. There is no default password."
  fi
}

if [[ "$MODE" == "--check" ]]; then
  printf 'Global Volume /workspace: '; findmnt -n /workspace >/dev/null 2>&1 && echo OK || echo MISSING
  printf 'Qwen weights: '; [[ -f "$MODEL/config.json" ]] && echo OK || echo MISSING
  printf 'Qwen archive: '; [[ -f "$QWEN_ARCHIVE_DIR/vllm-qwen-env.tar.zst" ]] && echo OK || echo MISSING
  printf 'Qwen env (%s): ' "$QWEN_ENV"; [[ -x "$QWEN_ENV/bin/vllm" ]] && echo PRESENT || echo MISSING
  printf 'Gemma weights (optional): '; [[ -f "$VOL/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it/config.json" ]] && echo PRESENT || echo ABSENT
  printf 'Qwen :%s: ' "$QWEN_PORT"; healthy "$QWEN_URL" && echo HEALTHY || echo DOWN
  printf 'Gateway :%s: ' "$GATEWAY_PORT"; healthy "$GATEWAY_URL" && echo HEALTHY || echo DOWN
  printf 'Console :%s: ' "$CONSOLE_PORT"; healthy "$CONSOLE_URL" && echo HEALTHY || echo DOWN
  printf 'Gemma :%s: ' "$GEMMA_PORT"; healthy "$GEMMA_URL" && echo HEALTHY || echo DOWN
  printf 'NVIDIA driver: %s\n' "$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1 || echo unknown)"
  printf 'GPU memory (total used MiB): %s\n' "$(gpu_query || echo unknown)"
  exit 0
fi

if [[ "$MODE" == "--preflight" ]]; then
  echo "Preflight (no services started, nothing restored):"
  run_preflight
  if (( ${#PREFLIGHT_FAILS[@]} )); then echo "PREFLIGHT_FAIL (${#PREFLIGHT_FAILS[@]})"; exit 1; fi
  echo "PREFLIGHT_PASS"
  exit 0
fi

[[ "$MODE" == "--start" ]] || fail "Usage: $0 [--start|--check|--preflight]"

mkdir -p "$DIAG"
LOCK="/tmp/ai-platform-start-${GATEWAY_PORT}.lock"
# Long-lived children are started with 9>&- so the lock is released when this script exits.
exec 9>"$LOCK"
flock -n 9 || fail "Another start for gateway :$GATEWAY_PORT is already running (lock $LOCK)."

log "Preflight"
run_preflight
if (( ${#PREFLIGHT_FAILS[@]} )); then
  printf '  - %s\n' "${PREFLIGHT_FAILS[@]}" >&2
  fail "Preflight failed (${#PREFLIGHT_FAILS[@]} check(s)); nothing was started."
fi

[[ -f "$REPO_ROOT/api/local_gateway.py" ]] || fail "Platform source missing at $REPO_ROOT. Run /workspace/ai-platform-release/START.sh (clones GitHub or restores the volume snapshot)."

if [[ ! -x "$QWEN_ENV/bin/vllm" ]]; then
  log "Restoring Qwen runtime from Global Volume archive into $QWEN_ENV (never onto /workspace)"
  QWEN_VLLM_ENV="$QWEN_ENV" bash "$REPO_ROOT/ops/restore-qwen-runtime.sh" \
    || fail "Archive restore failed. /workspace archives were not modified. Check $QWEN_ARCHIVE_DIR/SHA256SUMS and local disk space."
fi

export TMPDIR=/tmp
export VLLM_RPC_BASE_PATH=/tmp
# Bundled NVIDIA CUDA libs (cudart 13 etc.) must be on LD_LIBRARY_PATH for the archived env.
_ld_extra=""
for sp in "$QWEN_ENV"/lib/python3.*/site-packages/nvidia; do
  [[ -d "$sp" ]] && _ld_extra="$(find "$sp" -type f -name 'lib*.so*' -printf '%h\n' 2>/dev/null | sort -u | tr '\n' ':')${_ld_extra}"
done
[[ -n "$_ld_extra" ]] && export LD_LIBRARY_PATH="${_ld_extra}${LD_LIBRARY_PATH:-}"
unset _ld_extra

if ! "$QWEN_ENV/bin/python" - <<'PY'
import sys, torch
ok = torch.cuda.is_available()
print(f"torch={torch.__version__} cuda={torch.version.cuda} available={ok}")
sys.exit(0 if ok else 1)
PY
then
  fail "Qwen runtime cannot see the GPU (CUDA runtime/driver mismatch). Use a Pod with NVIDIA driver >=580."
fi

if healthy "$QWEN_URL"; then
  log "Reusing healthy Qwen on :$QWEN_PORT"
else
  read -r GPU_TOTAL _ <<<"$(gpu_query)"
  if [[ -n "${QWEN_GPU_MEM_UTIL:-}" ]]; then UTIL="$QWEN_GPU_MEM_UTIL"
  elif (( GPU_TOTAL < 90000 )); then UTIL=0.90   # 80GB class (A100): value proven on A100 80GB PCIe
  else UTIL=0.92; fi                              # >=94GB class (H100 NVL): value proven on H100 NVL
  log "Starting Qwen on 127.0.0.1:$QWEN_PORT (gpu_mem_util=$UTIL max_model_len=$QWEN_MAX_MODEL_LEN max_num_seqs=$QWEN_MAX_NUM_SEQS)"
  # max-num-seqs must stay below the available Mamba cache blocks for Qwen3.5 or the engine aborts.
  # FlashInfer JIT invokes `ninja` from PATH. A fresh Pod image does not ship it; the archived env does.
  nohup env PATH="$QWEN_ENV/bin:${PATH:-}" VLLM_DO_NOT_TRACK=1 "$QWEN_ENV/bin/python" "$QWEN_ENV/bin/vllm" serve "$MODEL" \
    --host 127.0.0.1 --port "$QWEN_PORT" \
    --trust-remote-code \
    --language-model-only \
    --reasoning-parser qwen3 \
    --max-model-len "$QWEN_MAX_MODEL_LEN" \
    --max-num-seqs "$QWEN_MAX_NUM_SEQS" \
    --gpu-memory-utilization "$UTIL" \
    --default-chat-template-kwargs '{"enable_thinking": false}' \
    >"$DIAG/qwen-vllm.log" 2>&1 </dev/null 9>&- &
  QWEN_PID=$!
  echo "$QWEN_PID" >"$DIAG/qwen-vllm.pid"
  log "Waiting up to ${QWEN_READY_TIMEOUT_S}s for Qwen (cold load from the Global Volume can take 10-25 minutes)"
  waited=0
  until healthy "$QWEN_URL"; do
    if ! kill -0 "$QWEN_PID" 2>/dev/null; then
      tail -n 40 "$DIAG/qwen-vllm.log" >&2 || true
      fail "Qwen exited during startup; see $DIAG/qwen-vllm.log"
    fi
    (( waited >= QWEN_READY_TIMEOUT_S )) && fail "Qwen not ready after ${QWEN_READY_TIMEOUT_S}s (process $QWEN_PID still running; re-run later to reuse it)"
    sleep 10; waited=$((waited + 10))
  done
  log "Qwen ready after ~${waited}s"
fi

umask 077
if [[ ! -s "$KEY" ]]; then
  mkdir -p "$(dirname "$KEY")"
  openssl rand -base64 48 | tr -d '\n' >"$KEY"
  chmod 600 "$KEY"
  log "Created ephemeral API key file $KEY"
fi

# Document Q&A parsers (PDF/XLSX) from verified wheels on the Global Volume into Pod-local RAG_DEPS.
if ! PYTHONPATH="$RAG_DEPS" "$QWEN_ENV/bin/python" -c 'import pypdf, openpyxl' 2>/dev/null; then
  log "Installing PDF/XLSX parsers into $RAG_DEPS from /workspace/runtime-setup/rag-wheelhouse"
  RAG_SETUP_PYTHON="$QWEN_ENV/bin/python" RAG_DEPS_DIR="$RAG_DEPS" bash "$REPO_ROOT/rag/setup_pdf_support.sh" >>"$DIAG/rag-deps.log" 2>&1 \
    || fail "PDF parser setup failed; see $DIAG/rag-deps.log"
  RAG_SETUP_PYTHON="$QWEN_ENV/bin/python" RAG_DEPS_DIR="$RAG_DEPS" bash "$REPO_ROOT/rag/setup_xlsx_support.sh" >>"$DIAG/rag-deps.log" 2>&1 \
    || fail "XLSX parser setup failed; see $DIAG/rag-deps.log"
fi

wait_healthy() { # url, pid, seconds, logfile
  local i
  for ((i = 0; i < $3; i++)); do
    healthy "$1" && return 0
    kill -0 "$2" 2>/dev/null || { tail -n 30 "$4" >&2 || true; return 1; }
    sleep 1
  done
  return 1
}

if healthy "$GATEWAY_URL"; then
  log "Reusing healthy gateway on :$GATEWAY_PORT"
else
  log "Starting gateway on :$GATEWAY_PORT -> Qwen :$QWEN_PORT"
  nohup env \
    PLATFORM_HOST=127.0.0.1 \
    PLATFORM_PORT="$GATEWAY_PORT" \
    PLATFORM_API_KEY="$(cat "$KEY")" \
    PLATFORM_API_KEY_FILE="$KEY" \
    VLLM_UPSTREAM_URL="http://127.0.0.1:${QWEN_PORT}/v1" \
    PLATFORM_MODEL_REGISTRY="$REPO_ROOT/models/registry.yaml" \
    PLATFORM_DEFAULT_MODEL_ID=qwen3.5-27b \
    RAG_DOCS_DIR="$VOL/rag-demo-docs" \
    RAG_MANAGED_DOCS_DIR="$RAG_MANAGED" \
    PYTHONPATH="$REPO_ROOT/api:$REPO_ROOT/models:$REPO_ROOT/rag:$RAG_DEPS" \
    "$QWEN_ENV/bin/python" "$REPO_ROOT/api/local_gateway.py" \
    >"$DIAG/gateway.log" 2>&1 </dev/null 9>&- &
  GW_PID=$!
  echo "$GW_PID" >"$DIAG/gateway.pid"
  wait_healthy "$GATEWAY_URL" "$GW_PID" 30 "$DIAG/gateway.log" || fail "Gateway :$GATEWAY_PORT failed; see $DIAG/gateway.log"
fi

if healthy "$CONSOLE_URL"; then
  log "Reusing healthy console on :$CONSOLE_PORT"
else
  log "Preparing the private operator store before the console starts"
  operator_status || fail "Operator store is not ready. Qwen and the gateway were not stopped. Provision an administrator with scripts/provision_console_operator.py. There is no default password."
  log "Starting console on :$CONSOLE_PORT"
  nohup env \
    WEB_HOST=127.0.0.1 \
    WEB_PORT="$CONSOLE_PORT" \
    PLATFORM_GATEWAY_URL="http://127.0.0.1:${GATEWAY_PORT}" \
    PLATFORM_API_KEY_FILE="$KEY" \
    PLATFORM_MODEL_ID=qwen3.5-27b \
    OPERATOR_AUTH_DIR="$OPERATOR_AUTH_DIR" \
    MICROSOFT_CLIENT_ID="${MICROSOFT_CLIENT_ID:-}" \
    MICROSOFT_TENANT="${MICROSOFT_TENANT:-common}" \
    MICROSOFT_REDIRECT_URI="${MICROSOFT_REDIRECT_URI:-http://127.0.0.1:18080/api/microsoft/callback}" \
    MICROSOFT_TOKEN_FILE="${MICROSOFT_TOKEN_FILE:-/tmp/microsoft-365-token.json}" \
    RAG_DOCS_DIR="${RAG_DOCS_DIR:-$VOL/rag-demo-docs}" \
    RAG_MANAGED_DOCS_DIR="$RAG_MANAGED" \
    /usr/bin/python3 "$REPO_ROOT/web/server.py" \
    >"$DIAG/console.log" 2>&1 </dev/null 9>&- &
  WEB_PID=$!
  echo "$WEB_PID" >"$DIAG/console.pid"
  wait_healthy "$CONSOLE_URL" "$WEB_PID" 30 "$DIAG/console.log" || fail "Console :$CONSOLE_PORT failed; see $DIAG/console.log"
fi

log "FIRST_RELEASE_READY console=:$CONSOLE_PORT gateway=:$GATEWAY_PORT qwen=:$QWEN_PORT"
log "SSH tunnel example: ssh -N -L 18080:127.0.0.1:${CONSOLE_PORT} -p <tcp-port> -i <key> root@<pod-ip>"
