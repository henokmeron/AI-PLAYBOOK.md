#!/usr/bin/env bash
# Archive the working isolated Qwen venv to Global Volume.
# Does not stop services, does not copy secrets, refuses overwrite of an existing archive.
set -Eeuo pipefail

ENV_DIR="${QWEN_VLLM_ENV:-/tmp/vllm-qwen-env}"
DEST_DIR=/workspace/runtime-setup/qwen-vllm
ARCHIVE="$DEST_DIR/vllm-qwen-env.tar.zst"
MANIFEST="$DEST_DIR/runtime-manifest.txt"
FREEZE="$DEST_DIR/requirements-frozen.txt"
SUMS="$DEST_DIR/SHA256SUMS"
GLOBAL=/workspace
MODEL_MARKER="$GLOBAL/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it/config.json"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

if ! command -v findmnt >/dev/null 2>&1; then
  echo "ERROR: findmnt required" >&2
  exit 2
fi
MOUNT_TARGET="$(findmnt -T "$GLOBAL" -n -o TARGET 2>/dev/null | head -n 1 || true)"
[[ "$MOUNT_TARGET" == "$GLOBAL" ]] || { echo "ERROR: $GLOBAL is not a mount point" >&2; exit 3; }
[[ -f "$MODEL_MARKER" ]] || { echo "ERROR: Gemma marker missing; refusing write" >&2; exit 3; }
[[ -x "$ENV_DIR/bin/vllm" ]] || { echo "ERROR: Qwen env missing at $ENV_DIR" >&2; exit 4; }
command -v zstd >/dev/null || { echo "ERROR: zstd required" >&2; exit 5; }

if [[ -e "$ARCHIVE" ]]; then
  echo "ERROR: $ARCHIVE already exists; refusing overwrite." >&2
  exit 6
fi

mkdir -p "$DEST_DIR"
# Never archive API keys or gateway secrets.
EXCLUDE=(
  --exclude='**/platform-gateway.key'
  --exclude='**/*.pem'
  --exclude='**/.env'
  --exclude='**/credentials*'
)

log "Recording vLLM version and pip freeze (no secrets)."
# Prefer importlib metadata: `vllm --version` needs CUDA libs on PATH/LD_LIBRARY_PATH.
"$ENV_DIR/bin/python" - <<'PY' >"$DEST_DIR/vllm-version.txt"
import importlib.metadata as m
print(m.version("vllm"))
PY
if ! "$ENV_DIR/bin/python" -m pip freeze >"$FREEZE" 2>/dev/null; then
  "$ENV_DIR/bin/python" - <<'PY' >"$FREEZE"
import importlib.metadata as m
rows = []
for d in m.distributions():
    name = d.metadata["Name"]
    rows.append(f"{name}=={d.version}")
print("\n".join(sorted(rows)))
PY
fi

{
  echo "Captured UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Source env: $ENV_DIR"
  echo "Archive: $ARCHIVE"
  echo "Host mount: $(findmnt -n -o FSTYPE,SOURCE /workspace)"
  echo "Note: archive created while Qwen may be serving; do not treat as a live restore-test proof."
  echo "vLLM version file: vllm-version.txt"
} >"$MANIFEST"

TMP_OUT="$ARCHIVE.tmp.$$"
log "Streaming tar+zstd of $ENV_DIR to $TMP_OUT (direct to Global Volume)."
# Stream to volume to avoid needing a second full copy on /tmp overlay.
tar -C "$(dirname "$ENV_DIR")" "${EXCLUDE[@]}" -cf - "$(basename "$ENV_DIR")" \
  | zstd -T0 -3 -o "$TMP_OUT"
zstd -t "$TMP_OUT"
mv "$TMP_OUT" "$ARCHIVE"

(
  cd "$DEST_DIR"
  sha256sum vllm-qwen-env.tar.zst requirements-frozen.txt runtime-manifest.txt vllm-version.txt >SHA256SUMS
  sha256sum -c SHA256SUMS
)

log "VERIFIED_ARCHIVE=$ARCHIVE"
log "SIZE=$(du -sh "$ARCHIVE" | cut -f1)"
cat "$DEST_DIR/vllm-version.txt" || true
