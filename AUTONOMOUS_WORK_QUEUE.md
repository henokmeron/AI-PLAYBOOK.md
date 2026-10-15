# Autonomous Work Queue

**Purpose:** Shared handover for Cursor and other collaborators working on AI Platform Build.
**Current workstream:** Qwen3.5-27B integration.
**Branch:** `feature/qwen3.5-27b-integration`
**Last reported feature commit:** `main` and both feature branches match. Qwen routing is `c232323`. Completion audit is `docs/results/completion-audit-2026-10-14.md`.
**Tracking issue:** https://github.com/henokmeron/AI-PLAYBOOK.md/issues/1
**Status:** Qwen is the RunPod-first production default, but on 2026-10-15 Pod `1g41ejmd99iyun` had the volume mounted and the weights present while `:8002`/`:8010`/`:8080` were down. Do not assume the old SSH port `11165`. See `docs/AGENT_HANDOFF.md`.
**Owner approval boundary:** Do not create new paid Pods, merge to `main`, delete volume assets, or restore Gemma onto the GPU without explicit approval. Prefer stopping idle Pods to limit GPU cost while leaving the volume intact.

## Read first
- `docs/qwen3.5-27b-integration.md`
- `docs/azure-qwen-migration.md`
- `docs/azure-qwen-cost-estimate.md`
- `ops/results/runpod-browser-probe-2026-10-13.md`
- Existing recovery runbook and ops scripts.

## Goal
Keep Qwen3.5-27B as the RunPod-first production default, preserve volume recovery assets, keep Gemma optional (409 while Qwen is loaded), and treat Azure as optional/deferred.

## Execution protocol
1. Inspect the latest branch/commit and working tree before doing anything. Fetch/pull this file before proceeding. Preserve uncommitted work; never reset or discard it blindly.
2. Work autonomously on reversible, non-disruptive tasks. Run tests, improve docs/scripts, and report actual command outputs/exit codes.
3. If RunPod is unreachable or stopped, do not repeatedly retry or assume it is available. Continue only with safe repository work and report that live tasks are blocked.
4. Do not start/restart a billable Pod, add credits, resize compute, create paid Azure resources, or incur other new costs without explicit user approval.
5. Do not load Gemma onto the GPU or change the Qwen production default without explicit approval. The live main ports are `:8002`/`:8010`/`:8080` for Qwen. Use isolated test ports for risky experiments.
6. Never overwrite/delete Gemma weights, prior snapshots, or unrelated documents. Keep large model weights out of Git. Keep recoverable source/configuration assets on persistent `/workspace` when available.
7. Do not expose credentials, tokens, private keys, or gateway keys in commits, logs, issues, or reports.
8. Before any potentially disruptive operation, inspect and document the rollback path. If it could affect the live platform, stop and request approval.
9. Do not mark Qwen integration complete until the exact model revision is downloaded and verified, the isolated runtime starts, a live request succeeds, relevant tests pass, and a recovery snapshot exists.
10. After each coherent tested change, commit it, fast-forward `main` to the same commit, and push `main` and the feature branches. Never force-push. Never restart the live Pod just because GitHub moved.

## Qwen acceptance checklist
- [x] Verify current branch, commit, clean/dirty status and remote before edits.
- [x] Verify official model revision, license, runtime requirements and compatible vLLM configuration.
- [x] Check GPU/VRAM and disk before downloading/starting. *(live: ~71 GiB GPU used by Qwen after load; weights on `/workspace`)*
- [x] Download resumably to the planned persistent path and verify file completeness/checksums where available. *(11 `model.safetensors-*-of-*` shards; manifest under `/workspace/models/Qwen3.5-27B/manifests/`)*
- [x] Keep Qwen dependencies isolated from Gemma's environment. *(`/tmp/vllm-qwen-env` installed live; Gemma env not overwritten)*
- [x] Verify startup preflight refuses unsafe GPU/service conflicts. *(code review + live isolated start on `:8002` only)*
- [x] Confirm model registry and API model selection. *(production `qwen3.5-27b`; Gemma selection while Qwen loaded → 409)*
- [x] Run local automated suites and record results.
- [x] When the user has started the billable Pod and SSH is reachable, run live checks; do not claim success before this.
- [x] One GPU: Gemma stays down while Qwen serves.
- [x] Isolated stack validated historically (`:8013`/`:8083`); main `:8010`/`:8080` now serve Qwen on A100 SXM (**VERIFIED** 2026-10-14).
- [ ] Re-test Gemma only if the owner explicitly requests a GPU switch away from Qwen.
- [x] Versioned recovery snapshot on `/workspace` verified (`…-0b49946.tar.gz` checksum OK).
- [x] Update the playbook/runbook with exact observed commands, results, limitations and rollback.
- [x] Prepare Azure migration and cost notes only; do not provision or upload to paid Azure resources without approval.

## Status log
- 2026-10-13: Feature work at `78aa1da` (registry/scripts/docs) then `99fac1c` (Cursor-browser probe). Local suites reported 69 OK. Qwen download/live serving not started.
- 2026-10-13 (browser probe): Cursor Browser could see logged-in RunPod console. No running Pod / no web terminal. Global Volume **New model container** `cmv2p5m0d000007jk9o3931ea` present (~66.4 GB, 1551 objects). Balance **−$0.23**. SSH `216.81.245.29:48480` refused. Evidence: `ops/results/runpod-browser-probe-2026-10-13.md`.
- 2026-10-13 (issue #1 safe repo phase): Fast-forwarded to include this queue file (`2b319cb`). Re-ran local suites: **69 tests OK** (`models.tests.test_registry_loader`, `api.test_rag_conversation`, `rag.tests.test_rag_engine`, `rag.tests.test_document_loaders`, `rag.tests.test_document_library`). Confirmed revision `fc05daec18b0a78c049392ed2e771dde82bdf654`, ports `:8002`/`:8013`/`:8083`, `production: gemma-4-31b-it`, and Gemma-conflict guards in `ops/start-qwen-isolated.sh` are consistent across scripts/docs. No Pod started; no main services touched.
- 2026-10-13 (live isolated stack): SSH reachable. Model downloaded/verified (11 shards). vLLM on `127.0.0.1:8002` (PID 4515) smoke **PASS** (`QWEN_OK`). Isolated gateway `:8013` + console `:8083` started and gateway smoke **PASS**. Evidence: `ops/results/qwen-live-stack-2026-10-13.md` and `/workspace/platform-diagnostics/qwen/`. Gemma production default unchanged; `:8010`/`:8080` untouched. Pod/volume left intact.
- 2026-10-13 (honest integration status): **Partially yes — not fully the platform** (historical). Superseded by 2026-10-14 status.
- 2026-10-13 (tonight completion / post-acceptance): Dual-model registry; Qwen runtime archived to `/workspace/runtime-setup/qwen-vllm/`.
- 2026-10-14: **Qwen is the production default.** A100 SXM cold start + main `:8002`/`:8010`/`:8080` E2E (chat, text/PDF/XLSX RAG, console UI) **VERIFIED**. Snapshot `0b49946` checksum OK. Evidence: `ops/results/qwen-integration-status-2026-10-14.md`, `docs/AGENT_HANDOFF.md`.
- **Next action requiring owner:** the idle A100 is billing at $1.79/hour with a balance near $4.89. Stopping it, or approving `START.sh` on the already-running Pod, is the owner's call. Microsoft sign-in still needs a work or school account that can open Entra app registrations. The personal account returned AADSTS16000. Do not paste a client id into chat.

## Required handover format
Report briefly:
1. Branch + full HEAD SHA + push status
2. What changed
3. Exact tests/commands and observed exit codes
4. Live checks vs not run
5. Snapshot path (or why unavailable)
6. Blockers/approval needed
7. Exact next action

**Important:** This file is a shared instruction/status source, not an execution trigger by itself. Cursor must be running or otherwise configured to poll/act on repository changes for unattended work to occur.
