# Four-format RAG API integration — 2026-10-11

## Result

**PASS: ALL CSV/DOCX/PDF/XLSX INTEGRATION TESTS PASSED** in the user's RunPod terminal screenshot.

The test used a temporary loopback gateway on port 8011. It confirmed the configured parsers were available, exercised each file format through the authenticated `POST /v1/rag/ask` endpoint, and cleaned up the temporary gateway and fixture directory afterwards.

## Observed outcomes

| Format | Question | Answer returned | Source filename |
|---|---|---|---|
| CSV | At which gate must visitors check in? | Visitors must check in at Gate C | `visitor-rules.csv` |
| DOCX | When is Project Helios launch review? | The review is scheduled for 18 November | `launch-review.docx` |
| PDF | When is Project Orion purchase order review? | The review takes place on 23 November | `project-review.pdf` |
| XLSX | What is the Q4 marketing budget? | The Q4 marketing budget is 27,500 | `department-budget.xlsx` |

All four responses returned `status: answered`, source labels, and the expected source filename. The XLSX answer used a formatted number (27,500), which was correctly validated by the test.

## Cleanup and isolation

The screenshot confirms: `Temporary format-test gateway stopped; existing gateway at 127.0.0.1:8010 and vLLM remain untouched.`

## Interpretation and scope

This proves that each of the four supported formats works for the specific small fictional fixture through the current local HTTP RAG API. It does not guarantee extraction quality for arbitrary business files, merged/formatted spreadsheet interpretation, formulas that lack cached results, scanned PDFs, or arbitrary PDF table layouts.

The main gateway remains local-only at `http://127.0.0.1:8010`; the model server remains local at `http://127.0.0.1:8000`. This prototype is not production-ready and must not be exposed publicly.
