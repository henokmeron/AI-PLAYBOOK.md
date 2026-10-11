# Live document persistence verification — 2026-10-11

## Result

**PASS.** The user-provided RunPod screenshot confirms the live document-management API wrote a test document to the mounted Global Volume and successfully listed and queried it.

## Evidence visible in the terminal output

- Mount verified: `/workspace`.
- Gateway health: `{"status":"ok","upstream":"ok","model_count":1}`.
- Upload returned metadata for collection `global-canary-1791758676` and file `global-volume-canary.md`, size 136 bytes.
- Physical file check passed at:
  `/workspace/rag-managed-docs/global-canary-1791758676/global-volume-canary.md`.
- Live collection listing returned the same file metadata.
- Live RAG query returned: `The persistent storage verification code is GLOBALVOL-58317 [Source 1].`
- Source metadata named `global-volume-canary.md`.
- Final line: `SUCCESS: document upload/list/retrieval verified at the mounted Global Volume path.`

## Retained canary

- Collection: `global-canary-1791758676`
- File: `/workspace/rag-managed-docs/global-canary-1791758676/global-volume-canary.md`
- This is fictional test content, intentionally retained for a future re-attach/persistence check.

## What this proves and what remains unproven

This proves upload, physical file creation, listing, and retrieval through the live gateway on the currently mounted Global Volume. It does **not** yet prove persistence after the current Pod is stopped or a different Pod attaches the same volume. That cross-Pod re-attach test is a separate recovery drill.

## Next operating rule

Commit meaningful source changes to GitHub, run relevant tests, then snapshot to the Global Volume with `ops/sync_global_volume.sh`. Do not upload real customer data until authentication/authorization, tenant isolation, retention/deletion, encryption, audit logging, and backup/restore are designed and tested.
