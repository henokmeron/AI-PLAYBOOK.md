#!/usr/bin/env bash
# Run the RAG parser/unit suite with the pinned isolated dependencies.
# Does not modify vLLM, the main gateway, or the main console.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${RAG_TEST_PYTHON:-/tmp/vllm-clean-env/bin/python}"
DEPS_DIR="${RAG_DEPS_DIR:-/tmp/rag-deps}"

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: expected Python at $PYTHON (set RAG_TEST_PYTHON to override)." >&2
  exit 2
fi

echo "=== ENSURE PINNED PDF/XLSX PARSER DEPS IN $DEPS_DIR ==="
bash "$ROOT/rag/setup_pdf_support.sh"
bash "$ROOT/rag/setup_xlsx_support.sh"

echo "=== VERIFY PINNED VERSIONS ==="
PYTHONPATH="$DEPS_DIR" "$PYTHON" -c '
import importlib.metadata as m, pypdf, openpyxl, et_xmlfile, defusedxml
assert m.version("pypdf") == "6.20.0", m.version("pypdf")
assert m.version("openpyxl") == "3.1.5", m.version("openpyxl")
assert m.version("et-xmlfile") == "2.0.0", m.version("et-xmlfile")
assert m.version("defusedxml") == "0.7.1", m.version("defusedxml")
print("Verified pypdf", m.version("pypdf"),
      "openpyxl", m.version("openpyxl"),
      "et-xmlfile", m.version("et-xmlfile"),
      "defusedxml", m.version("defusedxml"))
'

echo "=== RUN RAG UNIT TESTS ==="
cd "$ROOT"
PYTHONPATH="$DEPS_DIR:$ROOT/rag${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON" -m unittest discover -s rag/tests -v
