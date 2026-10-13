# Tonight completion — FINAL ACCEPTANCE REPORT (2026-10-13)

## Verdict

**Recoverable isolated dual-model platform: VERIFIED for Qwen isolated stack + registry selection safeguards.**  
**Full production dual-serve / Gemma-main restoration: NOT completed tonight (blocked by safety rules / one-GPU).**  
Do **not** call production cutover complete.

## 1. Branch / commit / push

| Item | Value |
| --- | --- |
| Branch | `feature/qwen3.5-27b-integration` |
| Commit | `7072cab31b93e5c27abffb2e14a96a1b67e685a1` |
| Push | Pushed to `origin/feature/qwen3.5-27b-integration` |

## 2. Persistent model paths (Global Volume)

| Model | Path | Size (du) | Complete? |
| --- | --- | --- | --- |
| Gemma 4 31B | `/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it` | ~59G | VERIFIED (config+index+shards) |
| Qwen3.5-27B | `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654` | ~52G | VERIFIED (11 shards + manifest) |

Mount: `fuse.geesefs` at `/workspace` (verified via `findmnt` + Gemma marker).

## 3. Download / start / live-test

| Model | Downloaded | Verified | Started | Live chat | Live RAG |
| --- | --- | --- | --- | --- | --- |
| Gemma | prior | VERIFIED on volume | NOT running tonight | NOT TESTED tonight (GPU held by Qwen) | NOT TESTED tonight on main |
| Qwen | VERIFIED | VERIFIED | VERIFIED `:8002` | VERIFIED `QWEN_OK` | VERIFIED isolated `:8013` upload/ask/delete |

## 4. Manual model selection (end-to-end)

| Behaviour | Status |
| --- | --- |
| Explicit `qwen3.5-27b` on Qwen gateway `:8013` | VERIFIED — `platform_selection.resolved_id=qwen3.5-27b` |
| Explicit `gemma-4-31b-it` on Qwen gateway | VERIFIED refusal **HTTP 409** runtime_mismatch (no silent switch) |
| `/v1/platform/models` health flags | VERIFIED — Qwen `runtime_loaded=true`, Gemma `false` |
| Console model picker UI | NOT TESTED (console still uses configured `PLATFORM_MODEL_ID`) |
| Production default change | NOT DONE (still `gemma-4-31b-it`) |

## 5. Routing features

| Feature | Status |
| --- | --- |
| Registry dual candidates | VERIFIED |
| Deterministic mismatch refusal | VERIFIED |
| Task routing metadata in registry | VERIFIED (documented labels only) |
| Intelligent AI router | NOT BUILT (by design) |
| Cost-based auto routing | NOT BUILT |
| `ops/switch-gpu-model.sh` | TESTED BUT NOT LIVE-exercised for Gemma restore (Gemma env missing on overlay) |

## 6. Tests run

| Suite | Result |
| --- | --- |
| `models.tests.test_registry_loader` | PASS |
| `api.test_rag_conversation` | PASS |
| `rag.tests.*` + `web.test_server` | PASS (70 tests OK combined run) |
| Live Qwen direct + gateway chat | PASS |
| Live Qwen RAG upload/ask/delete | PASS |
| Main Gemma `:8010`/`:8080` E2E | NOT TESTED (services down) |

## 7. Backup / snapshot

| Item | Status |
| --- | --- |
| Prior source snapshots on volume | Present (e.g. `…861086a…`) |
| New feature-commit snapshot | **VERIFIED** `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-7072cab31b93e5c27abffb2e14a96a1b67e685a1.tar.gz` (SHA256 `4fc0fe4a40551ade2368c15721474dde07f1dc4e4638aab01b0637bbfcba1616`) |
| Gemma runtime archive | Present: `/workspace/runtime-setup/vllm-clean-env.tar.zst` (`.sha256` companion missing) |
| Qwen runtime archive | NOT created (`/workspace/runtime-setup/qwen-vllm` absent) |

## 8. Running services / GPU

| Port | Status |
| --- | --- |
| `:8002` Qwen vLLM | up |
| `:8013` isolated gateway | up (selection build) |
| `:8083` isolated console | up |
| `:8000`/`:8010`/`:8080` | down |
| GPU | A100 80GB PCIe — ~71 GiB used by Qwen |

## 9. Costs

- GPU billed while Pod runs with Qwen loaded.
- No new Azure resources created.
- Exact $/h: read from RunPod console (not asserted here).

## 10. Blockers / next action

**Blockers**

- Gemma `/tmp/vllm-clean-env` absent on this Pod overlay — restore from archive before Gemma serve.
- Production default / main ports intentionally unchanged.
- Qwen venv not archived to Global Volume yet.

**Single most important next action**

Stop Qwen when finished tonight (`ops/start-qwen-isolated.sh --stop` or Pod stop) to halt GPU spend; then restore Gemma env from `/workspace/runtime-setup/vllm-clean-env.tar.zst` and bring main `:8000`/`:8010`/`:8080` back **only with approval**.

## Evidence paths

- `/workspace/platform-diagnostics/tonight/phase1-state.json`
- `/workspace/platform-diagnostics/tonight/phase2-verify.json`
- `/workspace/platform-diagnostics/tonight/phase3-reconfirm.json`
- `ops/results/tonight-phase1-state-2026-10-13.md`
- `ops/results/qwen-live-stack-2026-10-13.md`
