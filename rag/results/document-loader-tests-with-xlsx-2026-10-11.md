# XLSX-enabled document-loader test run — 2026-10-11

## Result

**PASS: 16 tests ran in 0.243 seconds, all OK**, according to the user's RunPod terminal screenshot after the isolated XLSX dependency setup.

## Dependency setup

The setup output confirmed the following versions under `/tmp/rag-deps`:
- `openpyxl 3.1.5`
- `et-xmlfile 2.0.0`
- `defusedxml 0.7.1`

The verified wheels and checksum list are stored under `/workspace/runtime-setup/rag-wheelhouse`. The script explicitly reported that the vLLM environment was not modified and existing pypdf files were left untouched.

## Coverage in the 16-test suite

- TXT and CSV extraction.
- HTML script/style filtering.
- DOCX paragraph extraction.
- Text-based PDF extraction/page markers, rejection of no-text/scanned PDFs pending OCR, malformed PDF handling and source attribution.
- XLSX worksheet name/cell value extraction, source name preservation and retrieval ranking, malformed workbook rejection, and empty-workbook rejection.
- Source file size guard and unsupported extension handling.

## Next

The parser suite has passed. Upgrade the main gateway using `api/upgrade_gateway_with_rag_smoke.sh`; it checks the pinned PDF and XLSX package versions before stopping the prior gateway and restarts only the gateway. Then run `api/test_format_ingestion.sh`, which uses an isolated temporary gateway to test CSV, DOCX, PDF, and XLSX through the HTTP API. Do not mark XLSX as fully end-to-end verified until the integration test passes.
