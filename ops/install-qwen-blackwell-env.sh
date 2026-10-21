#!/usr/bin/env bash
# Isolated Qwen runtime for RTX PRO 6000 Blackwell (compute capability 12.0).
# Does not modify /tmp/vllm-qwen-env, /tmp/vllm-clean-env, or the saved A100 archive.
#
# vLLM 0.32.0 publishes a CUDA 12.9 wheel and requires torch==2.13.0.
# torch 2.13.0+cu126 has no compute-capability 12.0 kernels.
# The matching CUDA 13.0 vLLM wheel returned HTTP 404 on 2026-10-21, so this
# install does not mix a CUDA 12.9 vLLM binary with a CUDA 13 PyTorch build.
# Pins live in ops/blackwell-runtime.lock.
#
# https://docs.vllm.ai/en/stable/getting_started/installation/gpu/
set -Eeuo pipefail
umask 077

ENV_DIR="${QWEN_BLACKWELL_ENV:-/tmp/vllm-qwen-blackwell-env}"
A100_ENV=/tmp/vllm-qwen-env
GEMMA_ENV=/tmp/vllm-clean-env
A100_ARCHIVE=/workspace/runtime-setup/qwen-vllm
LOCK="$(cd "$(dirname "$0")" && pwd)/blackwell-runtime.lock"
MIN_FREE_KB=20971520 # 20 GiB for the wheels
MODE="${1:---install}"

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

[[ -f "$LOCK" ]] || fail "missing $LOCK"
# shellcheck disable=SC1090
source "$LOCK"
[[ "$torch_backend" == "cu129" && "$torch" == "2.13.0+cu129" && "$vllm" == "0.32.0+cu129" ]] || fail "lockfile is not the CUDA 12.9 Blackwell pin"
[[ "$rejected_torch" == "2.13.0+cu126" ]] || fail "lockfile must keep rejecting torch 2.13.0+cu126"
[[ "$vllm_wheel_sha256" =~ ^[0-9a-f]{64}$ ]] || fail "lockfile wheel checksum is not sha256"

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

version = torch.__version__
cuda = str(torch.version.cuda or "")
if version.startswith("2.13.0+cu126") or cuda.startswith("12.6"):
    sys.exit(f"refusing torch {version} cuda {cuda}; compute capability 12.0 is absent")
if not version.startswith("2.13.0+cu129"):
    sys.exit(f"torch {version} is not the pinned 2.13.0+cu129 build")
if not cuda.startswith("12.9"):
    sys.exit(f"torch CUDA {cuda!r} is not CUDA 12.9")
if not vllm.__version__.startswith("0.32.0"):
    sys.exit(f"vllm {vllm.__version__} is not 0.32.0")
if not torch.cuda.is_available():
    sys.exit("torch.cuda.is_available() is false")
major, minor = torch.cuda.get_device_capability()
if major < 12:
    sys.exit(f"compute capability {major}.{minor} is not Blackwell")
name = torch.cuda.get_device_name(0)
# A one-element copy proves a kernel for this device can launch.
torch.zeros(1, device="cuda").cpu()
py = ".".join(str(part) for part in sys.version_info[:3])
print(f"python={py}")
print(f"vllm={vllm.__version__}")
print(f"torch={version} cuda={cuda}")
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
[[ "$DRIVER_MAJOR" =~ ^[0-9]+$ && "$DRIVER_MAJOR" -ge "$minimum_driver_major" ]] || fail "NVIDIA driver major $DRIVER_MAJOR is below $minimum_driver_major"
CC="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -n1 | tr -d ' ')"
CC_MAJOR="${CC%%.*}"
[[ "$CC_MAJOR" =~ ^[0-9]+$ && "$CC_MAJOR" -ge "$minimum_compute_capability" ]] || fail "GPU compute capability $CC is not 12.0 or newer; leaving the A100 runtime unchanged"

if [[ -x "$ENV_DIR/bin/vllm" ]]; then
  log "Reusing $ENV_DIR"
  python_check
  exit 0
fi
if [[ -e "$ENV_DIR" ]]; then
  fail "$ENV_DIR exists but is incomplete; inspect it and remove it manually. Nothing was deleted."
fi

command -v uv >/dev/null 2>&1 || fail "uv is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required"
mkdir -p "$(dirname "$ENV_DIR")"
FREE_KB="$(df -Pk "$(dirname "$ENV_DIR")" | awk 'END {print $4}')"
[[ "$FREE_KB" =~ ^[0-9]+$ && "$FREE_KB" -ge "$MIN_FREE_KB" ]] || fail "need at least 20 GiB free for the CUDA 12.9 environment"

log "Creating $ENV_DIR (A100 env $A100_ENV and archive $A100_ARCHIVE are not modified)"
uv venv --python "${QWEN_BLACKWELL_PYTHON:-3.12}" "$ENV_DIR"
"$ENV_DIR/bin/python" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 15) else 1)' || fail "Blackwell runtime needs Python >=3.11 and <3.15"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
log "Downloading the pinned vLLM $vllm wheel"
curl -fL --retry 3 --retry-delay 2 -o "$tmpdir/vllm.whl" "$vllm_wheel_url"
echo "${vllm_wheel_sha256}  $tmpdir/vllm.whl" | sha256sum -c -
log "Installing vLLM $vllm with torch $torch"
uv pip install -p "$ENV_DIR/bin/python" "$tmpdir/vllm.whl" "torch==2.13.0" "torchaudio==2.11.0" "torchvision==0.28.0" --torch-backend=cu129
log "Installing precompiled FlashInfer kernels for this CUDA build"
"$ENV_DIR/bin/vllm" download-kernels
python_check | tee "$ENV_DIR/BLACKWELL_MANIFEST.txt"
log "Blackwell runtime is ready at $ENV_DIR. It was not archived onto /workspace."
