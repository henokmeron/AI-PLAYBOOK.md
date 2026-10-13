# Qwen3.5-27B integration (RunPod-first)

## Baseline (inspected 2026-10-13)

| Item | Value |
| --- | --- |
| Branch started from | `cursor/local-web-console` @ `861086a` |
| Feature branch | `feature/qwen3.5-27b-integration` |
| Existing model | Gemma 4 31B-it under `/workspace/gemma-4-31B-it/...` |
| Existing vLLM | `/tmp/vllm-clean-env`, observed historically as vLLM 0.31.0 |
| Main ports | Gemma `:8000`, gateway `:8010`, console `:8080` |
| Doc Q&A test ports | `:8012` / `:8082` |
| Planned Qwen ports | inference `:8002`, gateway `:8013`, console `:8083` |
| Official model | `Qwen/Qwen3.5-27B`, license Apache-2.0 |
| Pinned revision | `fc05daec18b0a78c049392ed2e771dde82bdf654` |
| Files | 11 `model.safetensors-*-of-*.safetensors` shards + tokenizer/config |
| Official serving note | Qwen card asks for vLLM **main/nightly** in a **fresh** environment |

## Safest implementation (chosen)

1. Keep Gemma as `production` / `active_model_id` in `models/registry.yaml`.
2. Store Qwen weights at `/workspace/models/Qwen3.5-27B/<revision>/` (never in Git).
3. Install Qwen dependencies only in `/tmp/vllm-qwen-env` (later archive under `/workspace/runtime-setup/qwen-vllm`).
4. Never upgrade or extract over `/tmp/vllm-clean-env`.
5. Do not load Gemma and Qwen on one GPU at the same time.
6. Serve Qwen only on `:8002` after confirming `:8000` is down / GPU free.
7. Use isolated gateway `:8013` for Qwen validation; leave `:8010`/`:8080` untouched.

## Live validation (2026-10-13) — download + serve + smoke complete

| Item | Observed |
| --- | --- |
| Weights | `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654` (11 shards) |
| vLLM | `/tmp/vllm-qwen-env`, `127.0.0.1:8002`, smoke content `QWEN_OK` |
| Gateway / console | `127.0.0.1:8013` / `127.0.0.1:8083` (gateway smoke `QWEN_OK`) |
| Production default | Still Gemma (`models/registry.yaml` → `production: gemma-4-31b-it`) |
| Main ports | `:8010` / `:8080` **untouched** (not listening during this validation) |
| Evidence | `ops/results/qwen-live-stack-2026-10-13.md`, `ops/results/qwen-integration-status-2026-10-13.md`, `/workspace/platform-diagnostics/qwen/` |
| Integration scope | **Isolated only** — not production default; main `:8010`/`:8080` not connected to Qwen |

## Prior blockers (cleared for live serve; retained for history)

1. Earlier SSH endpoint `216.81.245.29:48480` was refused when the Pod was stopped; later session used a reachable SSH endpoint after the operator started the Pod.
2. **Cursor-browser probe (2026-10-13):** see `ops/results/runpod-browser-probe-2026-10-13.md` (balance/Pod-stop context at that time).
3. Concurrent Gemma+Qwen on one GPU remains refused by `ops/start-qwen-isolated.sh`.
4. Tracking: GitHub issue [#1](https://github.com/henokmeron/AI-PLAYBOOK.md/issues/1) + `AUTONOMOUS_WORK_QUEUE.md`.

## Operator sequence (after Pod is running)

```bash
# 1) Confirm Gemma/main stack without changing it
bash ops/start-platform.sh --check
bash ops/preflight-recovery.sh

# 2) Download Qwen to Global Volume (resumable)
bash ops/download-qwen3.5-27b.sh
bash ops/download-qwen3.5-27b.sh --check

# 3) Isolated nightly vLLM env for Qwen only
bash ops/install-qwen-vllm-env.sh
bash ops/install-qwen-vllm-env.sh --check

# 4) ONLY with approval to free the GPU: stop Gemma vLLM, then:
bash ops/start-qwen-isolated.sh --start
bash ops/start-test-gateway-qwen.sh --start

# 5) Smoke
curl -s http://127.0.0.1:8002/v1/models
curl -s http://127.0.0.1:8002/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654","messages":[{"role":"user","content":"Reply with exactly: qwen works"}],"max_tokens":16}'

# 6) Stop Qwen and restore Gemma with the existing main recovery helpers when finished
bash ops/start-qwen-isolated.sh --stop
# then, only if Gemma was stopped with approval: bash ops/start-platform.sh --start
```

## What is deferred / untested

- Vision / multimodal inputs
- Tool calling (`--enable-auto-tool-choice`)
- Long-context (>8192) on the current Pod
- Promoting Qwen to production default
- Azure GPU provisioning and Blob upload of Qwen weights

## Related docs

- Azure portability (prepare only): `docs/azure-qwen-migration.md`
- Cost worksheet: `docs/azure-qwen-cost-estimate.md`
- Registry: `models/registry.yaml`
