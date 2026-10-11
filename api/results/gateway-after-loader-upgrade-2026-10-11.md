# Gateway after document-loader upgrade — 2026-10-11

## Result

**PASS: ALL GATEWAY + RAG API TESTS PASSED** in the user-provided RunPod terminal screenshot after running `api/upgrade_gateway_with_rag_smoke.sh`.

## Observed results

- New gateway and shared BM25 engine passed Python syntax compilation.
- Existing gateway process was stopped and replaced; script explicitly reported that the vLLM model server was not touched.
- Health endpoint returned `{"status":"ok","upstream":"ok","model_count":1}`.
- Unauthenticated `POST /v1/rag/ask` request was rejected with `authentication required` (expected HTTP 401).
- Authenticated document Q&A returned status `answered` and: "Employees must submit expense claims with receipts within 10 business days of the expense [Source 1]."
- The low-relevance yacht-colour question returned `status: abstained`; top BM25 score 0.69 was below the configured demo-only minimum 2.30, so generation was blocked.
- Script ended with `ALL GATEWAY + RAG API TESTS PASSED.`
- Gateway is loopback-only at `http://127.0.0.1:8010`; its temporary API key remains at `/tmp/platform-gateway.key` and was not printed or committed.

## Scope and caveat

This confirms the upgraded gateway remains functional and that the RAG endpoint still passes its smoke cases. The smoke questions used Markdown fixtures. It does **not yet** prove the live HTTP API can answer from CSV, HTML or DOCX content. Those formats have passed the separate eight-test loader suite, but an end-to-end query against one of them should be run before claiming full API integration for those formats.

The prototype remains loopback-only and is not production-ready. PDF and XLSX are not supported.
