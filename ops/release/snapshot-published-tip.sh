#!/usr/bin/env bash
# Write a checksummed source snapshot of the published GitHub tip onto the
# Global Volume. Run this on the Pod, before Stop.
#
# It does not stop Qwen (:8002), the gateway (:8010), or the console (:8080).
# It does not delete weights, runtime archives, managed docs, older snapshots,
# or anything else under /workspace. It refuses to run unless /workspace is
# the fuse.geesefs Global Volume.
#
# Usage (on the Pod):
#   bash ops/release/snapshot-published-tip.sh
set -Eeuo pipefail

GLOBAL=/workspace
SNAP_DIR="$GLOBAL/ai-platform-backups/source-snapshots"
MANIFEST_DIR="$GLOBAL/ai-platform-backups/manifests"
WEIGHTS="$GLOBAL/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654"
QWEN_RT="$GLOBAL/runtime-setup/qwen-vllm"
BRANCH="${PLATFORM_BRANCH:-feature/qwen3.5-27b-integration}"
REMOTE="${PLATFORM_REMOTE:-https://github.com/henokmeron/AI-PLAYBOOK.md.git}"

if ! command -v findmnt >/dev/null 2>&1; then
  echo "ERROR: findmnt is missing; refusing to write." >&2
  exit 2
fi

MOUNT_TARGET="$(findmnt -T "$GLOBAL" -n -o TARGET 2>/dev/null | head -n 1 || true)"
MOUNT_TYPE="$(findmnt -T "$GLOBAL" -n -o FSTYPE 2>/dev/null | head -n 1 || true)"
MOUNT_SOURCE="$(findmnt -T "$GLOBAL" -n -o SOURCE 2>/dev/null | head -n 1 || true)"
if [[ "$MOUNT_TARGET" != "$GLOBAL" || "$MOUNT_TYPE" != "fuse.geesefs" ]]; then
  echo "ERROR: $GLOBAL is not the fuse.geesefs Global Volume." >&2
  echo "Detected target=${MOUNT_TARGET:-none} fstype=${MOUNT_TYPE:-none} source=${MOUNT_SOURCE:-none}" >&2
  echo "Nothing was written." >&2
  exit 3
fi
if [[ ! -d "$WEIGHTS" || ! -f "$QWEN_RT/vllm-qwen-env.tar.zst" ]]; then
  echo "ERROR: Qwen weights or the runtime archive are not on this volume." >&2
  echo "Nothing was written." >&2
  exit 3
fi

mkdir -p "$SNAP_DIR" "$MANIFEST_DIR"
WORK="/tmp/shutdown-snapshot-$$"
mkdir -p "$WORK"
trap 'rm -rf "$WORK"' EXIT

echo "Cloning $BRANCH from GitHub into $WORK (ephemeral)."
git clone --quiet --branch "$BRANCH" --single-branch "$REMOTE" "$WORK/src"
SHA="$(git -C "$WORK/src" rev-parse HEAD)"
SHORT="$(git -C "$WORK/src" rev-parse --short=7 HEAD)"
case "$SHA" in
  "$SHORT"*) ;;
  *) echo "ERROR: short SHA $SHORT is not a prefix of $SHA" >&2; exit 4 ;;
esac

ARCHIVE="$SNAP_DIR/AI-PLAYBOOK.md-runpod-first-${SHORT}.tar.gz"
SUM_FILE="$MANIFEST_DIR/AI-PLAYBOOK.md-runpod-first-${SHORT}.sha256"
if [[ -e "$ARCHIVE" || -e "$SUM_FILE" ]]; then
  echo "ERROR: snapshot already exists; refusing to overwrite." >&2
  echo "  $ARCHIVE" >&2
  echo "  $SUM_FILE" >&2
  exit 4
fi

# git archive emits the tree at the archive root (no .git). Untracked files,
# __pycache__, and token files are not in the commit, so they are not packed.
git -C "$WORK/src" archive --format=tar.gz -o "$ARCHIVE" HEAD
tar -tzf "$ARCHIVE" >/dev/null
SUM="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
printf '%s  %s\n' "$SUM" "$ARCHIVE" >"$SUM_FILE"
sha256sum -c "$SUM_FILE"

# Canonical launcher. install-to-volume.sh keeps a timestamped copy of a
# different START.sh and does not delete the previous file.
bash "$WORK/src/ops/release/install-to-volume.sh"

# VERSION.txt is a recovery pointer only when it already exists. Keep the
# previous text, and keep a full copy beside it. Do not create a new file.
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
for version_file in \
  "$GLOBAL/ai-platform-release/VERSION.txt" \
  "$GLOBAL/VERSION.txt" \
  "$GLOBAL/ai-platform-backups/VERSION.txt"
do
  if [[ -f "$version_file" ]]; then
    cp "$version_file" "$version_file.bak-$STAMP"
    {
      echo
      echo "commit=$SHA"
      echo "snapshot=$ARCHIVE"
      echo "snapshot_sha256=$SUM"
      echo "recorded_utc=$STAMP"
      echo "note=appended by snapshot-published-tip.sh; previous text kept above and in the .bak file"
    } >>"$version_file"
    echo "Appended pointer to $version_file (backup $version_file.bak-$STAMP)"
  fi
done

MANIFEST="$MANIFEST_DIR/shutdown-asset-manifest-${SHORT}-${STAMP}.txt"
{
  echo "Captured UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Repo: henokmeron/AI-PLAYBOOK.md"
  echo "Branch: $BRANCH"
  echo "Commit: $SHA"
  echo "Archive: $ARCHIVE"
  echo "Archive SHA256: $SUM"
  echo "Checksum file: $SUM_FILE"
  echo "Mount: $MOUNT_TYPE $MOUNT_SOURCE $MOUNT_TARGET"
  echo "Services were not stopped."
  echo
  echo "=== weights (names and sizes; the 52GiB tree was not fully re-hashed) ==="
  du -sh "$WEIGHTS" || true
  echo "file_count $(find "$WEIGHTS" -maxdepth 1 -type f | wc -l)"
  find "$WEIGHTS" -maxdepth 1 -type f -printf '%f\t%s\n' | sort
  echo
  echo "=== 1MiB prefix samples (not full-file hashes) ==="
  sample=0
  while IFS= read -r shard; do
    [[ -n "$shard" ]] || continue
    sample=$((sample + 1))
    printf 'SAMPLE_PREFIX_1MiB %s ' "$(basename "$shard")"
    head -c 1048576 "$shard" | sha256sum
    [[ "$sample" -ge 2 ]] && break
  done < <(find "$WEIGHTS" -maxdepth 1 -type f -name '*.safetensors' | sort)
  echo
  echo "=== existing runtime SHA256SUMS (checked, not rewritten) ==="
  if [[ -f "$QWEN_RT/SHA256SUMS" ]]; then
    cat "$QWEN_RT/SHA256SUMS"
    (cd "$QWEN_RT" && sha256sum -c SHA256SUMS)
  else
    echo "MISSING: $QWEN_RT/SHA256SUMS"
  fi
  echo
  echo "=== rag wheelhouse ==="
  if [[ -d "$GLOBAL/runtime-setup/rag-wheelhouse" ]]; then
    find "$GLOBAL/runtime-setup/rag-wheelhouse" -maxdepth 2 -type f -printf '%p\t%s\n' | sort
  else
    echo "MISSING: $GLOBAL/runtime-setup/rag-wheelhouse"
  fi
  echo
  echo "=== managed docs (count only) ==="
  if [[ -d "$GLOBAL/rag-managed-docs" ]]; then
    echo "file_count $(find "$GLOBAL/rag-managed-docs" -type f | wc -l)"
  else
    echo "MISSING: $GLOBAL/rag-managed-docs"
  fi
  echo
  echo "=== launcher ==="
  sha256sum "$GLOBAL/ai-platform-release/START.sh" "$WORK/src/ops/release/START.sh"
  echo
  echo "=== source snapshots now on the volume (older files kept) ==="
  ls -l "$SNAP_DIR"
} | tee "$MANIFEST"

echo "VERIFIED_SNAPSHOT=$ARCHIVE"
echo "VERIFIED_SHA256=$SUM"
echo "VERIFIED_COMMIT=$SHA"
echo "MANIFEST=$MANIFEST"
echo "RESTORE: on a new Pod with this same volume, bash /workspace/ai-platform-release/START.sh"
echo "Offline fallback uses this snapshot only when GitHub cannot be cloned."
