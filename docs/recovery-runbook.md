# AI Platform Recovery Runbook

Status: **recovery inventory documented; full cold-start recovery not yet verified**  
Last updated: 2026-10-12

This runbook records observed facts from the working RunPod prototype. It deliberately distinguishes verified facts from steps that still need a controlled test. Do not treat the system as fully reproducible until the cold-start test at the end passes.

## Verified working path

The following was tested live on the RunPod Pod on 2026-10-12:

- Browser console reached through an SSH local tunnel.
- Chat request reached the authenticated local gateway and returned a real Gemma answer.
- Document Q&A retrieved the expense policy answer and displayed source metadata.
- Local service ports:
  - vLLM: `127.0.0.1:8000`
  - Gateway: `127.0.0.1:8010`
  - Web console: `127.0.0.1:8080`
- SSH tunnel from Windows succeeded using the Pod's direct TCP SSH endpoint and local key:
  `ssh -N -o ConnectTimeout=10 -o ExitOnForwardFailure=yes -i "$env:USERPROFILE\\.ssh\\id_ed25519" -p 48480 -L 18080:127.0.0.1:8080 root@216.81.245.29`
  Browse to `http://127.0.0.1:18080`. Keep that PowerShell window open while using the console. The IP/port mapping is specific to the current Pod and may change after replacement.

## Persistent assets confirmed

Mounted Global Volume: `/workspace`

- Model directory: `/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it`
- Runtime assets: `/workspace/runtime-setup/`
- Runtime archive: `/workspace/runtime-setup/vllm-clean-env.tar.zst` (about 6.3 GB)
- Frozen Python requirements: `/workspace/runtime-setup/requirements-frozen.txt`
- Runtime manifest: `/workspace/runtime-setup/runtime-manifest.txt`
- Installer: `/workspace/runtime-setup/install-vllm.sh`
- Backup files and manifests: `/workspace/ai-platform-backups/`
- Demo RAG documents:
  - `/workspace/rag-demo-docs/employee-handbook.md`
  - `/workspace/rag-demo-docs/expenses-policy.md`
- Managed RAG collection canary:
  `/workspace/rag-managed-docs/global-canary-1791758676/global-volume-canary.md`
- Git repository / web console source: repository `henokmeron/AI-PLAYBOOK.md`, branch `cursor/local-web-console`, web files under `web/`.

The SHA256 manifest at `/workspace/runtime-setup/SHA256SUMS` was checked on 2026-10-12; all four entries returned `OK`: `vllm-clean-env.tar.zst`, `requirements-frozen.txt`, `runtime-manifest.txt`, and `install-vllm.sh`.

## Runtime facts captured

Manifest recorded on 2026-10-11:

- Python 3.12.3
- uv 0.9.0
- NVIDIA H100 NVL; driver 580.126.09
- PyTorch 2.13.0+cu130; CUDA 13.0
- vLLM version pinned by the installer: 0.31.0

Observed vLLM command line:

```bash
/tmp/vllm-clean-env/bin/python /tmp/vllm-clean-env/bin/vllm serve \
  /workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it \
  --host 127.0.0.1 --port 8000 \
  --gpu-memory-utilization 0.90 --max-model-len 8192
```

Observed gateway configuration names:

- `PLATFORM_HOST=127.0.0.1`
- `PLATFORM_PORT=8010`
- `PLATFORM_API_KEY` (secret; never commit or print)
- `VLLM_UPSTREAM_URL=http://127.0.0.1:8000/v1`
- `RAG_DOCS_DIR=/workspace/rag-demo-docs`
- `RAG_MANAGED_DOCS_DIR=/workspace/rag-managed-docs`
- `RAG_MIN_SCORE=2.30` (calibrated only for the two-file demo corpus)
- `RAG_MANAGED_MIN_SCORE=0.0` (prototype default; not a quality guarantee)

The live gateway source and its dependencies were found under `/tmp/platform-gateway-runtime/`; timestamped source copies exist under `/workspace/ai-platform-backups/deployed-runtime/`. The temporary runtime path is not durable across Pod replacement.

## Important warnings

1. **Do not run `install-vllm.sh` as a startup script.** It runs `uv venv --clear /tmp/vllm-clean-env` and installs vLLM. It is an installer, not a safe service launcher; running it can destroy/recreate the temporary environment and incur lengthy work.
2. Files in `/tmp` are ephemeral. This includes the current vLLM environment, gateway runtime, gateway key file `/tmp/platform-gateway.key`, and the cloned console repository at `/tmp/AI-PLAYBOOK`.
3. The model and recovery assets are on `/workspace`; do not download or copy the model again unless verification shows the persistent copy is missing or corrupt.
4. Do not publish gateway port 8010 or expose the web console on a public interface. Both services should remain bound to loopback; access the console through SSH forwarding.
5. Do not print, paste, commit, or include the gateway key in logs or this runbook.
6. The current gateway and web console are a development prototype, not production-hardened.

## RAG implementation and current limitation

The backed-up RAG engine splits documents into chunks of up to 1,200 characters with 160 characters of overlap and ranks them using BM25-style keyword scoring. It is not currently a semantic/vector retriever. The working smoke test retrieved the expense-policy answer and returned source metadata, but one successful query does not demonstrate high accuracy across large document collections.

The demo threshold `2.30` is explicitly calibrated only for the two-file demo corpus. The managed collection threshold defaults to `0.0`; this must not be treated as calibrated. Keep current behavior intact until a versioned evaluation set exists.

## What is not yet verified

- A complete startup script that restores the runtime archive, gateway source/dependencies, API key, and console after Pod replacement.
- Whether the managed RAG collection is backed up completely beyond the observed canary file and whether collection state survives all restart scenarios.
- A cold-start recovery test from the persistent volume without relying on `/tmp`.
- RAG accuracy across paraphrases, multi-document questions, unsupported questions, conflicting versions, long files, and citation correctness.

## Required next engineering task

Create one idempotent startup/recovery entry point that:

1. Verifies the persistent model and runtime archive checksums before starting anything.
2. Restores the vLLM environment from the existing archive to `/tmp` only if missing or invalid; does not reinstall when a valid environment exists.
3. Restores the gateway source and its dependencies from a chosen, manifest-verified backup into a deterministic temporary runtime directory.
4. obtains/creates the gateway key securely without echoing it or putting it in Git; ensures the gateway and console receive it only server-side.
5. Starts vLLM, waits for `http://127.0.0.1:8000/v1/models` to respond, starts the gateway, waits for `http://127.0.0.1:8010/health` to report healthy, then starts the console on `127.0.0.1:8080`.
6. Is safe to run twice, checks for already-running healthy services, and fails with actionable errors rather than silently launching duplicates.
7. Writes non-secret logs and status to a persistent diagnostics folder under `/workspace`.

After creating it, test on the current Pod without interrupting the working services first (dry-run / validation mode), then schedule a controlled stop/start test. Do not claim cold-start recovery works until the test passes.

## RAG quality gate

Before calling RAG business-grade, create a version-controlled benchmark with known-answer cases and source spans. Include exact wording, paraphrases, synonyms, multi-document synthesis, irrelevant/no-answer queries, conflicting/dated policies, long documents, and prompt-injection content in retrieved files. Measure retrieval recall at k, answer correctness, citation precision, unsupported-claim rate, and appropriate abstention. Establish a baseline for BM25 before changing it; compare a hybrid BM25 + semantic retrieval and reranking candidate against the same tests. Keep thresholds corpus-specific and require citations to retrieved source chunks.

## Document Q&A conversation (2026-10-12)

Conversational Document Q&A, bounded history validation, untrusted history framing, and spreadsheet calculation prompting are documented in [document-qa-conversation.md](document-qa-conversation.md). Create dated Global Volume snapshots with:

```bash
bash /tmp/AI-PLAYBOOK-upload-test/ops/snapshot-document-qa-test.sh
```

Snapshots land under `/workspace/runtime-setup/web-console-backups/document-qa-conversation-<UTC-stamp>/` and must never include API keys, `.env` files, model weights, or caches. Prefer a separate test console on `127.0.0.1:8082` (optional companion gateway on `8012`) before touching the main console on `8080` / gateway on `8010`.
