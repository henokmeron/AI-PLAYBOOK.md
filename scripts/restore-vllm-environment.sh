#!/usr/bin/env bash
# Restore a saved vLLM environment to its original path on a compatible RunPod Pod.
# Run with: bash restore-vllm-environment.sh
# Does not start the server and refuses to overwrite an existing environment.
set -euo pipefail

export TMPDIR=/tmp
export UV_CACHE_DIR=/tmp/uv-cache
export VLLM_RPC_BASE_PATH=/tmp

BACKUP_DIR=/workspace/runtime-setup
ARCHIVE="$BACKUP_DIR/vllm-clean-env.tar.zst"
TARGET=/tmp/vllm-clean-env
MIN_FREE_KB=12582912 # 12 GiB; archive expands to about 8.42 GB

if [[ ! -d "$BACKUP_DIR" || ! -f "$ARCHIVE" ]]; then
  echo "ERROR: Global Volume backup not found at $BACKUP_DIR" >&2
  exit 2
fi

cd "$BACKUP_DIR"
sha256sum -c SHA256SUMS
zstd -t "$ARCHIVE"

if [[ -e "$TARGET" ]]; then
  echo "ERROR: $TARGET already exists. Refusing to overwrite it." >&2
  echo "Use a fresh compatible Pod/container for a restore test." >&2
  exit 3
fi

FREE_KB=$(df -Pk /tmp | tail -n 1 | tr -s ' ' | cut -d ' ' -f 4)
if [[ ! "$FREE_KB" =~ ^[0-9]+$ || "$FREE_KB" -lt "$MIN_FREE_KB" ]]; then
  echo "ERROR: Need at least 12 GiB free on /tmp for safe extraction." >&2
  df -h /tmp
  exit 4
fi

echo "Extracting environment archive to $TARGET ..."
tar -I 'zstd -d' -xf "$ARCHIVE" -C /tmp

echo "Checking vLLM version..."
"$TARGET/bin/vllm" --version

echo "Checking Python/Torch/GPU..."
"$TARGET/bin/python" -c 'import torch; print("PyTorch:", torch.__version__); print("PyTorch CUDA build:", torch.version.cuda); print("CUDA available:", torch.cuda.is_available()); print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "not detected")'

echo "Environment extraction and basic checks completed."
echo "Next: launch the vLLM server and perform /v1/models plus a chat-completion test."
