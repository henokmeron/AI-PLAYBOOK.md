# Gateway after PDF dependency upgrade — 2026-10-11

## Result

**PASS: ALL GATEWAY + RAG API TESTS PASSED** in the user's terminal screenshot after the guarded gateway upgrade that checks for the isolated `pypdf==6.20.0` dependency.

## Screenshot-confirmed checks

- Gateway health endpoint returned `{"status":"ok","upstream":"ok","model_count":1}`.
- Unauthenticated RAG requests were rejected.
- Authenticated RAG request returned `status: answered`, with the factual answer that expense receipts are due within 10 business days and source metadata including `expenses-policy.md`.
- Low-relevance yacht-colour request returned `status: abstained`; top score 0.69 was below minimum score 2.3, and generation was blocked.
- Script ended with `ALL GATEWAY + RAG API TESTS PASSED.`
- Gateway remains local-only at `http://127.0.0.1:8010`; the vLLM model server was not restarted.

## Scope

This verifies gateway startup and the existing Markdown RAG smoke cases after enabling the PDF dependency. It does not yet verify end-to-end queries from CSV, DOCX or PDF. That is the next test: run `api/test_format_ingestion.sh` against an isolated second gateway at loopback port 8011. The main gateway at 8010 and vLLM at 8000 should remain untouched.
