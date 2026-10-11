# Excel XLSX support decision and dependency record

## Decision

Add read-only ingestion of Excel `.xlsx` workbooks using `openpyxl==3.1.5`. The dependency and its required companion `et-xmlfile==2.0.0` are extracted to `/tmp/rag-deps`, never installed into the working vLLM virtual environment. `defusedxml==0.7.1` is included to provide hardened XML parsing integration with openpyxl.

## Package provenance checked 2026-10-11

- [openpyxl 3.1.5 on PyPI](https://pypi.org/project/openpyxl/): MIT license, Python >=3.8, reads/writes Office Open XML workbooks; its published project notes that XML bomb protection requires `defusedxml`.
- [et-xmlfile 2.0.0 on PyPI](https://pypi.org/project/et-xmlfile/): MIT license, Python >=3.8; used by openpyxl.
- [defusedxml 0.7.1 on PyPI](https://pypi.org/project/defusedxml/0.7.1/): PSF license; provides protection helpers for XML attacks.

The exact wheels and SHA-256 digests are pinned in `rag/requirements-xlsx.txt`. `rag/setup_xlsx_support.sh` downloads them to local temporary files, verifies hashes, saves verified wheels and `XLSX-SHA256SUMS` to the Global Volume, and safely extracts them to `/tmp/rag-deps`.

## Data extraction behaviour

- Only `.xlsx` is supported here; legacy `.xls`, macro-enabled `.xlsm`, and writing/updating workbooks are out of scope.
- All worksheets are read-only; sheet names and visibility state are written into the extracted text.
- Non-empty cells are represented with their cell coordinates, e.g. `C2=27500`, and rows retain their row number.
- `data_only=True`: formulas are **not recalculated**. For formula cells, the reader uses a cached value stored in the workbook, if one exists. If a workbook has no cached result, the formula cell can appear empty. Users should open/recalculate and save source workbooks in Excel/LibreOffice before ingestion if formula outputs matter.
- Date/time values are rendered using ISO format.
- Resource limits: compressed/source file max 10 MiB; XLSX total uncompressed ZIP contents max 100 MiB; individual ZIP component max 40 MiB; at most 50 worksheets; 100,000 rows and 512 columns per worksheet; 5 million characters of extracted text.
- Invalid, corrupt, oversized or empty workbooks are rejected with a controlled ingestion error.

These safeguards are for a prototype and do not make arbitrary untrusted workbooks risk-free. Do not expose the service publicly or ingest confidential data before access controls, review and broader validation are in place.

## Testing sequence

1. Run `rag/setup_xlsx_support.sh`.
2. Fetch `document_loaders.py`, `rag_engine.py`, and `test_document_loaders.py`; run syntax compilation and focused parser tests with `PYTHONPATH=/tmp/rag-deps`.
3. After tests pass, run the guarded gateway upgrade.
4. Run `api/test_format_ingestion.sh` to test CSV, DOCX, PDF, and XLSX through a temporary gateway on port 8011.
5. Record the screenshot/output; do not call XLSX end-to-end verified until its integration test passes.

PDF parser wheel/dependency files in the same Global Volume wheelhouse are preserved. No change is made to the working vLLM environment.
