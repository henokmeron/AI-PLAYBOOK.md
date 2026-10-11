#!/usr/bin/env bash
# Snapshot the complete GitHub source tree to the mounted persistent Global Volume.
# Also preserve hashes for existing runtime backups and capture the currently deployed
# gateway modules separately from the latest source, so "source" and "running code"
# are not confused. Never run git operations on the FUSE-mounted volume.
set -Eeuo pipefail

REPO=henokmeron/AI-PLAYBOOK.md
BRANCH=main
GLOBAL=/workspace
ROOT="$GLOBAL/ai-platform-backups"
SOURCE_DIR="$ROOT/source-snapshots"
MANIFEST_DIR="$ROOT/manifests"
DEPLOYED_DIR="$ROOT/deployed-runtime"
RESTORE_DIR="$ROOT/restored-source"
WORK="/tmp/ai-platform-global-sync-$$"
mkdir -p "$WORK"
trap 'rm -rf "$WORK"' EXIT

if ! command -v findmnt >/dev/null 2>&1; then
  echo "ERROR: findmnt not available; refusing to assume /workspace is persistent." >&2
  exit 2
fi
MOUNT_INFO="$(findmnt -T "$GLOBAL" -n -o FSTYPE,SOURCE 2>/dev/null || true)"
if [[ "$MOUNT_INFO" != *"fuse.geeseefs"* ]]; then
  echo "ERROR: /workspace does not look like the expected mounted Global Volume." >&2
  echo "Detected mount: ${MOUNT_INFO:-none}" >&2
  echo "Nothing was copied. Confirm the Global Volume is mounted at /workspace." >&2
  exit 3
fi

mkdir -p "$SOURCE_DIR" "$MANIFEST_DIR" "$DEPLOYED_DIR" "$RESTORE_DIR"
echo "Global Volume mount verified: $MOUNT_INFO"

echo "=== RESOLVE CURRENT SOURCE COMMIT ==="
curl -fsSL "https://api.github.com/repos/$REPO/commits/$BRANCH" -o "$WORK/commit.json"
COMMIT="$("/tmp/vllm-clean-env/bin/python" - "$WORK/commit.json" <<'PY'
import json,sys
with open(sys.argv[1],encoding="utf-8") as f:
    d=json.load(f)
sha=d.get("sha","")
if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
    raise SystemExit("Could not resolve a full Git commit SHA")
print(sha)
PY
)"
echo "Source commit: $COMMIT"

echo "=== DOWNLOAD COMPLETE REPOSITORY ARCHIVE ==="
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$COMMIT" -o "$WORK/source.tar.gz"
tar -tzf "$WORK/source.tar.gz" >/dev/null
ARCHIVE_SHA="$(sha256sum "$WORK/source.tar.gz" | awk '{print $1}')"
TARGET="$SOURCE_DIR/AI-PLAYBOOK.md-$COMMIT.tar.gz"
if [[ -e "$TARGET" ]]; then
  EXISTING_SHA="$(sha256sum "$TARGET" | awk '{print $1}')"
  if [[ "$EXISTING_SHA" != "$ARCHIVE_SHA" ]]; then
    echo "ERROR: snapshot path exists but checksum differs; refusing to overwrite it." >&2
    exit 4
  fi
  echo "Immutable source snapshot already exists and matches checksum."
else
  cp "$WORK/source.tar.gz" "$TARGET"
fi
echo "$ARCHIVE_SHA  $TARGET" | sha256sum -c -
cp "$WORK/commit.json" "$MANIFEST_DIR/source-commit-$COMMIT.json.tmp"
cp "$MANIFEST_DIR/source-commit-$COMMIT.json.tmp" "$MANIFEST_DIR/source-commit-$COMMIT.json" && rm -f "$MANIFEST_DIR/source-commit-$COMMIT.json.tmp"

echo "=== CAPTURE DEPLOYED FILES IF AVAILABLE ==="
DEPLOYED_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEPLOYED_MANIFEST="$MANIFEST_DIR/deployed-files-$DEPLOYED_STAMP.txt"
: > "$WORK/deployed-files.txt"
for source_file in \
  /tmp/platform_gateway.py \
  /tmp/rag_engine.py \
  /tmp/document_loaders.py \
  /tmp/document_library.py; do
  if [[ -f "$source_file" ]]; then
    name="$(basename "$source_file")"
    dest="$DEPLOYED_DIR/$DEPLOYED_STAMP-$name"
    cp "$source_file" "$dest"
    sha256sum "$dest" >> "$WORK/deployed-files.txt"
  fi
done
{
  echo "Captured UTC: $DEPLOYED_STAMP"
  echo "Note: these are copies of runtime files found on this Pod, not a claim that they all match the current GitHub commit."
  cat "$WORK/deployed-files.txt"
} > "$WORK/deployed-manifest.txt"
cp "$WORK/deployed-manifest.txt" "$DEPLOYED_MANIFEST"

echo "=== RUNTIME AND DEPENDENCY BACKUP INVENTORY ==="
MANIFEST="$WORK/manifest.txt"
{
  echo "Project: $REPO"
  echo "GitHub branch: $BRANCH"
  echo "GitHub commit SHA: $COMMIT"
  echo "Snapshot archive: $TARGET"
  echo "Snapshot SHA256: $ARCHIVE_SHA"
  echo "Captured UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Global Volume mount: $MOUNT_INFO"
  echo
  echo "Existing runtime backups and pinned parser wheel inventories:"
  for item in \
    /workspace/runtime-setup/install-vllm.sh \
    /workspace/runtime-setup/requirements-frozen.txt \
    /workspace/runtime-setup/runtime-manifest.txt \
    /workspace/runtime-setup/vllm-clean-env.tar.zst \
    /workspace/runtime-setup/SHA256SUMS \
    /workspace/runtime-setup/rag-wheelhouse/SHA256SUMS \
    /workspace/runtime-setup/rag-wheelhouse/XLSX-SHA256SUMS \
    /workspace/runtime-setup/rag-wheelhouse/pypdf-6.20.0-py3-none-any.whl \
    /workspace/runtime-setup/rag-wheelhouse/openpyxl-3.1.5-py2.py3-none-any.whl \
    /workspace/runtime-setup/rag-wheelhouse/et_xmlfile-2.0.0-py3-none-any.whl \
    /workspace/runtime-setup/rag-wheelhouse/defusedxml-0.7.1-py2.py3-none-any.whl; do
    if [[ -f "$item" ]]; then
      sha256sum "$item"
    else
      echo "MISSING: $item"
    fi
  done
  echo
  echo "Model inventory (sizes, not fresh checksums; Azure remains the independent master):"
  if [[ -d /workspace/gemma-4-31B-it ]]; then
    du -sh /workspace/gemma-4-31B-it
    find /workspace/gemma-4-31B-it -type f -printf '%P\t%s bytes\n' 2>/dev/null | sort
  else
    echo "MISSING: /workspace/gemma-4-31B-it"
  fi
  echo
  echo "Deployed file copy manifest: $DEPLOYED_MANIFEST"
  cat "$WORK/deployed-manifest.txt"
} > "$MANIFEST"

MANIFEST_TARGET="$MANIFEST_DIR/global-volume-manifest-$COMMIT.txt"
cp "$MANIFEST" "$MANIFEST_TARGET"
sha256sum "$TARGET" "$MANIFEST_TARGET"

echo
echo "SUCCESS: source snapshot and manifest saved on the mounted Global Volume."
echo "Source archive: $TARGET"
echo "Manifest:       $MANIFEST_TARGET"
echo "Runtime backup folder (existing): /workspace/runtime-setup"
echo "Model folder:                     /workspace/gemma-4-31B-it"
echo "Temporary /tmp files are not the persistent copy."
