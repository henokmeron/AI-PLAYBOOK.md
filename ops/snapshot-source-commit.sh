#!/usr/bin/env bash
# Create an immutable GitHub source snapshot on the Global Volume for a given commit.
# Does not copy model weights. Verifies mount + Gemma marker before writing.
set -Eeuo pipefail

REPO="${REPO:-henokmeron/AI-PLAYBOOK.md}"
COMMIT="${1:-}"
GLOBAL=/workspace
ROOT="$GLOBAL/ai-platform-backups"
SOURCE_DIR="$ROOT/source-snapshots"
MANIFEST_DIR="$ROOT/manifests"
WORK="/tmp/ai-platform-commit-snapshot-$$"
mkdir -p "$WORK"
trap 'rm -rf "$WORK"' EXIT

if [[ -z "$COMMIT" || ${#COMMIT} -lt 7 ]]; then
  echo "Usage: $0 <full-or-prefix-git-sha>" >&2
  exit 2
fi

if ! command -v findmnt >/dev/null 2>&1; then
  echo "ERROR: findmnt not available; refusing to assume /workspace is persistent." >&2
  exit 2
fi

MOUNT_TARGET="$(findmnt -T "$GLOBAL" -n -o TARGET 2>/dev/null | head -n 1 || true)"
MOUNT_TYPE="$(findmnt -T "$GLOBAL" -n -o FSTYPE 2>/dev/null | head -n 1 || true)"
MOUNT_SOURCE="$(findmnt -T "$GLOBAL" -n -o SOURCE 2>/dev/null | head -n 1 || true)"
MODEL_MARKER="$GLOBAL/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it/config.json"

if [[ "$MOUNT_TARGET" != "$GLOBAL" ]]; then
  echo "ERROR: $GLOBAL is not itself a mount point." >&2
  exit 3
fi
if [[ ! -f "$MODEL_MARKER" ]]; then
  echo "ERROR: Gemma marker missing; refusing to write." >&2
  exit 3
fi
mkdir -p "$SOURCE_DIR" "$MANIFEST_DIR"
echo "Global Volume mount verified: $MOUNT_TYPE $MOUNT_SOURCE"

# Resolve to full SHA via GitHub API
curl -fsSL "https://api.github.com/repos/$REPO/commits/$COMMIT" -o "$WORK/commit.json"
FULL_SHA="$(python3 - "$WORK/commit.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
sha=d.get("sha","")
if len(sha)!=40:
    raise SystemExit("Could not resolve full commit SHA")
print(sha)
PY
)"
echo "Resolved commit: $FULL_SHA"

curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$FULL_SHA" -o "$WORK/source.tar.gz"
tar -tzf "$WORK/source.tar.gz" >/dev/null
ARCHIVE_SHA="$(sha256sum "$WORK/source.tar.gz" | awk '{print $1}')"
TARGET="$SOURCE_DIR/AI-PLAYBOOK.md-$FULL_SHA.tar.gz"
if [[ -e "$TARGET" ]]; then
  EXISTING_SHA="$(sha256sum "$TARGET" | awk '{print $1}')"
  if [[ "$EXISTING_SHA" != "$ARCHIVE_SHA" ]]; then
    echo "ERROR: snapshot exists but checksum differs; refusing overwrite." >&2
    exit 4
  fi
  echo "Immutable snapshot already present and matches."
else
  cp "$WORK/source.tar.gz" "$TARGET"
fi
echo "$ARCHIVE_SHA  $TARGET" | sha256sum -c -
cp "$WORK/commit.json" "$MANIFEST_DIR/source-commit-$FULL_SHA.json"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
{
  echo "Captured UTC: $STAMP"
  echo "Repo: $REPO"
  echo "Commit: $FULL_SHA"
  echo "Archive: $TARGET"
  echo "SHA256: $ARCHIVE_SHA"
  echo "Mount: $MOUNT_TYPE $MOUNT_SOURCE"
} | tee "$MANIFEST_DIR/snapshot-verify-$FULL_SHA-$STAMP.txt"

echo "VERIFIED_SNAPSHOT=$TARGET"
echo "VERIFIED_SHA256=$ARCHIVE_SHA"
