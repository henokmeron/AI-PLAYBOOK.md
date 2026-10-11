# Local authenticated API gateway

## Why this is the next platform boundary

Business integrations should not each talk directly to the model server. A gateway gives our future RAG service, Outlook/Excel connectors and tools one consistent API boundary where authentication, limits and policy can be enforced.

## Current prototype scope

- Standard-library Python; no new packages.
- Default listener: `127.0.0.1:8010` (loopback only).
- Upstream vLLM: `http://127.0.0.1:8000/v1`.
- `GET /health`: checks whether the upstream models endpoint is reachable, returning a count but not model names.
- `POST /v1/chat/completions`: requires a bearer API key; proxies non-streaming JSON requests to vLLM.
- Rejects unauthenticated calls, unsupported paths, invalid JSON, oversized payloads and streaming requests.
- Basic per-client in-memory rate limit: 30 requests/minute.
- Logs route/status only; it does not log prompts, completion bodies or credentials.

## One-command demo on the current RunPod Pod

Keep vLLM running in the first terminal. In the second terminal run:

```bash
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/api/run_gateway_smoke.sh -o /tmp/run_gateway_smoke.sh && bash /tmp/run_gateway_smoke.sh
```

The script fetches the gateway, creates a random API key stored only on the Pod's local `/tmp` filesystem, starts the gateway in the background, and checks health, unauthorized rejection, and an authenticated real generation request. It will not print the secret. It leaves the local gateway running after all checks pass, with log at `/tmp/platform-gateway.log`, PID file at `/tmp/platform-gateway.pid`, and key file at `/tmp/platform-gateway.key`.

To stop the local gateway after testing:

```bash
kill "$(cat /tmp/platform-gateway.pid)"
```

The generated key is temporary and will be lost when local temporary storage is cleared. Do not copy it into GitHub, source files or screenshots.

## Security limitations

This is **not a production or publicly exposed gateway**. It is deliberately bound to loopback. Do not change `PLATFORM_HOST` to `0.0.0.0` or expose port 8010 publicly. Before integration with external apps/customers, replace or harden this prototype with HTTPS termination, managed secrets/rotation, real user/service identity, tenant isolation, durable audit records, robust rate/quota controls, request/response schemas, monitoring, cancellation/timeouts, policy enforcement and security testing. The current in-memory limit is not distributed, and a single shared key is suitable only for local testing.


## Gateway smoke test result — 2026-10-11

The user ran `api/run_gateway_smoke.sh` on the current Pod. Screenshot confirms:
- `GET /health` returned `{"status":"ok","upstream":"ok","model_count":1}`.
- Unauthenticated `POST /v1/chat/completions` returned HTTP 401 with `authentication required`.
- An authenticated request passed through the gateway and Gemma returned `gateway works`.
- The loopback-only gateway remains running at `http://127.0.0.1:8010`.
- The random API key is held in the Pod-local file `/tmp/platform-gateway.key` and was not printed or saved to GitHub. It is ephemeral; do not use it for a production deployment.

The next integration test runs document Q&A through this gateway with the bearer key. Do not bypass the gateway for that test, and do not expose port 8010 publicly.


## RAG client-through-gateway test passed — 2026-10-11

The user ran `rag/ask_documents.py` with the gateway URL `http://127.0.0.1:8010/v1`, explicit Gemma model ID, and `--api-key-file /tmp/platform-gateway.key`. It retrieved `expenses-policy.md` first, then the gateway and Gemma returned the correct answer "10 business days" with `[Source 1]`. Report: [rag-through-gateway-2026-10-11.md](../rag/results/rag-through-gateway-2026-10-11.md).

This proves the command-line RAG client can authenticate to and use the gateway, but it is not yet a single HTTP RAG endpoint for a business app. Next: build `POST /v1/rag/ask` behind the same authenticated front door. Keep the service loopback-only until production security exists.


## Single-endpoint document Q&A — implementation added, test pending

The upgraded gateway now exposes `POST /v1/rag/ask`, using shared lexical retrieval from `rag/rag_engine.py`. A request only needs a question and optional `top_k`; the response includes answer status, answer text, cited source metadata (file, chunk and retrieval score), and retrieval information. It uses the same bearer key as `/v1/chat/completions` and the same rate limiter.

- API contract: [OpenAPI specification](openapi.yaml).
- Shared retrieval engine: [rag/rag_engine.py](../rag/rag_engine.py).
- Run the guarded upgrade/test from the current Pod: [upgrade_gateway_with_rag_smoke.sh](upgrade_gateway_with_rag_smoke.sh).

### Upgrade and test the currently running gateway

Keep the vLLM terminal running. The test script downloads and syntax-checks the new gateway and engine before stopping the old gateway. It backs up the previous gateway code and attempts to roll back if the new health/auth/RAG checks fail. Run in the second terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/api/upgrade_gateway_with_rag_smoke.sh -o /tmp/upgrade_gateway_with_rag_smoke.sh && bash /tmp/upgrade_gateway_with_rag_smoke.sh
```

The script preserves the current temporary API key, keeps the listener on `127.0.0.1:8010`, tests that unauthenticated RAG requests return 401, tests a correct expense answer with source metadata, and tests that an irrelevant question is blocked before generation. It never stops vLLM and does not print the key.

### Example API request (local development only)

```bash
curl -sS -X POST http://127.0.0.1:8010/v1/rag/ask \
  -H "Authorization: Bearer $(cat /tmp/platform-gateway.key)" \
  -H 'Content-Type: application/json' \
  -d '{"question":"How many business days do employees have to submit expense receipts?","top_k":4}'
```

Do not expose this loopback-only prototype publicly. The shared key is temporary; the BM25 score threshold is demo-corpus-only. Production needs proper identity/tenancy, HTTPS, secret management, access-controlled document sources, durable auditability, calibrated retrieval, monitoring and security review.


The fresh deployment smoke script (`api/run_gateway_smoke.sh`) now also downloads the shared `rag_engine.py` module and checks the new `/v1/rag/ask` route, including unauthenticated rejection, supported answer plus source metadata, and low-relevance abstention. For an already-running old gateway, use the guarded `api/upgrade_gateway_with_rag_smoke.sh` instead; it preserves the key and has a rollback path.


## Live RAG API test passed — 2026-10-11

The user ran the guarded upgrade script against the current Pod. It syntax-checked the new gateway and shared retrieval engine, restarted only the gateway, confirmed upstream health, rejected unauthenticated RAG requests, returned the correct source-cited expense deadline for an authenticated RAG request, and abstained on the low-relevance yacht question before generation. Final output: `ALL GATEWAY + RAG API TESTS PASSED.`

Detailed evidence: [gateway-rag-api-live-2026-10-11.md](results/gateway-rag-api-live-2026-10-11.md).

The API is verified only as a local loopback prototype. It must not be exposed publicly or treated as production-ready.


### Document loader dependency

The updated gateway imports `rag_engine.py`, which now imports `document_loaders.py`. Both files must be present in the same directory as `platform_gateway.py` (the scripts place them under `/tmp`). The guarded upgrade/fresh-start scripts now download and syntax-check the loader module. Run the RAG parser unit tests before upgrading the live gateway.


## Document-loader tests passed — 2026-10-11

The focused parser suite completed with 8/8 tests passing. This clears the preflight for the guarded in-place gateway upgrade, which will fetch `document_loaders.py`, `rag_engine.py`, and `local_gateway.py`, syntax-check them, then run the end-to-end RAG API checks. The upgrade script preserves the API key and has a rollback path; it restarts only the gateway, not vLLM.
