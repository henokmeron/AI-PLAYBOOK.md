#!/usr/bin/env bash
# Install the canonical launcher into /workspace/ai-platform-release/.
# Keeps a timestamped backup of any different existing START.sh/README.md; deletes nothing.
set -Eeuo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${RELEASE_DIR:-/workspace/ai-platform-release}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$DEST"
for name in START.sh README.md; do
  src="$SRC_DIR/$name"
  dst="$DEST/$name"
  [[ -f "$src" ]] || { echo "ERROR: missing $src" >&2; exit 1; }
  if [[ -f "$dst" ]] && cmp -s "$src" "$dst"; then
    echo "unchanged $dst"
    continue
  fi
  if [[ -f "$dst" ]]; then
    cp "$dst" "$dst.bak-$STAMP"
    echo "backup    $dst.bak-$STAMP"
  fi
  # Plain copy: FUSE rejects chmod/chown, and bash START.sh does not need the exec bit.
  cat "$src" >"$dst"
  echo "installed $dst"
done
bash -n "$DEST/START.sh"
echo "OK: $DEST/START.sh syntax valid"
