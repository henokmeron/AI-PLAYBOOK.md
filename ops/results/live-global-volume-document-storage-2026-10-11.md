# Live Global Volume document storage test — 2026-10-11

## Result

**PASS.** User-provided RunPod terminal screenshot confirms the script `ops/test_persistent_document_storage.sh` completed successfully.

Confirmed from output:
- Mounted Global Volume verified at `/workspace`.
- Gateway health returned `{"status":"ok","upstream":"ok","model_count":1}`.
- Canary upload returned `stored` for collection `global-canary-1791758676`, file `global-volume-canary.md`, 136 bytes.
- Script verified the file physically exists under:
  `/workspace/rag-managed-docs/global-canary-1791758676/global-volume-canary.md`
- Live API list returned the canary document's metadata.
- Live RAG query answered from the canary source: `The persistent storage verification code is GLOBALVOL-58317 [Source 1].`
- Final status: `SUCCESS: document upload/list/retrieval verified at the mounted Global Volume path.`

The small fictional canary was intentionally retained for a future Pod re-attach persistence test.

## What this proves and what remains

This proves the live gateway can upload, list and retrieve a document from the mounted Global Volume path. It does not yet prove the document survives detaching the volume and attaching it to another Pod; that separate recovery drill remains pending.

Do not upload real customer documents until authentication, per-customer isolation, encryption, retention/deletion, backup, and audit requirements have been designed and tested.
