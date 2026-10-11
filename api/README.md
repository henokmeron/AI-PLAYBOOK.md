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
