# PDF support decision and dependency record

## Decision

Support searchable/text-based PDF files in the RAG ingestion layer using `pypdf==6.20.0`. The parser is imported lazily, so TXT/Markdown/CSV/HTML/DOCX ingestion still works when the PDF dependency is absent. The dependency is installed in `/tmp/rag-deps`, not in `/tmp/vllm-clean-env`; the pinned wheel is kept on the Global Volume in `/workspace/runtime-setup/rag-wheelhouse`.

## Package facts checked 2026-10-11

Primary source: [PyPI project page for pypdf 6.20.0](https://pypi.org/project/pypdf/6.20.0/).

- Exact version: `6.20.0`
- Project description: pure-Python PDF library with text extraction support.
- License expression shown on PyPI: BSD-3-Clause.
- Python requirement: Python >=3.9 (the RunPod runtime is Python 3.12.3).
- Wheel: `pypdf-6.20.0-py3-none-any.whl`, approximately 401.7 KB.
- Wheel SHA-256, verified from the PyPI release metadata: `f003fc2014814d264fe7dd3f9d435c158e23e1a85a2233f87a0a2d6d21c914ad`.
- Direct wheel source: `https://files.pythonhosted.org/packages/18/42/a945f65cc61c739ec80f4112c4b78ed1791f25f19389c9c9e247e2/pypdf-6.20.0-py3-none-any.whl`.
- The setup script verifies SHA-256 before copying the wheel to the Global Volume and before extracting it for use.

## Parser safeguards and limits

- Source file maximum: 10 MiB (shared ingestion limit).
- Maximum pages: 300.
- Maximum extracted text: 5,000,000 characters.
- Password-protected PDFs are rejected.
- PDFs with no extractable text (typically scanned/image-only documents) are rejected with an explicit message; OCR is not yet included.
- Extracted text is labelled with page numbers before chunking.
- Unsupported/corrupt PDFs produce a controlled ingestion error.

These are defensive limits for a prototype, not a claim that parsing hostile PDFs is risk-free. Do not ingest arbitrary external PDFs into a publicly exposed service. The current gateway stays bound to loopback and requires its temporary bearer key.

## Setup, verification and persistence

Use `rag/setup_pdf_support.sh`. It downloads/verifies the pinned wheel, saves it and `SHA256SUMS` to Global Volume, and extracts the package into `/tmp/rag-deps` without changing the vLLM virtual environment. Because `/tmp` is Pod-local, rerun this setup after Pod recreation; the verified wheel on Global Volume avoids a new network download when retained.

The current gateway's launch/upgrade scripts set `PYTHONPATH=/tmp/rag-deps`, so the gateway can import pypdf when a PDF is queried. A fresh gateway deployment must run PDF setup first.

## Limitations

- Searchable text extraction only. Images, tables and multi-column layout may extract imperfectly.
- Scanned/image-only PDF OCR is not implemented.
- PDF annotation text/embedded files are not parsed.
- Excel XLSX support remains a separate future feature.
- Before production, keep this package in an explicit dependency inventory, rescan for relevant security advisories, and test representative customer PDF samples and malformed/encrypted input behaviour.
