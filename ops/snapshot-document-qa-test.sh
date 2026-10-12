#!/usr/bin/env bash
# Create a dated recovery snapshot of the Document Q&A test checkout on Global Volume.
# Run on the RunPod Pod. Does not stop services or include credentials/model weights.
set -euo pipefail

SRC="${1:-/tmp/AI-PLAYBOOK-upload-test}"
DEST_ROOT="${2:-/workspace/runtime-setup/web-console-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="document-qa-conversation-${STAMP}"
DEST="${DEST_ROOT}/${NAME}"

if [[ ! -d "$SRC/.git" ]]; then
  echo "ERROR: expected a git checkout at $SRC" >&2
  exit 2
fi
mkdir -p "$DEST_ROOT"
mkdir -p "$DEST"

COMMIT="$(git -C "$SRC" rev-parse HEAD)"
BRANCH="$(git -C "$SRC" branch --show-current || true)"

tar -C "$(dirname "$SRC")" -czf "${DEST}/source.tgz" \
  --exclude="$(basename "$SRC")/.git" \
  --exclude='*/__pycache__' \
  --exclude='*/.env' \
  --exclude='*.key' \
  "$(basename "$SRC")"

{
  echo "name=${NAME}"
  echo "created_utc=${STAMP}"
  echo "source=${SRC}"
  echo "branch=${BRANCH}"
  echo "commit=${COMMIT}"
  echo "includes=source tree without .git, keys, env files, caches, or model weights"
  echo "docs=docs/document-qa-conversation.md web/README.md"
} > "${DEST}/MANIFEST.txt"

cp -f "$SRC/docs/document-qa-conversation.md" "${DEST}/document-qa-conversation.md" 2>/dev/null || true
cp -f "$SRC/web/README.md" "${DEST}/web-README.md" 2>/dev/null || true

test -s "${DEST}/source.tgz"
test -s "${DEST}/MANIFEST.txt"
echo "Created recovery snapshot: ${DEST}"
cat "${DEST}/MANIFEST.txt"
