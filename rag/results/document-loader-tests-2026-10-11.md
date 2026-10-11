# Business document loader unit-test run — 2026-10-11

## Result

**PASS: 8 tests ran, all OK**. The user's RunPod terminal screenshot shows all 8 tests passed in 0.010 seconds.

## Coverage

- CSV rows become searchable text.
- HTML visible text is extracted while script/style content is excluded.
- DOCX paragraph text is extracted.
- Unsupported file extensions are rejected.
- Invalid DOCX/ZIP files are rejected.
- Oversized source files are rejected by the 10 MiB limit.
- Plain text is read.
- The RAG index preserves DOCX/CSV source names and ranks the deadline document for the receipt-deadline question.

## Interpretation

These parser/unit tests run without model inference or GPU calls. They validate the tested sample formats and safety checks only; they do not demonstrate robust extraction from every real-world Word/CSV/HTML variant. PDF and XLSX remain unsupported.
