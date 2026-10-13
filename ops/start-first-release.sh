#!/usr/bin/env bash
# One/two-command first-release bring-up: Qwen primary on :8002 + main gateway :8010 + console :8080.
# Does not download weights. Does not start Gemma. Does not create paid resources.
set -Eeuo pipefail

REPO_ROOT="${REPO_ROOT:-/tmp/AI-PLAYBOOK}"
VOL=/workspace
SETUP="$VOL/runtime-setup"
QWEN_ARCHIVE_DIR="$SETUP/qwen-vllm"
QWEN_ENV="${QWEN_VLLM_ENV:-/tmp/vllm-qwen-env}"
MODEL="$VOL/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654"
KEY="${PLATFORM_API_KEY_FILE:-/tmp/platform-gateway.key}"
DIAG="$VOL/platform-diagnostics/first-release"
MODE="${1:---start}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }
healthy() { curl -fsS --max-time 3 "$1" >/dev/null 2>&1; }

mkdir -p "$DIAG"
umask 077

[[ -f "$MODEL/config.json" ]] || fail "Qwen model missing at $MODEL"
[[ -f "$QWEN_ARCHIVE_DIR/vllm-qwen-env.tar.zst" ]] || fail "Qwen runtime archive missing"
[[ -f "$VOL/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it/config.json" ]] || fail "Global Volume Gemma marker missing"

if [[ "$MODE" == "--check" ]]; then
  printf 'Qwen weights: '; [[ -f "$MODEL/config.json" ]] && echo OK
  printf 'Qwen env: '; [[ -x "$QWEN_ENV/bin/vllm" ]] && echo PRESENT || echo MISSING
  printf 'Qwen :8002: '; healthy http://127.0.0.1:8002/v1/models && echo HEALTHY || echo DOWN
  printf 'Gateway :8010: '; healthy http://127.0.0.1:8010/health && echo HEALTHY || echo DOWN
  printf 'Console :8080: '; healthy http://127.0.0.1:8080/api/status && echo HEALTHY || echo DOWN
  printf 'Gemma :8000: '; healthy http://127.0.0.1:8000/v1/models && echo HEALTHY || echo DOWN
  exit 0
fi

[[ "$MODE" == "--start" ]] || fail "Usage: $0 [--start|--check]"

if healthy http://127.0.0.1:8000/v1/models; then
  fail "Gemma is loaded on :8000. Stop it before starting Qwen first-release (one GPU)."
fi

if [[ ! -x "$QWEN_ENV/bin/vllm" ]]; then
  log "Restoring Qwen runtime from Global Volume archive"
  bash "$(dirname "$0")/restore-qwen-runtime.sh"
fi

export PATH="$QWEN_ENV/bin:$PATH"
export TMPDIR=/tmp
export VLLM_RPC_BASE_PATH=/tmp
# Bundled NVIDIA CUDA libs (cudart 13 etc.) must be on LD_LIBRARY_PATH for archived envs.
if [[ -d "$QWEN_ENV/lib" ]]; then
  _ld_extra="$(find "$QWEN_ENV/lib" -type f \( -name 'libcudart.so*' -o -name 'libcuda.so*' \) -printf '%h\n' 2>/dev/null | sort -u | tr '\n' ':')"
  # Prefer site-packages/nvidia/*/lib layout used by pip CUDA wheels.
  if [[ -d "$QWEN_ENV/lib/python3.12/site-packages/nvidia" ]]; then
    _ld_extra="$(find "$QWEN_ENV/lib/python3.12/site-packages/nvidia" -type f -name 'lib*.so*' -printf '%h\n' 2>/dev/null | sort -u | tr '\n' ':')${_ld_extra}"
  elif [[ -d "$QWEN_ENV/lib/python3.11/site-packages/nvidia" ]]; then
    _ld_extra="$(find "$QWEN_ENV/lib/python3.11/site-packages/nvidia" -type f -name 'lib*.so*' -printf '%h\n' 2>/dev/null | sort -u | tr '\n' ':')${_ld_extra}"
  fi
  if [[ -n "${_ld_extra}" ]]; then
    export LD_LIBRARY_PATH="${_ld_extra}${LD_LIBRARY_PATH:-}"
  fi
  unset _ld_extra
fi
# Driver gate: archived cu130/cu13 runtimes need NVIDIA driver ~580+.
# On driver 570 / CUDA 12.8 hosts, use a host-matched venv (see ops/_install_qwen_env_cu128.py).
DRIVER_VER="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1 || true)"
log "NVIDIA driver: ${DRIVER_VER:-unknown}"
if ! "$QWEN_ENV/bin/python" - <<'PY'
import torch, sys
ok = torch.cuda.is_available()
print(f"torch={torch.__version__} cuda={torch.version.cuda} available={ok}")
sys.exit(0 if ok else 1)
PY
then
  fail "Qwen env cannot see the GPU (likely CUDA runtime/driver mismatch). On CUDA 12.8 / driver 570 hosts, rebuild with ops/_install_qwen_env_cu128.py rather than extracting the cu130 archive."
fi

if ! healthy http://127.0.0.1:8002/v1/models; then
  log "Starting Qwen vLLM on 127.0.0.1:8002"
  # max-num-seqs must stay below available Mamba cache blocks on Qwen3.5 (else engine dies).
  nohup env VLLM_DO_NOT_TRACK=1 "$QWEN_ENV/bin/python" "$QWEN_ENV/bin/vllm" serve "$MODEL" \
    --host 127.0.0.1 --port 8002 \
    --trust-remote-code \
    --language-model-only \
    --reasoning-parser qwen3 \
    --max-model-len 8192 \
    --max-num-seqs 256 \
    --gpu-memory-utilization 0.92 \
    --default-chat-template-kwargs '{"enable_thinking": false}' \
    >"$DIAG/qwen-vllm.log" 2>&1 &
  echo $! >"$DIAG/qwen-vllm.pid"
  ready=0
  for _ in $(seq 1 360); do
    if healthy http://127.0.0.1:8002/v1/models; then ready=1; break; fi
    sleep 2
  done
  [[ "$ready" == 1 ]] || fail "Qwen did not become ready; see $DIAG/qwen-vllm.log"
else
  log "Reusing healthy Qwen on :8002"
fi

if [[ ! -f "$KEY" ]]; then
  openssl rand -base64 48 | tr -d '\n' >"$KEY"
  chmod 600 "$KEY"
  log "Created ephemeral API key file $KEY"
fi

# Ensure repo checkout for gateway/console source
if [[ ! -f "$REPO_ROOT/api/local_gateway.py" ]]; then
  log "Cloning platform source into $REPO_ROOT"
  git clone --branch feature/qwen3.5-27b-integration --single-branch \
    https://github.com/henokmeron/AI-PLAYBOOK.md.git "$REPO_ROOT"
fi
if [[ -d /workspace/ai-platform-release/ops ]]; then
  mkdir -p "$REPO_ROOT/ops"
  cp -a /workspace/ai-platform-release/ops/. "$REPO_ROOT/ops/" || true
fi
if [[ -d /workspace/ai-platform-release/tree ]]; then
  cp -a /workspace/ai-platform-release/tree/. "$REPO_ROOT/" || true
fi
[[ -f "$REPO_ROOT/api/local_gateway.py" ]] || fail "Repo missing at $REPO_ROOT after clone/overlay"

# Ensure RAG parser wheels if setup scripts exist
if [[ -f "$REPO_ROOT/rag/setup_pypdf.sh" ]]; then
  bash "$REPO_ROOT/rag/setup_pypdf.sh" >>"$DIAG/rag-deps.log" 2>&1 || true
fi
if [[ -f "$REPO_ROOT/rag/setup_openpyxl.sh" ]]; then
  bash "$REPO_ROOT/rag/setup_openpyxl.sh" >>"$DIAG/rag-deps.log" 2>&1 || true
fi

if ! healthy http://127.0.0.1:8010/health; then
  log "Starting first-release gateway on :8010 → Qwen :8002"
  nohup env \
    PLATFORM_HOST=127.0.0.1 \
    PLATFORM_PORT=8010 \
    PLATFORM_API_KEY="$(cat "$KEY")" \
    PLATFORM_API_KEY_FILE="$KEY" \
    VLLM_UPSTREAM_URL=http://127.0.0.1:8002/v1 \
    PLATFORM_MODEL_REGISTRY="$REPO_ROOT/models/registry.yaml" \
    PLATFORM_DEFAULT_MODEL_ID=qwen3.5-27b \
    PYTHONPATH="$REPO_ROOT/api:$REPO_ROOT/models:$REPO_ROOT/rag${PYTHONPATH:+:$PYTHONPATH}" \
    /usr/bin/python3 "$REPO_ROOT/api/local_gateway.py" \
    >"$DIAG/gateway.log" 2>&1 &
  echo $! >"$DIAG/gateway.pid"
  sleep 2
  healthy http://127.0.0.1:8010/health || fail "Gateway :8010 failed; see $DIAG/gateway.log"
else
  log "Reusing healthy gateway on :8010"
fi

if ! healthy http://127.0.0.1:8080/api/status; then
  log "Starting first-release console on :8080"
  nohup env \
    WEB_HOST=127.0.0.1 \
    WEB_PORT=8080 \
    PLATFORM_GATEWAY_URL=http://127.0.0.1:8010 \
    PLATFORM_API_KEY_FILE="$KEY" \
    PLATFORM_MODEL_ID=qwen3.5-27b \
    /usr/bin/python3 "$REPO_ROOT/web/server.py" \
    >"$DIAG/console.log" 2>&1 &
  echo $! >"$DIAG/console.pid"
  sleep 2
  healthy http://127.0.0.1:8080/api/status || fail "Console :8080 failed; see $DIAG/console.log"
else
  log "Reusing healthy console on :8080"
fi

log "FIRST_RELEASE_READY console=http://127.0.0.1:8080 gateway=http://127.0.0.1:8010 qwen=http://127.0.0.1:8002"
log "SSH tunnel example: ssh -N -L 18080:127.0.0.1:8080 -p <tcp-port> root@<pod-ip>"
