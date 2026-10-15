# Agent handoff — read this first

**Every new agent / new chat must read this file before changing or starting anything.**  
**Before you finish a chat, update this file** with what you verified, what you changed, what failed, and what the next agent must not break. Do not delete older sections; add a dated entry at the top of “Session log”.

Last updated: **2026-10-15** (callback page and sign-in status are in source; the Pod was checked from outside and was not changed).

## Only this repository

Do not create a new project, a new GitHub repo, or a new folder. All work stays here.

| | |
| --- | --- |
| Local folder | `C:\Users\henok\src\AI-PLAYBOOK.md` |
| GitHub | `https://github.com/henokmeron/AI-PLAYBOOK.md.git` (remote name `origin`) |
| Work branch | `feature/qwen-a100-start-hardening` (same commits as `feature/qwen3.5-27b-integration`) |
| `main` | Fast-forward it to the feature tip and push it. Never force-push. |
| Pod | RunPod only. Do not start a different app or a second paid Pod. |

`git` on the Windows PATH often fails (the `git.exe` that is found is a launcher without the real binary). Use this binary:

`C:\Users\henok\AppData\Local\GitHubDesktop\app-3.5.4\resources\app\git\mingw64\bin\git.exe`

Confirm with `git remote -v` before any commit. If the remote is not `henokmeron/AI-PLAYBOOK.md`, stop.

The local branch `feature/qwen3.5-27b-integration` used to sit at stale `467ca3e` while GitHub was at `01e7692`. It has been fast-forwarded to match GitHub. Stay on `feature/qwen-a100-start-hardening` unless you have just fetched and both tips match.

---

## Standing rules (do not weaken)

1. **Qwen3.5-27B is the only auto-started model.** Gemma stays optional and must not load or take GPU memory unless the operator deliberately switches.
2. **Do not** create Azure resources, delete model weights / runtime archives / snapshots / user docs, or provision another paid Pod without explicit approval.
3. **Do not** stop or replace a working Pod without approval. Prefer isolated ports for risky tests (e.g. 8013/8083, 8014).
4. **Do not claim** a GPU, recovery path, or feature works unless it was actually load-tested and/or E2E-tested. Use labels: **VERIFIED** / **FAILED** / **NOT TESTED** / **BLOCKED**.
5. Keep large weights and the vLLM archive **on the Global Volume**, never in Git. Restored Python env goes under **`/tmp`**, never onto `/workspace`.
6. Secrets stay out of git, browser JS, and reports. Key file on Pod: `/tmp/platform-gateway.key` (ephemeral; never print it).
7. PowerShell + SSH strips embedded double quotes and CRLF breaks bash. Prefer scp’d scripts + LF conversion (`python3 /tmp/fresh/_lfconvert.py` if present).
8. **Push feature-branch commits and `main`.** The owner requires this. Keep `feature/qwen-a100-start-hardening`, `feature/qwen3.5-27b-integration`, and `main` on the same commit by fast-forwarding `main`. Never force-push. Do not push untracked `ops/_*.sh`, `ops/_*.py`, or `__pycache__`.

---

## Current live platform (as of last update)

| Item | Value | Status |
| --- | --- | --- |
| Active test Pod | RunPod `00n856z3eue5v9` (“testing system”), **A100-SXM4-80GB**, **$1.79/hr** | Running. The older Pod `3s3mh10hrkhocw` is not in the Pod list. |
| SSH (TCP) | `root@154.54.102.31 -p 11165`, key `%USERPROFILE%\.ssh\id_ed25519` | VERIFIED 2026-10-15. Cheap health check only. |
| GPU / driver | 81,920 MiB, **71,347 MiB used** | VERIFIED 2026-10-15. Qwen was left running. |
| Container | 250 GB RAM, 30 GB overlay disk | OK |
| Global Volume | Same volume id `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace` (fuse.geesefs) | VERIFIED |
| Qwen | `127.0.0.1:8002` | HTTP 200 after ~1080s cold load on 2026-10-14 |
| Gateway | `127.0.0.1:8010` | HTTP 200, `default_model_id` `qwen3.5-27b` |
| Console | `127.0.0.1:8080` (tunnel: `-L 18080:127.0.0.1:8080`) | HTTP 200. The **running process** is still commit `98511df`. |
| Other Pod | “Qwen model testing system” **H100 NVL** showed **$0.00/hr** earlier; do not assume it is still needed or safe to delete | Leave alone unless user says otherwise |

### Exact volume paths that must remain

- Weights: `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654` (11 shards, ~51.75 GiB on disk; **BF16**, no quantization).
- Runtime archive: `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` (+ `SHA256SUMS`, `vllm-version.txt`).
- RAG wheels: `/workspace/runtime-setup/rag-wheelhouse/`.
- Launcher: `/workspace/ai-platform-release/START.sh` (canonical in git: `ops/release/START.sh`).
- Managed docs: `/workspace/rag-managed-docs`.
- Source snapshot for the published tip `01e76922`:  
  `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-runpod-first-01e7692.tar.gz`  
  SHA-256: `a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370` (re-checked against the file and its manifest on 2026-10-14).  
  Older snapshots `083fa58` and `0b49946` are still on the volume. The `083fa58` checksum was not re-hashed this session.

### Git

- **GitHub** feature branches include the Qwen routing work. `main` is fast-forwarded to the same tip and pushed. It is not force-pushed.
- `e1e360f` is the parent of **`c2323238041cea8317d2322e6d16554d0bc967bc`** (Qwen routing). That push is a fast-forward. The `ninja` PATH change itself is **`083fa58`**, already inside `e1e360f`.
- Local checkout is `feature/qwen-a100-start-hardening`. Keep `feature/qwen3.5-27b-integration` on the same commit.
- Live Pod source is `/tmp/AI-PLAYBOOK` at `98511df` on `feature/qwen3.5-27b-integration`, verified 2026-10-15. Qwen `:8002`, gateway `:8010`, and console `:8080` returned HTTP 200. Gemma on `:8000` was down. `MICROSOFT_CLIENT_ID` was unset. Weights were still present. The Pod was not restarted.
- Volume `VERSION.txt` and snapshot `…-01e7692.tar.gz` match SHA-256 `a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370` (checked 2026-10-14).
- Do not commit untracked `ops/_*.sh` / `ops/_*.py` probe helpers or `__pycache__`.

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
- Live agent smoke vs Qwen on Pod `00n856z3eue5v9`, deployed code `98511df`: **calculator VERIFIED** on 2026-10-14. `agents.live_smoke` and `POST /api/agent` both returned `696.486` from the calculator tool. Document Q&A on `POST /api/rag` answered the receipt question from the demo corpus and abstained on CEO salary. That live check was not repeated on 2026-10-15 because the new code is not deployed.
- In source, the Agent desk now has `search_documents`. It uses the existing retrieval pipeline, cites the file, abstains when coverage is too low, and flags instruction-like document text. That path is **unit-tested with a fake model**, not live against Qwen. Standalone Document Q&A, Chat, and System Status remain. File attachments on the Agent page are unsupported and are not indexed.
- Approval pause is unit-tested. No live external approval was clicked, and no email was sent.
- Microsoft 365 OAuth is implemented in source for read-only mail. **No Entra application was created. No application id is configured. No real account was authorised. No real Graph request or mailbox search succeeded.** The live console is still `98511df` and was not restarted. See `docs/integrations/microsoft-365-signin.md`.
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

- Fix is **committed and pushed** in `083fa58` (GitHub tip `01e76922`). It is one comment plus `PATH="$QWEN_ENV/bin:${PATH:-}"` on the existing `nohup env` line. Volume `START.sh` matches git `ops/release/START.sh` (SHA-256 `6059e4c2…`). A brand-new clone of `feature/qwen3.5-27b-integration` gets the fix. **This Pod's `/tmp/AI-PLAYBOOK` does not:** it is still `0b49946` with that PATH line uncommitted and without the comment. Leave it; the running Qwen process was not started from the published commit.

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

### 2026-10-15 — callback page, token revocation, console not replaced

- GitHub `HEAD`, `main`, and `cursor/microsoft-signin-options-2e6d` were `7ebad238e2d2f30de329e9b27043973638a9e989` at the start of this session. The working tree had only untracked `rag/__pycache__`, which was left untracked.
- The cloud agent is not the Pod. Qwen `:8002`, the gateway `:8010`, and the console `:8080` are not running here. TCP `154.54.102.31:11165` accepted a connection. There is no SSH private key in this environment, so the live processes, GPU, and `MICROSOFT_CLIENT_ID` were **not** re-checked on the Pod. The console was **not** restarted. No new Pod was started.
- The callback `http://127.0.0.1:18080/api/microsoft/callback` was showing Chrome's blank JSON viewer. The handler now returns an HTML page for success, cancellation, and failure. It does not send an empty redirect and does not put a fragment in a `Location` header. A redirect alone does not mark the account connected. The Agent page shows the account only when the server has confirmed it.
- A revoked refresh (`invalid_grant`) deletes the saved token. A network failure keeps it. Mail text that says to send mail does not grant `Mail.Send`. Tests are mocked. No real Graph mailbox search was run.
- No Entra application id was created or invented.

### 2026-10-15 — Microsoft sign-in choices, source only

- The Agent page now offers three sign-in links: any Microsoft account (`common`), a work or school account (`organizations`), and a personal account (`consumers`). The server maps those names. A query cannot point the login at another host or directory. A console locked to one tenant keeps that tenant. PKCE, the loopback redirect, and the read-only scopes are unchanged. There is still no client secret and no `Mail.Send`.
- No Entra application was created. This environment has no signed-in Microsoft session, so an application id was not invented and was not written into the repo or the Pod. `MICROSOFT_CLIENT_ID` is still unset. Mail remains mock-tested.
- The Pod was not restarted. Qwen, the gateway, and the console were left as they were. Last known rate is $1.79/hour. The live console is still the older checkout until a console-only replacement is done.

### 2026-10-15 — execution states, catalog evidence, source only

- Cheap SSH check, no restart and no model call: Pod `00n856z3eue5v9`, volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace` (fuse.geesefs), checkout `/tmp/AI-PLAYBOOK` `98511df` on `feature/qwen3.5-27b-integration`. Qwen `:8002/health` and gateway `:8010/health` returned HTTP 200. Console `:8080/` and `:8080/api/status` returned HTTP 200. Console `:8080/health` is not a route (HTTP 404). Gemma `:8000` was down. GPU 71,347 / 81,920 MiB. Qwen weights were present. `MICROSOFT_CLIENT_ID` was unset. Billing was not re-queried. Last known rate is $1.79/hour. The Pod was left running.
- The runner now records operator states as it moves: received, investigating, awaiting information, awaiting approval, executing, verifying, completed, failed, escalated, and cancelled. A task record stores the objective, plan steps, tool calls, results, approvals, errors, verification, and outcome. Retries, timeouts, and cancellation were already enforced; an interrupted tool call is recovered without calling that tool again. The model is not the approval boundary: a catalog write runs only after a one-time grant for that exact call. Mail tools stay hidden unless `mail:read` is granted. Mail search and read are **mock-tested**. Nothing in the catalog is marked live-tested. Send and the other writes stay unavailable and still make no Graph call.
- Document search stays on the same loop. Instruction-like document text and tool output are untrusted data. Secret-shaped values are redacted before they reach the operator view or the next model turn. File attachments on the Agent page are still unsupported.
- Entra still needs a signed-in user. No application was created and no client id exists. The registration steps are unchanged in `docs/integrations/microsoft-365-signin.md`.
- `docs/integrations/endpoint-diagnostics.md` is a research note only. No remote-control software was installed and no device connector runs.
- Tests: `agents.tests.test_execution`, `test_runtime`, `test_workspace`, `test_tools`, `integrations.tests.test_catalog`, `test_microsoft_oauth`, `test_framework`, and `web.test_server` — 141 tests, OK. All mocked. No live Graph call, no email, no model load, no calculator re-run.
- **Approval required before this code can run on the Pod.** Do not stop Qwen or the gateway. The exact request is in `docs/integrations/microsoft-365-signin.md`. Publishing to GitHub does not deploy it. The live checkout remains `98511df`.

### 2026-10-15 — agent document search and OAuth corrections, source only

- Cheap SSH check, no restart: Pod `00n856z3eue5v9`, volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace` (fuse.geesefs), checkout `/tmp/AI-PLAYBOOK` `98511df` on `feature/qwen3.5-27b-integration`. Qwen `:8002`, gateway `:8010`, and console `:8080` returned HTTP 200. Gemma `:8000` was down. GPU 71,347 / 81,920 MiB. Qwen weights were present. `MICROSOFT_CLIENT_ID` was unset. Billing was not re-queried; the last known rate is $1.79/hour and the Pod was left running.
- The Agent desk can call `search_documents` through the existing retrieval pipeline. A task can cite a file, abstain, and see instruction-like passages marked as data. Document Q&A `POST /api/rag` is unchanged. This is not live until the console process is replaced.
- Mail search and read stay behind the connector catalog. They appear only when the saved token includes delegated `Mail.Read`. Send, Teams, files, and calendar still make no Graph call. Tokens stay in `/tmp/microsoft-365-token.json` mode `0600`, not on `/workspace` and not in git. A group- or world-readable file is not loaded on Linux.
- Entra admin center asked for a sign-in. No app was created and no client id exists. The owner has to sign in and create one app named `Business AI local`, as written in `docs/integrations/microsoft-365-signin.md`.
- GitHub `main` and both feature branches contain this paragraph. The Pod is not running it; the live checkout is still `98511df`.
- Tests: `integrations.tests.test_microsoft_oauth`, `test_catalog`, `test_framework`, `agents.tests.test_workspace`, `test_tools`, `test_runtime`, and `web.test_server` — 132 tests, OK. All mocked. No live Graph call, no email, no model load, no calculator re-run.
- **Approval required before this code can run on the Pod.** Do not run `START.sh --start` while the console is already healthy: that launcher reuses the healthy Qwen, gateway, and console, so it will not load this commit. Do not stop Qwen. Weights stay on the volume. The exact request is in `docs/integrations/microsoft-365-signin.md`.

### 2026-10-14 — live calculator check and Microsoft sign-in source

- Confirmed Pod `00n856z3eue5v9`, volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace`, checkout `98511df`. Qwen `:8002`, gateway `:8010`, and console `:8080` returned HTTP 200. The Pod was not restarted and the new sign-in code was not deployed.
- Live calculator: final state, one calculator call, answer contains `696.486`. Live Agent page returned the same answer and the tool activity. Live Document Q&A answered the 10-business-day receipt question and abstained on CEO salary.
- Added the Entra PKCE sign-in and read-only Graph mail path. Send and the other writes still make no request. Automated tests use a fake transport. A real Microsoft account is not connected.
- Next owner step, when they want the live connection: register the Entra public client in `docs/integrations/microsoft-365-signin.md`, set `MICROSOFT_CLIENT_ID`, and approve a console restart. Do not stop the Pod without approval. Last known billing was $1.79/hour with a balance warning near $4.79.

### 2026-10-14 — owner started Pod `00n856z3eue5v9`

- The previous SSH address `154.54.102.36:10469` refused the connection. The running Pod is `00n856z3eue5v9` (“testing system”), SSH `root@154.54.102.31 -p 11165`.
- The same Global Volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373` is mounted at `/workspace`. Qwen weights and the runtime archive were already there. GPU was idle.
- Ran `/workspace/ai-platform-release/START.sh`. It cloned `98511df`. Preflight passed. Checksum of the Qwen runtime archive passed. Qwen became ready after about 1080 seconds. Gateway and console returned HTTP 200. Gemma was not started.
- RunPod showed a low-balance warning around $4.79 before this start. The Pod is billing at $1.79/hour while it stays on.

### 2026-10-14 — Teams plugin diagnosis and connector foundation

- Cursor's Teams plugin failed with `spawn git ENOENT`. `git` is not on the Windows PATH. The plugin is the MIT wrapper at `cursor/plugins` `third_party/teams` commit `837067b`, 5,796 bytes, and it calls `https://api.cursor.com/rest-mcp/teams/mcp`. That URL returned 401 without a Cursor credential. It is not reused in this platform. The files were placed in Cursor's expected cache directory. This session still has no Teams tools.
- Added `integrations/catalog.py`, `integrations/microsoft365.py`, and `agents/workspace.py`. The console has an Agent page. Microsoft 365 is listed as not connected. Local tests: integrations 30, agents 77, web console 19, all OK. No Graph call was made.
- The live Pod was not restarted and was not given this code.

### 2026-10-14 — completion audit and tonight's agent test

- Re-checked GitHub: `main` and both feature branches were `ebe1a8a` before this audit commit.
- `ops/test_qwen_launch_path.py` passed. Fresh-Pod run of that script remains **NOT TESTED**.
- Registry and agent unit tests passed after fixing a false failure: the search test treated the digits `999` inside a random call id as a leaked secret.
- Pod health at 20:52 UTC: `:8002`, `:8010`, `:8080` HTTP 200. Checkout still `0b49946`. `agents/live_smoke.py` is on that checkout. Did not restart anything and did not upload documents.
- Checklist: `docs/results/completion-audit-2026-10-14.md`.
- Tonight the owner can run the calculator smoke and Document Q&A. There is no live approval button.

### 2026-10-14 — publish the feature tip on main

- Owner asked for `main` to receive the work that was only on the feature branches, and for `main` to be pushed.
- `origin/main` (`33160fd`) is a direct ancestor of the feature tip, so `main` can fast-forward. No history rewrite.
- Probe scripts and `__pycache__` stay untracked.

### 2026-10-14 — push feature branches

- Owner rule: push feature-branch commits to GitHub. Do not force-push and do not push `main`.
- `git ls-remote` showed both feature branches at `e1e360f`. Local `c232323` has that commit as its only parent, so the push is a fast-forward.
- Did **not** restart the Pod or change `/workspace`.

### 2026-10-14 — Qwen routing, local only

- Chat with no model already resolved to `qwen3.5-27b` when the registry is loaded. Document Q&A did not: it used the first id from the upstream `/models` list. The console could also auto-select the first usable model if Qwen was not loaded.
- Document Q&A now resolves the registry default and sends that checkpoint id. If the upstream is serving something else, the gateway returns **HTTP 409** `model_not_loaded` and does not call the other model. An unknown explicit model is **HTTP 409** `unknown_model`.
- The console selects the configured default only. It no longer falls through to Gemma.
- Tests: `models.tests.test_registry_loader` + `ops.test_qwen_launch_path` 9 OK; `api/test_rag_conversation.py` 10 OK; `api/test_gateway_reliability.py` 17 OK; `web/test_server.py` 18 OK.
- Did **not** restart the Pod, push, or change the volume. The live gateway still runs the previous code until an approved restart.

### 2026-10-14 — connect the next agent to this repo only

- Confirmed this workspace remote is `https://github.com/henokmeron/AI-PLAYBOOK.md.git`. No other project was opened.
- Working Git binary is GitHub Desktop’s `mingw64\bin\git.exe` (see “Only this repository” above). PATH `git` is not reliable on this PC.
- Fast-forwarded the local branch `feature/qwen3.5-27b-integration` from stale `467ca3e` to `01e7692`, matching GitHub. No history was rewritten.
- Corrected the queue sentence that still said the `ninja` PATH fix might be unpushed. Added `ops/test_qwen_launch_path.py` (1 test, OK). Did not touch the Pod.

### 2026-10-14 20:07 UTC — read-only takeover check

- Did **not** restart services, start a Pod, download weights, or delete volume files.
- SSH to `3s3mh10hrkhocw` succeeded. `:8002/health`, `:8002/v1/models`, `:8010/health`, `:8080/` all HTTP 200. Gateway health: `default_model_id=qwen3.5-27b`. vLLM id is the Qwen weight path. GPU A100-SXM4-80GB, 73,507 / 81,920 MiB, driver 580.126.16. `/tmp/vllm-qwen-env/bin/ninja` is present.
- GitHub both feature branches = `01e76922`. Pod checkout = dirty `0b49946`. The stale local integration ref and the stale queue sentence were corrected in the later session entry above.
- Fresh-Pod run of the published script: **NOT TESTED** (do not start another Pod to test it).
- Nginx still listens on `0.0.0.0:8081`. Still deferred.

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
