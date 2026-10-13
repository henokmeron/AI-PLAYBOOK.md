# Persistent build and recovery policy

## Goal

This is a reusable AI platform build, not a disposable demo. Every meaningful code/configuration change must have a source-of-truth commit in GitHub and a versioned source snapshot on the mounted RunPod Global Volume. Runtime assets needed to recreate the environment also belong on persistent storage. Pod-local `/tmp` files are working copies/cache only, never the only backup.

## Storage responsibilities

### GitHub — canonical version history
- All source code, parser implementations, API endpoints, tests, setup/upgrade scripts, API schema, runbooks, decisions and evaluation reports.
- Every meaningful change is committed with a message. This preserves diffs and the commit history, which an archive alone cannot provide.
- Do not store API keys, passwords, tokens, customer documents or model weights in GitHub.

Repository: `henokmeron/AI-PLAYBOOK.md`.

### RunPod Global Volume mounted at `/workspace` — persistent local build/recovery copy
- Full repository source archive pinned to a 40-character Git commit SHA, stored under `/workspace/ai-platform-backups/source-snapshots/`.
- Manifest, commit metadata and SHA-256 checksums under `/workspace/ai-platform-backups/manifests/`.
- Copies of deployed runtime Python files under `/workspace/ai-platform-backups/deployed-runtime/`, separate from latest GitHub source so drift is visible.
- Model files under `/workspace/gemma-4-31B-it/`.
- Existing vLLM environment archive, frozen requirements, runtime manifest and installer under `/workspace/runtime-setup/`.
- Verified PDF/XLSX parser wheels and checksum lists under `/workspace/runtime-setup/rag-wheelhouse/`.
- Managed business document collections, after the document-management feature is validated and enabled, under `/workspace/rag-managed-docs/`. Do not place real customer data there until access control, retention, tenancy, encryption and backup policy are designed.

### Pod-local `/tmp` — temporary working state only
Examples include `/tmp/vllm-clean-env`, the active gateway script, temporary API key, temporary parser extraction, test fixtures and logs. These can disappear when a Pod is recreated. The key is intentionally temporary and must not be persisted to source archives/manifests. Packages used by the model are recreated from the saved runtime environment archive; parser wheels are re-extracted from the Global Volume wheelhouse.

### Azure — optional deferred off-platform backup
Azure is **not required** for the RunPod-first release. The Global Volume at `/workspace` plus GitHub are the operational authorities for first-release recovery.
If an independent Azure Blob copy already exists, it may be kept as an optional off-platform backup. Do not delete Azure account resources unless the operator explicitly chooses to. Do not block startup or recovery on Azure availability.

## How to snapshot the current source

After the script is committed to GitHub and the Global Volume is mounted at `/workspace`, run:

```bash
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/ops/sync_global_volume.sh -o /tmp/sync_global_volume.sh && bash -n /tmp/sync_global_volume.sh && bash /tmp/sync_global_volume.sh
```

The script:
1. Verifies `/workspace` is itself a mount point and that the expected Gemma `config.json` exists there. It reports the filesystem/source but does not rely on brittle equality checks against the FUSE filesystem name.
2. Resolves the latest `main` commit SHA and downloads that exact full repository archive.
3. Validates the archive, records its SHA-256, and stores an immutable commit-named archive on the Global Volume (it refuses to overwrite a snapshot whose checksum differs).
4. Captures copies/checksums of deployed runtime source files if present.
5. Records the current model directory inventory and SHA-256 for the existing runtime/dependency backup artifacts. It does not recalculate checksums for every model weight because the model is already backed up separately and hashing tens of gigabytes is unnecessary for every source snapshot.
6. Writes a versioned manifest.

Expected locations:
- `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-<commit-sha>.tar.gz`
- `/workspace/ai-platform-backups/manifests/global-volume-manifest-<commit-sha>.txt`
- `/workspace/ai-platform-backups/manifests/source-commit-<commit-sha>.json`
- `/workspace/ai-platform-backups/deployed-runtime/`

The snapshot itself contains no uncommitted local files or secrets; it captures the commit in GitHub. Any change not yet committed to GitHub is not included. Commit source and update tests/docs before running the sync.

## Restore model and Python runtime

1. Attach the same Global Volume to a new Pod at `/workspace`.
2. Inspect the manifest in `/workspace/ai-platform-backups/manifests/`.
3. Verify the SHA-256 of the source archive before using it.
4. Fetch/extract the source archive to Pod-local disk (for example under `/tmp`) or download the same GitHub commit. Do not rely on a normal git working tree inside the FUSE mount.
5. Restore the vLLM Python environment from `/workspace/runtime-setup/vllm-clean-env.tar.zst` using the matching saved `install-vllm.sh`, frozen requirements and `runtime-manifest.txt`; check its existing `SHA256SUMS` first.
6. Recreate the isolated parser path under `/tmp/rag-deps` from the verified wheels in `/workspace/runtime-setup/rag-wheelhouse/` by running the PDF and XLSX setup scripts.
7. Re-run the GPU-free unit tests, then gateway smoke tests before using the service.

The exact restore steps must continue to be tested as the runtime evolves. A backup artifact existing is not the same thing as a completed recovery drill.

## Operating rule going forward

After each meaningful milestone (new endpoint, dependency, model/runtime change, parser, integration or evaluation change):
1. Commit code, exact pins, tests and notes to GitHub.
2. Run the relevant tests.
3. Run `ops/sync_global_volume.sh` to save a versioned source snapshot and runtime inventory to the Global Volume.
4. Verify the script reports the archive and manifest paths and successful checksums.
5. If deployed runtime changes, separately verify the deployed gateway files and runtime manifest match the expected source/config version.

Do not copy the temporary API key or other secrets into persistent snapshots. Until this sync script has been run successfully on the Pod, the new source files are versioned in GitHub, but the source snapshot has not yet been confirmed on the Global Volume.


## First successful snapshot — 2026-10-11

The user confirmed successful output from `ops/sync_global_volume.sh`. GitHub commit `404dad8e59363ff7882b0cbb05bae1640e1e3d1a` was archived and checksum-verified at `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-404dad8e59363ff7882b0cbb05bae1640e1e3d1a.tar.gz`; manifest at `/workspace/ai-platform-backups/manifests/global-volume-manifest-404dad8e59363ff7882b0cbb05bae1640e1e3d1a.txt`. See [the dated snapshot record](results/global-volume-snapshot-2026-10-11.md).

This is the first confirmed copy, not the latest source after this note. Re-run the sync script after the note is committed to create a newer snapshot that includes it.


## Snapshot after document-management tests — 2026-10-11

The user confirmed a newer successful snapshot at commit `bd44a9d3bca78837c039fca140b2d8543b0bab83`; its checksum passed. Archive: `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-bd44a9d3bca78837c039fca140b2d8543b0bab83.tar.gz`. Manifest: `/workspace/ai-platform-backups/manifests/global-volume-manifest-bd44a9d3bca78837c039fca140b2d8543b0bab83.txt`. Full record: [snapshot report](results/global-volume-document-management-snapshot-2026-10-11.md).

Next persistence verification is to deploy the latest gateway and save/read a small, non-sensitive canary document under `/workspace/rag-managed-docs/`. The source snapshot above predates this added snapshot report and any subsequent gateway deployment/test code; run the sync script again after the next verified milestone.


## Live document-storage canary

After the main gateway is upgraded, `ops/test_persistent_document_storage.sh` uses the authenticated API to upload and retrieve one fictional canary under `/workspace/rag-managed-docs/`. It verifies the file physically exists on the mounted Global Volume. The canary is deliberately retained as a later cross-Pod re-attach check; it contains no customer information. This proves a live write/read on the mounted path only, not yet survival across Pod replacement.
