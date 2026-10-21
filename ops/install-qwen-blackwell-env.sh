#!/usr/bin/env bash
# Isolated CUDA 13 runtime for RTX PRO 6000 Blackwell (compute capability 12.0).
# Does not modify /tmp/vllm-qwen-env, /tmp/vllm-clean-env, or the saved A100 archive.
#
# Official route: https://docs.vllm.ai/en/stable/getting_started/installation/gpu/
#   uv pip install vllm --torch-backend=cu130
#   vllm download-kernels
# torch 2.13.0+cu126 does not ship kernels for compute capability 12.0.
set -Eeuo pipefail
umask 077

ENV_DIR="${QWEN_BLACKWELL_ENV:-/tmp/vllm-qwen-blackwell-env}"
A100_ENV=/tmp/vllm-qwen-env
GEMMA_ENV=/tmp/vllm-clean-env
A100_ARCHIVE=/workspace/runtime-setup/qwen-vllm
MIN_DRIVER_MAJOR=580
MIN_CC_MAJOR=12
MIN_FREE_KB=20971520 # 20 GiB for the CUDA 13 wheels
MODE="${1:---install}"

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

case "$ENV_DIR" in
  "$A100_ENV"|"$GEMMA_ENV") fail "refusing to install into $ENV_DIR" ;;
  /workspace/*) fail "refusing to install a live environment onto the volume ($ENV_DIR)" ;;
esac
[[ "$ENV_DIR" != "$A100_ARCHIVE" ]] || fail "refusing to replace the A100 runtime archive"

python_check() {
  "$ENV_DIR/bin/python" - <<'PY'
import sys
import torch
import vllm

cuda = str(torch.version.cuda or "")
if not cuda.startswith("13."):
    sys.exit(f"torch CUDA {cuda!r} is not a CUDA 13 build")
if not torch.cuda.is_available():
    sys.exit("torch.cuda.is_available() is false")
major, minor = torch.cuda.get_device_capability()
if major < 12:
    sys.exit(f"compute capability {major}.{minor} is not Blackwell")
name = torch.cuda.get_device_name(0)
# A one-element copy proves a kernel for this device can launch.
torch.zeros(1, device="cuda").cpu()
print(f"vllm={vllm.__version__}")
print(f"torch={torch.__version__} cuda={cuda}")
print(f"gpu={name} cc={major}.{minor}")
PY
}

if [[ "$MODE" == "--check" ]]; then
  [[ -x "$ENV_DIR/bin/python" ]] || fail "missing $ENV_DIR/bin/python"
  python_check
  exit 0
fi

[[ "$MODE" == "--install" ]] || fail "usage: $0 [--install|--check]"

command -v nvidia-smi >/dev/null 2>&1 || fail "nvidia-smi is required"
DRIVER_MAJOR="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1 | cut -d. -f1)"
[[ "$DRIVER_MAJOR" =~ ^[0-9]+$ && "$DRIVER_MAJOR" -ge "$MIN_DRIVER_MAJOR" ]] || fail "NVIDIA driver major $DRIVER_MAJOR is below $MIN_DRIVER_MAJOR"
CC="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -n1 | tr -d ' ')"
CC_MAJOR="${CC%%.*}"
[[ "$CC_MAJOR" =~ ^[0-9]+$ && "$CC_MAJOR" -ge "$MIN_CC_MAJOR" ]] || fail "GPU compute capability $CC is not 12.0 or newer; leaving the A100 runtime unchanged"

if [[ -x "$ENV_DIR/bin/vllm" ]]; then
  log "Reusing $ENV_DIR"
  python_check
  exit 0
fi
if [[ -e "$ENV_DIR" ]]; then
  fail "$ENV_DIR exists but is incomplete; inspect it and remove it manually. Nothing was deleted."
fi

command -v uv >/dev/null 2>&1 || fail "uv is required"
mkdir -p "$(dirname "$ENV_DIR")"
FREE_KB="$(df -Pk "$(dirname "$ENV_DIR")" | awk 'END {print $4}')"
[[ "$FREE_KB" =~ ^[0-9]+$ && "$FREE_KB" -ge "$MIN_FREE_KB" ]] || fail "need at least 20 GiB free for the CUDA 13 environment"

log "Creating $ENV_DIR (A100 env $A100_ENV and archive $A100_ARCHIVE are not modified)"
uv venv "$ENV_DIR"
log "Installing vLLM with the CUDA 13.0 PyTorch backend"
uv pip install -p "$ENV_DIR/bin/python" vllm --torch-backend=cu130
log "Installing precompiled FlashInfer kernels for this CUDA build"
"$ENV_DIR/bin/vllm" download-kernels
python_check | tee "$ENV_DIR/BLACKWELL_MANIFEST.txt"
log "Blackwell runtime is ready at $ENV_DIR. It was not archived onto /workspace."
