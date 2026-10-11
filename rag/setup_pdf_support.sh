#!/usr/bin/env bash
# Fetch and verify the pinned pypdf wheel on persistent Global Volume storage,
# then extract it to an isolated Pod-local directory without altering vLLM's venv.
set -euo pipefail

PYTHON=/tmp/vllm-clean-env/bin/python
WHEEL_DIR=/workspace/runtime-setup/rag-wheelhouse
WHEEL_NAME=pypdf-6.20.0-py3-none-any.whl
WHEEL="$WHEEL_DIR/$WHEEL_NAME"
DOWNLOAD=/tmp/$WHEEL_NAME.download
DEPS_DIR=/tmp/rag-deps
EXPECTED_SHA256=f003fc2014814d264fe7dd3f9d435c158e23e1a85a2233f87a0a2d6d21c914ad
WHEEL_URL=https://files.pythonhosted.org/packages/18/42/a945f65cc61c739ec80f4112c4b78ed1791f25d33f45f19389c9c9e247e2/pypdf-6.20.0-py3-none-any.whl

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: current vLLM Python environment not found; PDF setup aborted." >&2
  exit 2
fi

mkdir -p "$WHEEL_DIR" "$DEPS_DIR"

# Reuse the persistent verified wheel if present; otherwise fetch it to local
# temporary storage, verify the official PyPI SHA-256, then copy it to Global Volume.
if [[ -f "$WHEEL" ]] && echo "$EXPECTED_SHA256  $WHEEL" | sha256sum -c - >/dev/null 2>&1; then
  echo "Using existing persistent pypdf wheel."
else
  echo "Downloading pinned pypdf wheel to local temporary storage..."
  curl -fsSL "$WHEEL_URL" -o "$DOWNLOAD"
  echo "$EXPECTED_SHA256  $DOWNLOAD" | sha256sum -c -
  cp "$DOWNLOAD" "$WHEEL"
  rm -f "$DOWNLOAD"
fi

echo "=== VERIFY PERSISTENT WHEEL ==="
echo "$EXPECTED_SHA256  $WHEEL" | sha256sum -c -
(
  cd "$WHEEL_DIR"
  sha256sum "$WHEEL_NAME" > SHA256SUMS
  sha256sum -c SHA256SUMS
)

# Avoid modifying /tmp/vllm-clean-env. Clear only the separate parser target.
rm -rf "$DEPS_DIR/pypdf" "$DEPS_DIR/pypdf-6.20.0.dist-info" "$DEPS_DIR/pypdf-6.20.0.data"

"$PYTHON" - "$WHEEL" "$DEPS_DIR" <<'PY'
import pathlib
import sys
import zipfile

wheel_path = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2]).resolve()
with zipfile.ZipFile(wheel_path) as archive:
    for info in archive.infolist():
        member = pathlib.PurePosixPath(info.filename)
        if member.is_absolute() or ".." in member.parts:
            raise SystemExit(f"Unsafe wheel path rejected: {info.filename}")
        target = (destination / pathlib.Path(*member.parts)).resolve()
        if destination not in target.parents and target != destination:
            raise SystemExit(f"Unsafe wheel destination rejected: {info.filename}")
    archive.extractall(destination)
print("Wheel extracted into isolated parser directory.")
PY

echo "=== VERIFY ISOLATED PDF DEPENDENCY ==="
PYTHONPATH="$DEPS_DIR" "$PYTHON" -c 'import pypdf; from pypdf import PdfReader; print("pypdf:", pypdf.__version__); assert pypdf.__version__ == "6.20.0"'
echo
echo "Persistent wheel: $WHEEL"
echo "Persistent checksum: $WHEEL_DIR/SHA256SUMS"
echo "Isolated import path: $DEPS_DIR"
echo "The vLLM environment at /tmp/vllm-clean-env has not been modified."
