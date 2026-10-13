#!/usr/bin/env bash
# Restore archived Qwen venv onto Pod-local disk (default /tmp/vllm-qwen-env).
# Refuses overwrite. Never extracts onto the Global Volume. Does not start vLLM.
set -Eeuo pipefail

BACKUP_DIR=/workspace/runtime-setup/qwen-vllm
ARCHIVE="$BACKUP_DIR/vllm-qwen-env.tar.zst"
TARGET="${QWEN_VLLM_ENV:-/tmp/vllm-qwen-env}"
PARENT="$(dirname "$TARGET")"
MIN_FREE_KB=12582912 # 12 GiB

[[ -f "$ARCHIVE" && -f "$BACKUP_DIR/SHA256SUMS" ]] || {
  echo "ERROR: Qwen runtime archive/manifest missing under $BACKUP_DIR" >&2
  exit 2
}
command -v zstd >/dev/null || { echo "ERROR: zstd required" >&2; exit 3; }

case "$TARGET" in
  /workspace/*) echo "ERROR: refusing to restore a live environment onto the Global Volume ($TARGET)" >&2; exit 7 ;;
esac

if [[ -e "$TARGET" ]]; then
  echo "ERROR: $TARGET already exists. Refusing to overwrite." >&2
  exit 4
fi

mkdir -p "$PARENT"
FREE_KB=$(df -Pk "$PARENT" | awk 'END {print $4}')
[[ "$FREE_KB" =~ ^[0-9]+$ && "$FREE_KB" -ge "$MIN_FREE_KB" ]] || {
  echo "ERROR: Need at least 12 GiB free under $PARENT" >&2
  df -h "$PARENT"
  exit 5
}

(cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)
zstd -t "$ARCHIVE"

# The archive's top-level directory is vllm-qwen-env/.
STAGE="$(mktemp -d "$PARENT/.qwen-restore.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
echo "Extracting $ARCHIVE into $PARENT ..."
tar -I 'zstd -d' -xf "$ARCHIVE" -C "$STAGE"
[[ -x "$STAGE/vllm-qwen-env/bin/vllm" ]] || { echo "ERROR: restored vllm binary missing" >&2; exit 6; }
mv "$STAGE/vllm-qwen-env" "$TARGET"
echo "Restore complete: $TARGET"
echo "Next: bash ops/start-first-release.sh --start (only when the GPU is free / Gemma stopped)."
