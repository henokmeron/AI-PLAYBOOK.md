#!/usr/bin/env bash
# Resumable download of Qwen/Qwen3.5-27B onto the Global Volume.
# Does not touch Gemma weights, main services, or the Gemma vLLM environment.
#
# Usage (on RunPod, with /workspace mounted):
#   bash ops/download-qwen3.5-27b.sh
#   bash ops/download-qwen3.5-27b.sh --check
set -Eeuo pipefail
umask 077

HF_ID="Qwen/Qwen3.5-27B"
REVISION="fc05daec18b0a78c049392ed2e771dde82bdf654"
VOL="${WORKSPACE_ROOT:-/workspace}"
DEST="$VOL/models/Qwen3.5-27B/$REVISION"
GEMMA_MARKER="$VOL/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it/config.json"
MODE="${1:---download}"

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

[[ -d "$VOL" && -f "$GEMMA_MARKER" ]] || fail "Global Volume or Gemma marker missing; refusing download."
[[ "$DEST" == "$VOL"/models/Qwen3.5-27B/* ]] || fail "refusing unexpected destination $DEST"

mkdir -p "$DEST" "$VOL/models/Qwen3.5-27B/manifests"
export HF_HOME="${HF_HOME:-$VOL/hf-cache}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
mkdir -p "$HF_HOME" "$HUGGINGFACE_HUB_CACHE"

expected_shards=11
# HF layout uses model.safetensors-NNNN-of-NNNN.safetensors (not only model-NNNN...).
shard_count() {
  find "$DEST" -maxdepth 1 -type f \( -name 'model.safetensors-*-of-*.safetensors' -o -name 'model-*.safetensors' \) 2>/dev/null | wc -l
}
check_complete() {
  local count
  count=$(shard_count)
  [[ -f "$DEST/config.json" && -f "$DEST/model.safetensors.index.json" && "$count" -ge "$expected_shards" ]]
}

if [[ "$MODE" == "--check" ]]; then
  if check_complete; then
    log "PASS: Qwen weights look complete under $DEST (shards=$(shard_count))"
    (cd "$DEST" && find . -type f | sort | sha256sum > "$VOL/models/Qwen3.5-27B/manifests/${REVISION}.sha256sums")
    log "Wrote checksum inventory $VOL/models/Qwen3.5-27B/manifests/${REVISION}.sha256sums"
    exit 0
  fi
  fail "Qwen download incomplete under $DEST (shards=$(shard_count)/$expected_shards)"
fi

if [[ "$MODE" != "--download" ]]; then
  echo "Usage: bash ops/download-qwen3.5-27b.sh [--download|--check]" >&2
  exit 2
fi

if check_complete; then
  log "Qwen revision already present at $DEST; skipping download."
  exec bash "$0" --check
fi

if command -v hf >/dev/null 2>&1; then
  DOWNLOAD=(hf download "$HF_ID" --revision "$REVISION" --local-dir "$DEST")
elif command -v huggingface-cli >/dev/null 2>&1; then
  DOWNLOAD=(huggingface-cli download "$HF_ID" --revision "$REVISION" --local-dir "$DEST")
else
  fail "Install Hugging Face Hub CLI (hf or huggingface-cli) in a non-Gemma env before downloading."
fi

FREE_KB=$(df -Pk "$VOL" | awk 'END {print $4}')
# ~60 GiB headroom target for BF16 weights + metadata.
[[ "$FREE_KB" =~ ^[0-9]+$ && "$FREE_KB" -ge 65000000 ]] || log "WARN: less than ~62 GiB free on $VOL; monitor download space carefully."

log "Starting resumable download of $HF_ID@$REVISION into $DEST"
"${DOWNLOAD[@]}"
check_complete || fail "Download finished but expected files are missing under $DEST"
bash "$0" --check
log "Gemma marker still present: $GEMMA_MARKER"
log "DONE"
