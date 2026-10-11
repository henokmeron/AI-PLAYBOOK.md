# CSV, DOCX and PDF RAG API integration — 2026-10-11

## Result

**PASS: ALL CSV/DOCX/PDF INTEGRATION TESTS PASSED** in the user's RunPod terminal screenshot.

The test used an isolated temporary gateway on `127.0.0.1:8011`, separate from the main gateway on `127.0.0.1:8010` and vLLM on `127.0.0.1:8000`.

## Observed successful cases

| Format | Question / fixture | Answer observed | Source returned |
|---|---|---|---|
| CSV | Where must visitors check in? | Visitors must check in at Gate C | `visitor-rules.csv` |
| DOCX | When is Project Helios launch review? | 18 November | `launch-review.docx` |
| PDF | When is Project Orion purchase order review? | 23 November | `project-review.pdf` |

All three responses reported `status: answered`, and all output included a source citation `[Source 1]`. The output also confirmed pypdf 6.20.0 was available.

The cleanup message states: "Temporary format-test gateway stopped; existing gateway at 127.0.0.1:8010 and vLLM remain untouched."

## Interpretation

This confirms that the current RAG HTTP API can ingest and answer from one fictional CSV, one DOCX, and one text-based PDF test document, while returning the correct source filenames.

This does not establish robust parsing for every real-world document, scanning/OCR support, table/layout fidelity in PDFs, spreadsheet/XLSX support, production security, or quality on large customer corpora. The API remains a loopback-only prototype; scanned/image-only PDFs and password-protected PDFs remain unsupported without further work.
