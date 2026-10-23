# Autonomous Work Queue

**Purpose:** Shared handover for Cursor and other collaborators working on AI Platform Build.
**Current workstream:** Qwen3.5-27B integration.
**Branch:** `feature/qwen3.5-27b-integration`
**Last reported feature commit:** IT Helpdesk on `feature/qwen-a100-start-hardening` (see tip after push).
**Tracking issue:** https://github.com/henokmeron/AI-PLAYBOOK.md/issues/1
**Status:** IT Helpdesk mock-tested in source. Active Pod `4lvr54b0wmkz6c` (A100 SXM, same volume) after loss of `1cj381fjuujeq7`. Prefer **Stop** when idle. Helpdesk live-vs-Qwen **NOT TESTED** until console redeploy.
**Owner approval boundary:** Do not create new paid Pods, delete volume assets, or restore Gemma onto the GPU without explicit approval. Prefer stopping idle Pods to limit GPU cost while leaving the volume intact.

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
- 2026-10-23: Automation approval boundary and repair stages are in `70e731a54218afc4fa8d05792af473a1a9523c9c`. Power Automate live is NOT TESTED. The repair fixture is not the second endpoint. `python -m ops.run_tests` was 49 modules, 0 failed, exit 0, about 143 seconds. Gateway pid 109608 and console pid 109642 loaded that commit. Health 200/200/200. Qwen pid 1826 was not signalled. Production **NO-GO**. Mailbox content match is still unproven. The next owner action is to name one harmless phrase that is already in the mailbox.
- 2026-10-23: Shutdown save. Document replace keeps the previous version and download requires the owner. Helpdesk tickets cannot silently lower severity or run a repair before approval. Local tests passed (71 gateway/console/library tests, exit 0; 6 ticket tests, exit 0; `python -m ops.run_tests` 47 modules, 0 failed, exit 0, about 163 seconds, before the ticket module existed). Not deployed onto the running gateway or console. Qwen left running. Production **NO-GO**. Mailbox content match is still unproven. Next start is `bash /workspace/ai-platform-release/START.sh` after the pod is started again; that loads weights from the volume and is not a few seconds.
- 2026-10-23: Offline quiz regression is `3fc5909622e3efcbd24a620af80f76d846c4875e` (2.4 ratio packs 6/drops 12; 4.4 packs 17/drops 1). Mailbox content match is not proven (list count 9, search count 0). The gate requires `mailbox_content_match_ok`. Console pid 97009 loaded `cbf52ec5405056734302a05db2970f7362c57c0e`. Qwen pid 1826 and gateway pid 87842 were not restarted. Production **NO-GO**. Do not repeat the handbook PDF quiz or the `the` search. Next owner actions: a harmless phrase known to be in the mailbox, a second Windows PC, Blackwell approval, a fresh machine for recovery, and a weight-copy destination.
- 2026-10-22: Coordinator integrated specialist edits onto `main` above `409c891`. Microsoft URLs use directory `d595636e-9ef4-4890-b8a7-bde8dd5cab03`. Live mail **NOT CONFIGURED**. A100 `gom4ualdk47qrj` was not restarted. Production **NO-GO**. Open gates: deployed commit, mail end-to-end, second endpoint, Blackwell, fresh-environment recovery.
- 2026-10-13: Feature work at `78aa1da` (registry/scripts/docs) then `99fac1c` (Cursor-browser probe). Local suites reported 69 OK. Qwen download/live serving not started.
- 2026-10-13 (browser probe): Cursor Browser could see logged-in RunPod console. No running Pod / no web terminal. Global Volume **New model container** `cmv2p5m0d000007jk9o3931ea` present (~66.4 GB, 1551 objects). Balance **−$0.23**. SSH `216.81.245.29:48480` refused. Evidence: `ops/results/runpod-browser-probe-2026-10-13.md`.
- 2026-10-13 (issue #1 safe repo phase): Fast-forwarded to include this queue file (`2b319cb`). Re-ran local suites: **69 tests OK** (`models.tests.test_registry_loader`, `api.test_rag_conversation`, `rag.tests.test_rag_engine`, `rag.tests.test_document_loaders`, `rag.tests.test_document_library`). Confirmed revision `fc05daec18b0a78c049392ed2e771dde82bdf654`, ports `:8002`/`:8013`/`:8083`, `production: gemma-4-31b-it`, and Gemma-conflict guards in `ops/start-qwen-isolated.sh` are consistent across scripts/docs. No Pod started; no main services touched.
- 2026-10-13 (live isolated stack): SSH reachable. Model downloaded/verified (11 shards). vLLM on `127.0.0.1:8002` (PID 4515) smoke **PASS** (`QWEN_OK`). Isolated gateway `:8013` + console `:8083` started and gateway smoke **PASS**. Evidence: `ops/results/qwen-live-stack-2026-10-13.md` and `/workspace/platform-diagnostics/qwen/`. Gemma production default unchanged; `:8010`/`:8080` untouched. Pod/volume left intact.
- 2026-10-13 (honest integration status): **Partially yes — not fully the platform** (historical). Superseded by 2026-10-14 status.
- 2026-10-13 (tonight completion / post-acceptance): Dual-model registry; Qwen runtime archived to `/workspace/runtime-setup/qwen-vllm/`.
- 2026-10-14: **Qwen is the production default.** A100 SXM cold start + main `:8002`/`:8010`/`:8080` E2E (chat, text/PDF/XLSX RAG, console UI) **VERIFIED**. Snapshot `0b49946` checksum OK. Evidence: `ops/results/qwen-integration-status-2026-10-14.md`, `docs/AGENT_HANDOFF.md`.
- 2026-10-15 (CUDA-13 replace): Pod `vx4oe3oyfsqnz8` driver 580; `START.sh` + E2E **VERIFIED**. Evidence: `docs/results/runpod-cuda13-replace-2026-10-15.md`.
- 2026-10-15 (agent loop): Async progress, cancel, and auditable task history at `0165267` (90 agent + 23 web tests OK). Pod **STOPPED**.
- 2026-10-15 (agent queue + IT): Serial queue, IT incident schema/playbook, richer Agent UI (95 agent + 23 web OK).
- 2026-10-15 (live resume): Migrate API failed; new Pod `1cj381fjuujeq7` + volume; tip `a680580`; E2E **FAILS:NONE**; Agent async/cancel **VERIFIED**. **Next:** Stop Pod when idle; continue product features offline or after Start.
- 2026-10-18: From this Linux agent, `154.54.102.40:13212` and `216.81.248.126:19091` refused connections. No `id_ed25519` here. Pod health not read. `START.sh` not run. Local unittest of ops centre, helpdesk, history, queue, and web console: **40 OK**. Volume was not touched.

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
