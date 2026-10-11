# Gateway and RAG API live test — 2026-10-11

## Result

**PASS: ALL GATEWAY + RAG API TESTS PASSED** in the user's RunPod terminal screenshot after the guarded gateway upgrade.

## Observed checks

- The updated gateway and shared retrieval engine passed Python syntax compilation before the upgrade.
- The old gateway process (PID 2953) was stopped; the vLLM server was explicitly left running.
- New gateway health endpoint returned `{"status":"ok","upstream":"ok","model_count":1}`.
- An unauthenticated request to `POST /v1/rag/ask` returned `{"error":"authentication required"}`; expected HTTP 401 was confirmed.
- An authenticated RAG request returned `status: answered`, the correct answer "Employees must submit expense claims with receipts within 10 business days of the expense [Source 1].", and source filenames `expenses-policy.md` and `employee-handbook.md`.
- An authenticated low-relevance question returned `status: abstained`, no source chunks, and retrieval reason `below_min_score` with top score 0.69 and minimum score 2.3. The model was not called for this request.
- Final script output confirmed all gateway + RAG API smoke tests passed.
- Gateway remains loopback-only at `http://127.0.0.1:8010`; temporary API key remains at `/tmp/platform-gateway.key`, not printed or committed.

## Interpretation

The single-request API contract is verified end-to-end on the current local Pod: client → authenticated gateway → document retrieval → relevance gate → vLLM/Gemma → answer with source metadata.

This is still a local prototype. It is not exposed publicly and is not production-ready. The key is temporary and shared; there is no real user identity, tenant isolation, durable audit logging, managed secrets, HTTPS endpoint for external consumers, or corpus-specific threshold calibration beyond the fictional demo files.
