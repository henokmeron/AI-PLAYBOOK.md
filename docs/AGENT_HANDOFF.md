# Agent handoff — read this first

**Every new agent / new chat must read this file before changing or starting anything.**  
**Before you finish a chat, update this file** with what you verified, what you changed, what failed, and what the next agent must not break. Do not delete older sections; add a dated entry at the top of “Session log”.

Last updated: **2026-10-14** (Qwen integration status closed: production default on A100; see `ops/results/qwen-integration-status-2026-10-14.md`).

---

## Standing rules (do not weaken)

1. **Qwen3.5-27B is the only auto-started model.** Gemma stays optional and must not load or take GPU memory unless the operator deliberately switches.
2. **Do not** create Azure resources, delete model weights / runtime archives / snapshots / user docs, or provision another paid Pod without explicit approval.
3. **Do not** stop or replace a working Pod without approval. Prefer isolated ports for risky tests (e.g. 8013/8083, 8014).
4. **Do not claim** a GPU, recovery path, or feature works unless it was actually load-tested and/or E2E-tested. Use labels: **VERIFIED** / **FAILED** / **NOT TESTED** / **BLOCKED**.
5. Keep large weights and the vLLM archive **on the Global Volume**, never in Git. Restored Python env goes under **`/tmp`**, never onto `/workspace`.
6. Secrets stay out of git, browser JS, and reports. Key file on Pod: `/tmp/platform-gateway.key` (ephemeral; never print it).
7. PowerShell + SSH strips embedded double quotes and CRLF breaks bash. Prefer scp’d scripts + LF conversion (`python3 /tmp/fresh/_lfconvert.py` if present).

---

## Current live platform (as of last update)

| Item | Value | Status |
| --- | --- | --- |
| Active test Pod | RunPod `3s3mh10hrkhocw` (“another pod test”), **A100-SXM4-80GB**, **$1.79/hr** | Running |
| SSH (TCP) | `root@154.54.102.36 -p 10469`, key `%USERPROFILE%\.ssh\id_ed25519` | Working when last checked |
| GPU / driver | 81,920 MiB, driver **580.126.16**, ~73.5 GiB used with Qwen loaded | VERIFIED |
| Container | 250 GB RAM, 30 GB overlay disk | OK |
| Global Volume | Same volume id `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace` (fuse.geesefs) | VERIFIED |
| Qwen | `127.0.0.1:8002` | HTTP 200 |
| Gateway | `127.0.0.1:8010` | HTTP 200 |
| Console | `127.0.0.1:8080` (tunnel example: `-L 18080:127.0.0.1:8080`) | HTTP 200 |
| Other Pod | “Qwen model testing system” **H100 NVL** showed **$0.00/hr** earlier; do not assume it is still needed or safe to delete | Leave alone unless user says otherwise |

### Exact volume paths that must remain

- Weights: `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654` (11 shards, ~51.75 GiB on disk; **BF16**, no quantization).
- Runtime archive: `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` (+ `SHA256SUMS`, `vllm-version.txt`).
- RAG wheels: `/workspace/runtime-setup/rag-wheelhouse/`.
- Launcher: `/workspace/ai-platform-release/START.sh` (canonical in git: `ops/release/START.sh`).
- Managed docs: `/workspace/rag-managed-docs`.
- Source snapshot for commit `083fa58`:  
  `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-runpod-first-083fa58.tar.gz`  
  SHA-256: `2fa0ecd0f7d3f2867b4641e1fa532800c63856f14f53ea4d515cb565ea005d22` (verified).  
  Older `0b49946` snapshot remains on the volume.

### Git

- Branch: **`feature/qwen3.5-27b-integration`** (also tip of `feature/qwen-a100-start-hardening`).
- Commit: **`083fa58`** / full `083fa5850c1c3b572fad8b63aa938192f58e8b45` (includes `ninja` PATH fix + integration status doc).
- Prior tip `0b49946` remains a valid historical snapshot on the volume.
- **`main` was not merged.** Do not merge without approval.
- Local working tree often has untracked `ops/_*.sh` / `ops/_*.py` probe helpers and `__pycache__` — **do not commit those by accident.**

---

## What is actually proven

### Model / runtime

- Model: Qwen3.5-27B, architecture `Qwen3_5ForConditionalGeneration`, text **dtype bfloat16**, `quantization_config` absent.
- Archived env: vLLM **`0.32.0rc1.dev62+g624a5ddaf`**, torch **`2.13.0+cu126`**. Needs host **driver ≥ 580** (CUDA 13–capable hosts). Driver 570 = **BLOCKED** (seen earlier on an A100 PCIe).
- Serve flags: `--trust-remote-code --language-model-only --reasoning-parser qwen3 --max-model-len 8192 --max-num-seqs 256`, thinking off. Memory util **0.90** on 80GB-class GPUs, **0.92** on larger (H100).
- Measured on this A100 SXM cold start: weights **50.13 GiB** on GPU; KV **19.63 GiB** (~197k tokens, ~24× concurrency at 8192). Load ~490 s after restore.
- Preflight refuses GPUs under **79,000 MiB** (`gpu-vram>=80GB`).

### Startup / recovery

- New `START.sh`: ownership repair, `safe.directory`, ff-only on clean checkouts, snapshot fallback if GitHub unreachable, flock, preflight (volume, weights, archive, driver, VRAM, free GPU, ports, `/tmp` ≥12 GiB for restore).
- Isolated H100 drill (ports 8013/8083): ownership, lock, restore, E2E, PDF/XLSX, offline snapshot fallback — **VERIFIED** (see `docs/results/a100-switch-readiness-2026-10-14.md`).
- **A100 SXM fresh Pod cold start with this launcher: VERIFIED** on 2026-10-14 (preflight + full start + E2E). Note: volume `VERSION.txt` may still say `fresh_pod_cold_start=NOT_TESTED` — that line is stale.

### RAG / Document Q&A

- Benchmark v1 + architecture audit committed in `0b49946` (`docs/results/rag-benchmark-2026-10-14.md`, `docs/rag/architecture-audit.md`, `eval/rag/`).
- Retrieval improved (recall@3 / MRR); E2E 40/40 on isolated gateway :8014 during that work.
- On the **current A100 stack**: text RAG E2E 9/9; PDF + XLSX upload/ask/delete **VERIFIED** (Safeguarding “three years”; Complex 0–4 rate 99.498 / £99.50).

### Agents / security / integrations

- `agents/`, `integrations/`, security review, fine-tuning plan: committed (`de40330`, smoke `473d119`).
- Live agent smoke vs Qwen: **calculator only VERIFIED**. Document/table/approval tools: local fake-model tests only.
- Nginx on some Pods listens on `0.0.0.0:8081` → console without login. User **deferred** fixing auth/nginx until a later “login” phase. Treat Pod docs as non-sensitive until then (`docs/security/baseline-review.md`).

---

## GPU compatibility (do not guess)

| GPU | Verdict |
| --- | --- |
| **A40 / RTX A6000 / L40S (48 GB)** | **Cannot** run this BF16 Qwen. Weights alone ~50 GiB on GPU. A40 Pod inspected: 46,068 MiB. Preferring $0.59 A40 is a dead end for *this* checkpoint. |
| **A100 80GB (PCIe or SXM)** | Viable. SXM cold start **VERIFIED**. Need driver ≥580 and same volume. |
| **H100 NVL** | Previously proven live stack; expensive. |

Do **not** “fix” the A40 by quantizing or re-downloading a smaller Qwen unless the user explicitly approves a new model track.

---

## Critical failure the next agent must know

**First start on a fresh Pod failed** with FlashInfer JIT:

`FileNotFoundError: ninja`

`ninja` exists at `/tmp/vllm-qwen-env/bin/ninja` after archive restore, but a clean RunPod image does not put it on `PATH`.

**Workaround that made this Pod succeed:** start with  
`PATH=/tmp/vllm-qwen-env/bin:$PATH`  
or the one-line change in `ops/start-first-release.sh`:

```bash
nohup env PATH="$QWEN_ENV/bin:${PATH:-}" VLLM_DO_NOT_TRACK=1 ...
```

- Fix is **committed and pushed** as of `083fa58` in `ops/start-first-release.sh`. Volume `VERSION.txt` points at that commit. Next `START.sh` that fast-forwards/clones this tip picks it up. Checkouts still on `0b49946` need the PATH workaround once.

After a failed start, nothing on `/workspace` is deleted; re-run after fixing PATH.

---

## How to start / check (do not invent new paths)

```bash
bash /workspace/ai-platform-release/START.sh --preflight
bash /workspace/ai-platform-release/START.sh --check
# Only if approved / empty GPU:
PATH=/tmp/vllm-qwen-env/bin:$PATH bash /workspace/ai-platform-release/START.sh --start
# or after PATH fix is in the script the checkout uses:
bash /workspace/ai-platform-release/START.sh
```

E2E helper (uses key file; does not print it):  
`/tmp/vllm-qwen-env/bin/python /tmp/AI-PLAYBOOK/ops/_pod_e2e_verify.py`

---

## Session log (newest first)

### 2026-10-14 — Qwen integration status closure

- Wrote `ops/results/qwen-integration-status-2026-10-14.md` (honest answer: Qwen **is** production default; plan file left untouched).
- Verified volume archive SHA256SUMS, snapshot `083fa58`, live `:8002`/`:8010`/`:8080`, registry `qwen3.5-27b`.
- Pushed `083fa58` (PATH/`ninja` fix + handoff + queue update). Volume `VERSION.txt` updated. Live services left running (HTTP 200).

### 2026-10-14 — A100 SXM verification

- Inspected A40 ($0.59): **incompatible** (VRAM).
- User switched to A100 SXM `3s3mh10hrkhocw`. Preflight **PASS**. First start **FAILED** (missing `ninja` on PATH). Second start with PATH **PASS**; Qwen ready ~490s; gateway + console up.
- E2E chat / models / Gemma-409 / text RAG: **PASS**. PDF + XLSX Q&A: **PASS**. Console tunnel + UI chat `UI_OK`: **PASS**.
- Did not stop the $0.00/hr H100 listing; did not delete volume assets; did not merge to main.

### Earlier (same project arc, same branch tip `0b49946`)

- Startup hardening, A100 readiness docs, RAG benchmark v1, agent foundation, security review, deferred nginx auth.
- Details: `docs/results/a100-switch-readiness-2026-10-14.md`, `docs/results/rag-benchmark-2026-10-14.md`, `docs/first-release-recovery.md`, `docs/security/baseline-review.md`.

---

## Before you finish your chat (checklist)

- [ ] Update **this file** (session log + any changed Pod IP/ports/status).
- [ ] Say what is VERIFIED / FAILED / NOT TESTED / BLOCKED.
- [ ] Confirm you did **not** delete weights, archives, or snapshots.
- [ ] If you fixed startup/recovery, say whether it is **committed and on the volume launcher**, or only local/`/tmp`.
- [ ] Leave secrets out of the write-up.
