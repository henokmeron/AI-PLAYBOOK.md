#!/usr/bin/env bash
# Isolated CSV/DOCX/PDF/XLSX -> RAG HTTP API integration test.
# Starts a temporary loopback gateway on 8011; leaves the existing 8010 gateway and vLLM untouched.
set -euo pipefail

BASE=https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main
PYTHON=/tmp/vllm-clean-env/bin/python
KEY_FILE=/tmp/platform-gateway.key
APP_DIR=/tmp/platform-format-test-app
DOCS_DIR=/tmp/platform-format-test-docs
URL=http://127.0.0.1:8011
PID_FILE=/tmp/platform-format-test.pid
LOG_FILE=/tmp/platform-format-test.log
TEST_PID=""

cleanup() {
  status=$?
  if [[ -n "$TEST_PID" ]] && kill -0 "$TEST_PID" 2>/dev/null; then
    kill "$TEST_PID" 2>/dev/null || true
    for _ in $(seq 1 10); do
      if ! kill -0 "$TEST_PID" 2>/dev/null; then break; fi
      sleep 1
    done
  fi
  rm -f "$PID_FILE"
  rm -rf "$APP_DIR" "$DOCS_DIR"
  if [[ "$status" -eq 0 ]]; then
    echo "Temporary format-test gateway stopped; existing gateway at 127.0.0.1:8010 and vLLM remain untouched."
  else
    echo "Format test failed. Temporary gateway log (if any): $LOG_FILE" >&2
    tail -30 "$LOG_FILE" 2>/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT

if [[ ! -x "$PYTHON" ]]; then echo "ERROR: current Python environment not found; no installation attempted." >&2; exit 2; fi
if [[ ! -r "$KEY_FILE" ]]; then echo "ERROR: current temporary gateway key not found; existing service untouched." >&2; exit 3; fi
if ! PYTHONPATH=/tmp/rag-deps "$PYTHON" -c 'import importlib.metadata as m, pypdf, openpyxl, et_xmlfile, defusedxml; assert m.version("pypdf")=="6.20.0"; assert m.version("openpyxl")=="3.1.5"; assert m.version("et-xmlfile")=="2.0.0"; assert m.version("defusedxml")=="0.7.1"; print("Verified pypdf and XLSX parser dependencies")'; then echo "ERROR: run rag/setup_pdf_support.sh and rag/setup_xlsx_support.sh first; existing services remain untouched." >&2; exit 4; fi
if curl -fsS http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then :; else echo "ERROR: vLLM is not responding at 127.0.0.1:8000." >&2; exit 4; fi
if curl -fsS "$URL/health" >/dev/null 2>&1; then echo "ERROR: port 8011 already has a responsive service. Refusing to replace it." >&2; exit 5; fi

mkdir -p "$APP_DIR" "$DOCS_DIR"
curl -fsSL "$BASE/api/local_gateway.py" -o "$APP_DIR/local_gateway.py"
curl -fsSL "$BASE/rag/rag_engine.py" -o "$APP_DIR/rag_engine.py"
curl -fsSL "$BASE/rag/document_loaders.py" -o "$APP_DIR/document_loaders.py"
curl -fsSL "$BASE/rag/document_library.py" -o "$APP_DIR/document_library.py"

cat > "$DOCS_DIR/visitor-rules.csv" <<'CSV'
rule,detail
visitor check-in,Visitors must check in at Gate C.
CSV

"$PYTHON" - "$DOCS_DIR/launch-review.docx" <<'PY'
import sys, zipfile
from pathlib import Path
path = Path(sys.argv[1])
xml = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:body>'
    '<w:p><w:r><w:t>Project Helios launch review is scheduled for 18 November.</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>The review owner is the Operations team.</w:t></w:r></w:p>'
    '</w:body></w:document>'
)
with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("word/document.xml", xml)
PY

"$PYTHON" - "$DOCS_DIR/project-review.pdf" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = "Project Orion purchase order review takes place on 23 November."
stream = b"BT /F1 12 Tf 72 720 Td (" + text.encode("ascii") + b") Tj ET"
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
]
data = bytearray(b"%PDF-1.4\n%PDF integration fixture\n")
offsets = [0]
for number, obj in enumerate(objects, start=1):
    offsets.append(len(data))
    data.extend(f"{number} 0 obj\n".encode("ascii"))
    data.extend(obj)
    data.extend(b"\nendobj\n")
xref_offset = len(data)
data.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
data.extend(b"0000000000 65535 f \n")
for offset in offsets[1:]:
    data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
data.extend(
    (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
     f"startxref\n{xref_offset}\n%%EOF\n").encode("ascii")
)
path.write_bytes(bytes(data))
PY

PYTHONPATH=/tmp/rag-deps "$PYTHON" - "$DOCS_DIR/department-budget.xlsx" <<'PY'
import sys
from pathlib import Path
import openpyxl
path = Path(sys.argv[1])
workbook = openpyxl.Workbook()
sheet = workbook.active
sheet.title = "Budget"
sheet.append(["Department", "Budget type", "Q4 budget"])
sheet.append(["Marketing", "planned amount", 27500])
workbook.save(path)
workbook.close()
PY

"$PYTHON" -m py_compile "$APP_DIR/local_gateway.py" "$APP_DIR/rag_engine.py" "$APP_DIR/document_loaders.py" "$APP_DIR/document_library.py"
API_KEY="$(cat "$KEY_FILE")"
PYTHONPATH=/tmp/rag-deps PLATFORM_HOST=127.0.0.1 PLATFORM_PORT=8011 PLATFORM_API_KEY="$API_KEY" \
  VLLM_UPSTREAM_URL=http://127.0.0.1:8000/v1 RAG_DOCS_DIR="$DOCS_DIR" RAG_MANAGED_DOCS_DIR="$APP_DIR/managed" RAG_MIN_SCORE=0 RAG_MANAGED_MIN_SCORE=0 \
  UV_CACHE_DIR=/tmp/uv-cache TMPDIR=/tmp \
  nohup "$PYTHON" "$APP_DIR/local_gateway.py" > "$LOG_FILE" 2>&1 </dev/null &
TEST_PID=$!
echo "$TEST_PID" > "$PID_FILE"

ready=0
for _ in $(seq 1 25); do
  if curl -fsS "$URL/health" >/tmp/platform-format-health.json 2>/dev/null; then ready=1; break; fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then echo "ERROR: isolated test gateway failed to start." >&2; exit 6; fi

echo "=== CSV INTEGRATION TEST ==="
csv_response="$(curl -fsS -X POST "$URL/v1/rag/ask" \
  -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' \
  -d '{"question":"At which gate must visitors check in?","top_k":2}')"
printf '%s' "$csv_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("Status:",d.get("status")); print("Answer:",d.get("answer")); print("Sources:",", ".join(x.get("file","?") for x in d.get("sources",[]))); assert d.get("status")=="answered"; assert "gate c" in d.get("answer","").casefold(); assert any(x.get("file")=="visitor-rules.csv" for x in d.get("sources",[]))'
echo "PASS: CSV was retrieved and its source was returned."

echo "=== DOCX INTEGRATION TEST ==="
docx_response="$(curl -fsS -X POST "$URL/v1/rag/ask" \
  -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' \
  -d '{"question":"When is the Project Helios launch review scheduled?","top_k":2}')"
printf '%s' "$docx_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("Status:",d.get("status")); print("Answer:",d.get("answer")); print("Sources:",", ".join(x.get("file","?") for x in d.get("sources",[]))); assert d.get("status")=="answered"; assert "18 november" in d.get("answer","").casefold(); assert any(x.get("file")=="launch-review.docx" for x in d.get("sources",[]))'
echo "PASS: DOCX was retrieved and its source was returned."

echo "=== PDF INTEGRATION TEST ==="
pdf_response="$(curl -fsS -X POST "$URL/v1/rag/ask" \
  -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' \
  -d '{"question":"When does the Project Orion purchase order review take place?","top_k":2}')"
printf '%s' "$pdf_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("Status:",d.get("status")); print("Answer:",d.get("answer")); print("Sources:",", ".join(x.get("file","?") for x in d.get("sources",[]))); assert d.get("status")=="answered"; assert "23 november" in d.get("answer","").casefold(); assert any(x.get("file")=="project-review.pdf" for x in d.get("sources",[]))'
echo "PASS: PDF was retrieved and its source was returned."

echo "=== XLSX INTEGRATION TEST ==="
xlsx_response="$(curl -fsS -X POST "$URL/v1/rag/ask" \
  -H "Authorization: Bearer $API_KEY" -H 'Content-Type: application/json' \
  -d '{"question":"What is the Q4 marketing budget?","top_k":2}')"
printf '%s' "$xlsx_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); answer=d.get("answer",""); digits="".join(c for c in answer if c.isdigit()); print("Status:",d.get("status")); print("Answer:",answer); print("Sources:",", ".join(x.get("file","?") for x in d.get("sources",[]))); assert d.get("status")=="answered"; assert "27500" in digits; assert any(x.get("file")=="department-budget.xlsx" for x in d.get("sources",[]))'
echo "PASS: XLSX was retrieved and its source was returned."

echo "ALL CSV/DOCX/PDF/XLSX INTEGRATION TESTS PASSED."
