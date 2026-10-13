#!/usr/bin/env bash
# Restore archived Qwen venv to /tmp/vllm-qwen-env. Refuses overwrite. Does not start vLLM.
set -Eeuo pipefail

BACKUP_DIR=/workspace/runtime-setup/qwen-vllm
ARCHIVE="$BACKUP_DIR/vllm-qwen-env.tar.zst"
TARGET=/tmp/vllm-qwen-env
MIN_FREE_KB=12582912 # 12 GiB

[[ -f "$ARCHIVE" && -f "$BACKUP_DIR/SHA256SUMS" ]] || {
  echo "ERROR: Qwen runtime archive/manifest missing under $BACKUP_DIR" >&2
  exit 2
}
command -v zstd >/dev/null || { echo "ERROR: zstd required" >&2; exit 3; }

cd "$BACKUP_DIR"
sha256sum -c SHA256SUMS
zstd -t "$ARCHIVE"

if [[ -e "$TARGET" ]]; then
  echo "ERROR: $TARGET already exists. Refusing to overwrite." >&2
  exit 4
fi

FREE_KB=$(df -Pk /tmp | awk 'END {print $4}')
[[ "$FREE_KB" =~ ^[0-9]+$ && "$FREE_KB" -ge "$MIN_FREE_KB" ]] || {
  echo "ERROR: Need at least 12 GiB free on /tmp" >&2
  df -h /tmp
  exit 5
}

echo "Extracting $ARCHIVE to /tmp ..."
tar -I 'zstd -d' -xf "$ARCHIVE" -C /tmp
[[ -x "$TARGET/bin/vllm" ]] || { echo "ERROR: restored vllm binary missing" >&2; exit 6; }
echo "Restore complete. Set LD_LIBRARY_PATH for nvidia cu13 libs before starting."
echo "Next: ops/start-qwen-isolated.sh --start (only when GPU is free / Gemma stopped)."
