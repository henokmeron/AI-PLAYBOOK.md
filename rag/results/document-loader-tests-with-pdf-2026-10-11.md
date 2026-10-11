# PDF-enabled document-loader test run — 2026-10-11

## Result

**PASS: 12 tests ran, all OK**. The user's terminal screenshot shows `Ran 12 tests in 0.064s` followed by `OK`, executed after installing the pinned parser and setting `PYTHONPATH=/tmp/rag-deps`.

## Additional PDF coverage now passing

- Text extraction from a PDF with a page marker.
- Rejection of a PDF with no extractable text, with an explicit OCR-needed message.
- Rejection of a malformed PDF.
- Indexing and retrieval preserve the PDF source filename.

The previous TXT/CSV/HTML/DOCX tests also remain in the 12-test suite and passed.

## What this proves—and what it does not

The local parser test suite now works with the pinned `pypdf==6.20.0` dependency. These tests do not use GPU inference. They validate the generated test fixtures, not every real-world PDF layout. Scanned/image-only PDFs and password-protected PDFs remain unsupported; OCR is not installed.
