# Autonomous Work Queue

**Purpose:** Shared handover for Cursor and other collaborators working on AI Platform Build.
**Current workstream:** Qwen3.5-27B integration.
**Branch:** `feature/qwen3.5-27b-integration`
**Last reported feature commit:** `78aa1da`
**Status:** Prepared locally; live Qwen download/serving has NOT been validated because RunPod SSH was unreachable.
**Owner approval boundary:** Do not make paid changes or disrupt the working Gemma/main services.

## Read first
- `docs/qwen3.5-27b-integration.md`
- `docs/azure-qwen-migration.md`
- `docs/azure-qwen-cost-estimate.md`
- Existing recovery runbook and ops scripts.

## Goal
Finish and validate Qwen3.5-27B integration on RunPod, keep Gemma as the default, preserve all source/configuration/recovery assets, then prepare (not execute) Azure migration.

## Execution protocol
1. Inspect the latest branch/commit and working tree before doing anything. Fetch/pull this file before proceeding. Preserve uncommitted work; never reset or discard it blindly.
2. Work autonomously on reversible, non-disruptive tasks. Run tests, improve docs/scripts, and report actual command outputs/exit codes.
3. If RunPod is unreachable or stopped, do not repeatedly retry or assume it is available. Continue only with safe repository work and report that live tasks are blocked.
4. Do not start/restart a billable Pod, add credits, resize compute, create paid Azure resources, or incur other new costs without explicit user approval.
5. Do not stop Gemma on :8000, change the production default, or touch main gateway :8010 / main console :8080 without explicit approval. Use isolated Qwen/test ports only after confirming GPU availability and no conflict.
6. Never overwrite/delete Gemma weights, prior snapshots, or unrelated documents. Keep large model weights out of Git. Keep recoverable source/configuration assets on persistent `/workspace` when available.
7. Do not expose credentials, tokens, private keys, or gateway keys in commits, logs, issues, or reports.
8. Before any potentially disruptive operation, inspect and document the rollback path. If it could affect the live platform, stop and request approval.
9. Do not mark Qwen integration complete until the exact model revision is downloaded and verified, the isolated runtime starts, a live request succeeds, relevant tests pass, and a recovery snapshot exists.
10. After each coherent work unit, update the status section below and commit/push only the relevant source/docs to this feature branch. Never merge into the main working branch automatically.

## Qwen acceptance checklist
- [ ] Verify current branch, commit, clean/dirty status and remote before edits.
- [ ] Verify official model revision, license, runtime requirements and compatible vLLM configuration.
- [ ] Check GPU/VRAM and disk before downloading/starting.
- [ ] Download resumably to the planned persistent path and verify file completeness/checksums where available.
- [ ] Keep Qwen dependencies isolated from Gemma's environment.
- [ ] Verify startup preflight refuses unsafe GPU/service conflicts.
- [ ] Confirm model registry and API model selection are backward-compatible.
- [ ] Run local automated suites and record results.
- [ ] When the user has started the billable Pod and SSH is reachable, run live checks; do not claim success before this.
- [ ] If GPU memory requires stopping Gemma, pause until explicit approval.
- [ ] Test Qwen through the isolated gateway/console; preserve the main :8010/:8080 services.
- [ ] Re-test Gemma after Qwen is stopped and restore its normal service safely.
- [ ] Create a versioned recovery snapshot on `/workspace`; verify it exists.
- [ ] Update the playbook/runbook with exact observed commands, results, limitations and rollback.
- [ ] Prepare Azure migration and cost notes only; do not provision or upload to paid Azure resources without approval.

## Status log
- 2026-10-13: Previous report says feature branch `feature/qwen3.5-27b-integration` at `78aa1da`, pushed; 69 local tests reported passing; Qwen download/live serving not started; Pod SSH unreachable; no new snapshot because `/workspace` inaccessible.
- Next safe action: inspect latest repository state and validate scripts/tests/doc consistency. Live installation remains blocked until the user starts the existing Pod and SSH is reachable.

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
