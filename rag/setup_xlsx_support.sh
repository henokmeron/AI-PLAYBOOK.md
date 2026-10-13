#!/usr/bin/env bash
# Download/checksum-pin XLSX parser wheels to Global Volume, then extract into
# /tmp/rag-deps separately from the working vLLM/PyTorch environment.
set -euo pipefail

PYTHON="${RAG_SETUP_PYTHON:-/tmp/vllm-clean-env/bin/python}"
WHEEL_DIR=/workspace/runtime-setup/rag-wheelhouse
DEPS_DIR="${RAG_DEPS_DIR:-/tmp/rag-deps}"

OPENPYXL_NAME=openpyxl-3.1.5-py2.py3-none-any.whl
OPENPYXL_SHA=5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2
OPENPYXL_URL=https://files.pythonhosted.org/packages/c0/da/977ded879c29cbd04de313843e76868e6e13408a94ed6b987245dc7c8506/openpyxl-3.1.5-py2.py3-none-any.whl

ETXML_NAME=et_xmlfile-2.0.0-py3-none-any.whl
ETXML_SHA=7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa
ETXML_URL=https://files.pythonhosted.org/packages/c1/8b/5fe2cc11fee489817272089c4203e679c63b570a5aaeb18d852ae3cbba6a/et_xmlfile-2.0.0-py3-none-any.whl

DEFUSED_NAME=defusedxml-0.7.1-py2.py3-none-any.whl
DEFUSED_SHA=a352e7e428770286cc899e2542b6cdaedb2b4953ff269a210103ec58f6198a61
DEFUSED_URL=https://files.pythonhosted.org/packages/07/6c/aa3f2f849e01cb6a001cd8554a88d4c77c5c1a31c95bdf1cf9301e6d9ef4/defusedxml-0.7.1-py2.py3-none-any.whl

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: Python interpreter $PYTHON not found. XLSX setup aborted (set RAG_SETUP_PYTHON)." >&2
  exit 2
fi
mkdir -p "$WHEEL_DIR" "$DEPS_DIR"

ensure_wheel() {
  local name="$1" expected="$2" url="$3"
  local stored="$WHEEL_DIR/$name" download="/tmp/$name.download"
  if [[ -f "$stored" ]] && echo "$expected  $stored" | sha256sum -c - >/dev/null 2>&1; then
    echo "Using verified wheel already on Global Volume: $name"
    return
  fi
  echo "Downloading $name to local temporary storage..."
  curl -fsSL "$url" -o "$download"
  echo "$expected  $download" | sha256sum -c -
  cp "$download" "$stored"
  rm -f "$download"
  echo "$expected  $stored" | sha256sum -c -
}

extract_wheel() {
  "$PYTHON" - "$1" "$DEPS_DIR" <<'PY'
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
print(f"Extracted verified wheel {wheel_path.name}")
PY
}

ensure_wheel "$OPENPYXL_NAME" "$OPENPYXL_SHA" "$OPENPYXL_URL"
ensure_wheel "$ETXML_NAME" "$ETXML_SHA" "$ETXML_URL"
ensure_wheel "$DEFUSED_NAME" "$DEFUSED_SHA" "$DEFUSED_URL"

echo "=== GLOBAL VOLUME CHECKSUM FILE ==="
(
  cd "$WHEEL_DIR"
  sha256sum "$OPENPYXL_NAME" "$ETXML_NAME" "$DEFUSED_NAME" > XLSX-SHA256SUMS
  sha256sum -c XLSX-SHA256SUMS
)

# Remove only previous copies of these three parser packages, not pypdf or vLLM.
rm -rf "$DEPS_DIR/openpyxl" "$DEPS_DIR/openpyxl-"*.dist-info \
  "$DEPS_DIR/et_xmlfile" "$DEPS_DIR/et_xmlfile-"*.dist-info \
  "$DEPS_DIR/defusedxml" "$DEPS_DIR/defusedxml-"*.dist-info

extract_wheel "$WHEEL_DIR/$OPENPYXL_NAME"
extract_wheel "$WHEEL_DIR/$ETXML_NAME"
extract_wheel "$WHEEL_DIR/$DEFUSED_NAME"

echo "=== VERIFY ISOLATED PARSER VERSIONS ==="
PYTHONPATH="$DEPS_DIR" "$PYTHON" -c 'import importlib.metadata as m, openpyxl, et_xmlfile, defusedxml; print("openpyxl:",m.version("openpyxl")); print("et-xmlfile:",m.version("et-xmlfile")); print("defusedxml:",m.version("defusedxml")); assert m.version("openpyxl")=="3.1.5"; assert m.version("et-xmlfile")=="2.0.0"; assert m.version("defusedxml")=="0.7.1"'
echo
echo "Wheels persisted at: $WHEEL_DIR"
echo "Checksum list: $WHEEL_DIR/XLSX-SHA256SUMS"
echo "Isolated import path: $DEPS_DIR"
echo "Existing pypdf in that directory is left untouched; the runtime behind $PYTHON has not been modified."
