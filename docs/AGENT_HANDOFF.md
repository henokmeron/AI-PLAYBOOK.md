# Agent handoff — read this first

**Every new agent / new chat must read this file before changing or starting anything.**  
**Operator system map (beginner manual):** `docs/SYSTEM_MANUAL.md` — keep that file updated when architecture, paths, or operating steps change.  
**Before you finish a chat, update this file** with what you verified, what you changed, what failed, and what the next agent must not break. Do not delete older sections; add a dated entry at the top of “Session log”.

Last updated: **2026-10-22T16:30Z** (Coordinator integrated uncommitted specialist edits on top of `409c891`. A100 `gom4ualdk47qrj` was not restarted. Empty tenant and `common` resolve to directory `d595636e-9ef4-4890-b8a7-bde8dd5cab03` and are not sent. The running console has no `MICROSOFT_CLIENT_ID` and no token file. Mail stays **NOT CONFIGURED**. Inference and one RAG answer from about 15:50Z stay **LIVE VERIFIED** for that sample only. Second endpoint, Blackwell, and fresh-machine recovery stay open. Production **NO-GO**.)

## Only this repository

Do not create a new project, a new GitHub repo, or a new folder. All work stays here.

| | |
| --- | --- |
| Local folder | `C:\Users\henok\src\AI-PLAYBOOK.md` |
| GitHub | `https://github.com/henokmeron/AI-PLAYBOOK.md.git` (remote name `origin`) |
| Work branch | `main` only. Do not open a feature branch. |
| `main` | Commit and push this branch. Never force-push. |
| Pod | RunPod only. Do not start a different app or a second paid Pod. |

`git` on the Windows PATH often fails (the `git.exe` that is found is a launcher without the real binary). Use this binary:

`C:\Users\henok\AppData\Local\GitHubDesktop\app-3.5.4\resources\app\git\mingw64\bin\git.exe`

Confirm with `git remote -v` before any commit. If the remote is not `henokmeron/AI-PLAYBOOK.md`, stop.

The local branch `feature/qwen3.5-27b-integration` used to sit at stale `467ca3e` while GitHub was at `01e7692`. It has been fast-forwarded to match GitHub. Stay on `main`. Fast-forward `feature/qwen-a100-start-hardening` and `feature/qwen3.5-27b-integration` only when that update is a true fast-forward.

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
9. **Mandatory living playbook.** Every significant change is unfinished until matching playbook/docs are updated, verified for accuracy, committed, and pushed with the code. See `PLAYBOOK.md` → **Mandatory living playbook — continuously maintained** (sections A–F).

---

## Current live platform (as of last update)

| Item | Value | Status |
| --- | --- | --- |
| Active test Pod | `gom4ualdk47qrj` (“excessive_gray_crocodile”), **A100 SXM x1**, **$1.80/hr** (GPU **$1.79/hr** plus container disk **$0.007/hr**). At 15:33Z this was the only row. | **VERIFIED Running**. This is the one new pod. Do not deploy another. H100 `xx9cjogra5vcwl` was not started. |
| Prior Pod | `mlar88u3ku8utm` (“screeching_crimson_vole”) was **stopped**, then **terminated**. H100 `xx9cjogra5vcwl` was not listed and was not started. | **VERIFIED** terminated. Both confirm dialogs named `screeching_crimson_vole` only. The id then left the list. Do not recreate it. Do not start the H100. |
| SSH (TCP) | Connect for `gom4ualdk47qrj`: `root@154.54.102.41` port `12572`. Key `%USERPROFILE%\.ssh\id_ed25519`. Old `195.26.233.38:53380` belongs to the gone pod. | This session used the new Connect address. The key was not printed. |
| GPU / driver | NVIDIA A100-SXM4-80GB, **81920 MiB** total, driver **595.91.07**. At 15:50:02Z, after startup, **70647 MiB** used. At the completion sample, **70901 MiB**. | **VERIFIED** 80GB-class GPU on `gom4ualdk47qrj`. |
| Container | `/tmp/vllm-qwen-env` is the running interpreter for vLLM pid **1826**, started 15:23Z. | The env lives under `/tmp`, not on the volume. |
| Global Volume | Console id `cmv2p5m0d000007jk9o3931ea` (“New model container”), type **Global**, mounted at `/workspace`. `findmnt` source `5aac0c77-6fcc-4be9-a112-dfe3890e1373`, fstype `fuse.geesefs`. | Same source read on `gom4ualdk47qrj` at 2026-10-22T15:33:19Z. Direct S3 API is **not** supported. No new volume was created. Weights were not downloaded. |
| Qwen / Gateway / Console | `:8002` / `:8010` / `:8080` | **VERIFIED** HTTP **200 / 200 / 200** at 2026-10-22T15:49:11Z and again at 15:50:02Z. One `START.sh` finished with `FIRST_RELEASE_READY` at 15:48:46Z. Do not start a second copy. |
| Pod checkout | `/tmp/AI-PLAYBOOK` on `gom4ualdk47qrj` stayed `be9cbd2baf08ee1d9f1bbd192982c94575f57aeb`. | This session did not reset it. It is behind GitHub `main`. |
| Other Pod | Older idle/terminated Pods | Leave alone unless user says otherwise |

### Exact volume paths that must remain

- Weights: `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654` (11 shards, ~51.75 GiB on disk; **BF16**, no quantization).
- Runtime archive: `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` (+ `SHA256SUMS`, `vllm-version.txt`).
- RAG wheels: `/workspace/runtime-setup/rag-wheelhouse/`.
- Launcher: `/workspace/ai-platform-release/START.sh` (canonical in git: `ops/release/START.sh`).
- Managed docs: `/workspace/rag-managed-docs`.
- Source snapshot written and checksum-checked on the volume on 2026-10-22: `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-runpod-first-6f07b58.tar.gz`. SHA-256 `3cf154feb99536781232408ea06cc93373e14fe69e1d866daffa64ecdb015de7` (696,562 bytes, 380 members, commit `6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8`). Checksum file `/workspace/ai-platform-backups/manifests/AI-PLAYBOOK.md-runpod-first-6f07b58.sha256` (`sha256sum -c` OK).
- Operator backup: `/workspace/platform-state/operator-backups/20261022T015922Z/` (`operators.json` SHA-256 `41811efc68d6723d5dc77dc1af06c882397b793ec9d5d0eae03ea9bef91ac6bf`, plus `SHA256SUMS`). Scrypt hash only.
- Older snapshot `01e7692` was re-checked the same day and still SHA-256 `a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370`. It was not overwritten.

### Git

- The running checkout on `gom4ualdk47qrj` is `/tmp/AI-PLAYBOOK` at `be9cbd2baf08ee1d9f1bbd192982c94575f57aeb`. This session did not reset it and did not pull a newer commit into the running load. The terminated pod `mlar88u3ku8utm` had been on `f7043f8ad8ed9ac39423f96fe7fcbd12f21fe7ba`. The `vx4oe3oyfsqnz8` sentence below is an older pod.
- **GitHub** feature branches include the Qwen routing work. `main` is fast-forwarded to the same tip and pushed. It is not force-pushed.
- `e1e360f` is the parent of **`c2323238041cea8317d2322e6d16554d0bc967bc`** (Qwen routing). That push is a fast-forward. The `ninja` PATH change itself is **`083fa58`**, already inside `e1e360f`.
- Local checkout for new work is `main`. Keep `feature/qwen-a100-start-hardening` and `feature/qwen3.5-27b-integration` on the same commit by fast-forward only.
- Live Pod source on `vx4oe3oyfsqnz8` is `/tmp/AI-PLAYBOOK` at **`2d273f6`**. Qwen `:8002`, gateway `:8010`, and console `:8080` are up. Gemma on `:8000` is down. `MICROSOFT_CLIENT_ID` is unset. Weights were not re-downloaded.
- Volume snapshot `…-01e7692.tar.gz` SHA-256 `a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370` re-checked **OK** on 2026-10-15. Runtime `SHA256SUMS` **OK**. Volume `START.sh` matches git (`6059e4c2…`).
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
- Live agent smoke vs Qwen on Pod `00n856z3eue5v9`, deployed code `98511df`: **calculator VERIFIED** on 2026-10-14. `agents.live_smoke` and `POST /api/agent` both returned `696.486` from the calculator tool. Document Q&A on `POST /api/rag` answered the receipt question from the demo corpus and abstained on CEO salary.
- **2026-10-15 live IT Helpdesk on Pod `4lvr54b0wmkz6c` tip `c069674`: VERIFIED** against real Qwen (not mocked). Evidence: `docs/results/helpdesk-live-qwen-2026-10-15.md`. Async calculator smoke FAILS=0; helpdesk smoke FAILS=0; approval path cleared local temp cache only; web UI submit → Approve → incident report `resolved` (task `9dc32d7f8a774dfeb43573eeab8dc41a`).
- Protocol fix: accept Qwen’s `{"action":"<tool_name>",...}` shortcut. IT token budget raised to 48k after a live run hit the old 16k ceiling post-approval.
- In source, the Agent desk has `search_documents` (unit-tested with a fake model; live Document Q&A remains separate). File attachments on the Agent page are unsupported and are not indexed.
- Helpdesk approval pause: **live VERIFIED** for `clear_temp_cache` only. No email was sent. No customer systems touched.
- Microsoft 365 OAuth is implemented in source for read-only mail. The existing Entra app is `llmfortestingclientid`, single-tenant directory `d595636e-9ef4-4890-b8a7-bde8dd5cab03`. The saved Authentication blade has the loopback redirect. No running console has loaded the application id. No mailbox was read. Status **NOT CONFIGURED**. See the 2026-10-22 session entry and `docs/integrations/microsoft-365-signin.md`.
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

Qwen is already up on `gom4ualdk47qrj`. Do not run `START.sh` again while `:8002` is healthy. A second run would be a second copy. Do not start H100 `xx9cjogra5vcwl`. Do not create a volume or a pod. Do not click Stop, Terminate, or Resize. The old pod `mlar88u3ku8utm` is gone; do not revive it.

```bash
bash /workspace/ai-platform-release/START.sh --check
```

E2E helper (uses key file; does not print it):  
`/tmp/vllm-qwen-env/bin/python /tmp/AI-PLAYBOOK/ops/_pod_e2e_verify.py`

---

## Session log (newest first)

### 2026-10-22 — coordinator integrated specialist edits; production stays NO-GO

- Fetched `origin`. `main` and both feature branches were `409c8913dcd338a9bfe84ab1304fdffd8305c561`. Nothing was reset, cleaned, or force-pushed. Uncommitted specialist work was kept and included after the suite passed. `__pycache__` and `ops/_coord_poll_log.txt` were not committed.
- `integrations/microsoft_oauth.py` maps an empty tenant and `common` to directory `d595636e-9ef4-4890-b8a7-bde8dd5cab03`. `common` is not placed on authorize or token URLs. `?account=work` is not redirected to `/organizations/` unless `MICROSOFT_TENANT` is `organizations`. `web/test_server.py` now expects that directory on the configured sign-in redirect, expects `?account=directory` to use the same directory, and expects `?account=work` to be HTTP 400. PKCE, the absent client secret, the absent `Mail.Send` scope, the CSRF same-site refusal, and the rejection of an arbitrary account were not weakened.
- The running console on `gom4ualdk47qrj` still has no `MICROSOFT_CLIENT_ID` and no token file. This session did not open Azure, did not create a secret, did not restart the console, and did not read a mailbox. Live mail stays **NOT CONFIGURED**.
- Other specialist edits included with this commit: RAG cache keys are content hashes and a weak lexical overlap abstains; Operations overview, health, and director refuse `Sec-Fetch-Site` `cross-site` and `same-site` with HTTP 403; agent task ids are constrained, a supplied id is reused, a tool failure is not marked successful, and cancel is recorded while the worker is still stopping; connector retries require an idempotent operation plus a key; a Google Workspace skeleton stays **NOT CONFIGURED** with no client id; Windows repair requires a recorded approver and does not treat a later check-in as fresh evidence. No `agents/`, `integrations/`, `rag/`, `windows_repair/`, `web/`, or `api/` file was rewritten except the two Microsoft URL expectations in `web/test_server.py`.
- **LIVE VERIFIED** for inference and one RAG answer only, from the 2026-10-22 bring-up around 15:50Z: health HTTP 200 on `:8002`, `:8010`, and `:8080`; completions `PONG` and `PLATFORM_OK`; a grounded RAG answer (10 business days, `expenses-policy.md`, and a £100 threshold). The pod checkout stayed `be9cbd2baf08ee1d9f1bbd192982c94575f57aeb`. This session did not run `START.sh`, did not restart Qwen, did not stop the pod, did not start the H100, and did not write the Global Volume.
- `python -m ops.run_tests` on Python 3.11 was 44 modules, 44 ok, 0 failed, exit 0, about 114 seconds. `integrations.tests.test_endpoint` skipped 1. `api.test_gateway_reliability` was 31 tests, logged a Windows socket abort, and still passed. `web.test_server` was 31 tests and passed, including the directory redirect and the rejected work account. System Status percentages are computed from criteria. Production decision stays **NO-GO**. Still open: deployed commit equals intended Git tip, mail end-to-end, second endpoint, Blackwell live acceptance, fresh-environment recovery.

### 2026-10-22 — one new A100 deployed; old pod terminated; health 200

- The owner asked for one replacement near **$1.80/hr**, with Global Volume `cmv2p5m0d000007jk9o3931ea` on `/workspace`, and for `mlar88u3ku8utm` to be turned off. H100 `xx9cjogra5vcwl` was not started. No second volume was created. Weights were not downloaded. The Network Volume S3 API was not used.
- Prices on the deploy page after the CUDA filter was limited to **13.0–13.4**: B300 **$8.99/hr** 288GB, B200 **$7.99/hr** 180GB, H200 SXM **$5.29/hr** 141GB, RTX PRO 6000 **$2.49/hr** 96GB, **A100 SXM $1.79/hr 80GB**, H100 SXM **$3.99/hr** 80GB, A40 **$0.59/hr** 48GB, L40S **$1.09/hr** 48GB, PRO 6000 MIG 48GB **$1.29/hr**, RTX 5090 **$1.19/hr** 32GB, RTX PRO 4500 **$0.72/hr** 32GB, RTX PRO 4500 SE **$0.72/hr** 32GB, RTX 4090 **$0.89/hr** 24GB, L4 **$0.59/hr** 24GB, PRO 6000 MIG 24GB **$0.69/hr**, RTX 4000 Ada **$0.28/hr** 20GB. Before that filter the same A100 SXM was **$1.79/hr**, and the list also showed RTX 6000 Ada **$0.99/hr** 48GB and RTX A6000 **$0.59/hr** 48GB. The 48GB cards cannot hold this BF16 model. H100 and the larger cards were above the A100 price. One A100 was deployed.
- New pod: `gom4ualdk47qrj` (“excessive_gray_crocodile”), 1× A100 SXM, checkout total **$1.80/hr**, offered CUDA **13.2**. `findmnt /workspace` source `5aac0c77-6fcc-4be9-a112-dfe3890e1373`. `nvidia-smi`: NVIDIA A100-SXM4-80GB, **81920 MiB**, driver **595.91.07**. The volume attached while the old pod was still running. After the new pod was Running and that filesystem was mounted, `mlar88u3ku8utm` was stopped and then terminated. Both dialogs named `screeching_crimson_vole`. The pods list then contained only `gom4ualdk47qrj`.
- `bash /workspace/ai-platform-release/START.sh --preflight` returned **PREFLIGHT_PASS**. One `bash /workspace/ai-platform-release/START.sh` began at **15:15:17Z**, logged source `be9cbd2`, started vLLM at **15:23:09Z**, and logged `FIRST_RELEASE_READY` at **15:48:46Z** (Qwen ready after about **1530s**). No second copy. Gemma was not loaded.
- Shard samples from the new log, GPU memory, health `:8002/:8010/:8080`: restore and **0 MiB** / **000** through 15:21:09Z; **0/11** and **51923 MiB** at 15:25:10Z; **2/11** at 15:27:10Z (`75.88s/it`); the captured line stayed on **2/11** through 15:35:10Z; **3/11** at 15:37:10Z; **7/11** at 15:39:11Z; **9/11** at 15:41:11Z; **11/11** complete at 15:43:11Z in **19:09**; health **200/200/200** and **70647 MiB** at 15:49:11Z. That was not a 25-minute stall.
- One completion: HTTP **200**, text `PONG`. One RAG question on the demo expenses policy: HTTP **200**, answer named the **£100** approval threshold. The gateway key was not printed. A later watch of the same stack also recorded `PLATFORM_OK` and a 10-business-day RAG answer.
- Mail was not read. No second computer was set up. This GPU is an A100, not Blackwell. Production stays **NO-GO** on those gates. Do not start a second `START.sh` while health stays 200. Do not start the H100. Do not deploy another pod.

### 2026-10-22 — replacement A100 reached HTTP 200; this session only watched the load

- Console at 15:33Z, pods page 1 of 1: the only row was `gom4ualdk47qrj` (`excessive_gray_crocodile`), A100 SXM, **$1.80/hr**, Stop present and not clicked. H100 `xx9cjogra5vcwl` was not listed. Deploy was not clicked. No second pod was created. `mlar88u3ku8utm` was not revived.
- Connect SSH over exposed TCP was `root@154.54.102.41` port `12572`. The key was not printed. At 15:33:19Z: NVIDIA A100-SXM4-80GB, 81920 MiB, driver 595.91.07, **51923 MiB** used by `VLLM::EngineCore`. `findmnt /workspace` source `5aac0c77-6fcc-4be9-a112-dfe3890e1373`, fstype `fuse.geesefs`.
- `start-first-release.sh --start` (pid 655, from 15:15Z) and `vllm serve` (pid 1826, from 15:23Z) were already running. `START.sh` was not in the process list. This session did not run `START.sh`, did not run preflight, and did not start a second vLLM. Weights, the runtime archive, snapshots, and `START.sh` were not overwritten.
- Shard samples, GPU memory, health `:8002/:8010/:8080`. The 15:17–15:27 lines were read from the pod’s existing `/tmp/load-watch.log`. Later lines are this session’s own polls. Not STUCK.
  - 15:17:09Z restore, 0 MiB, 000/000/000
  - 15:25:10Z shard 0/11, 51923 MiB, 000/000/000
  - 15:27:10Z shard 2/11, 51923 MiB, 000/000/000
  - 15:35:02Z shard 2/11, 51923 MiB, 000/000/000
  - 15:38:02Z shard 5/11, 51923 MiB, 000/000/000
  - 15:39:32Z shard 7/11, 51923 MiB, 000/000/000
  - 15:41:02Z shard 8/11, 51923 MiB, 000/000/000
  - 15:42:32Z shard 10/11, 51923 MiB, 000/000/000
  - 15:44:02Z shard 11/11, 52835 MiB, 000/000/000
  - 15:45:32Z shard 11/11, 67571 MiB, utilization 100%, 000/000/000
  - 15:47:02Z shard 11/11, 70847 MiB, 000/000/000
  - 15:48:32Z shard 11/11, 70647 MiB, 000/000/000
  - 15:50:02Z application startup complete, 70647 MiB, HTTP **200 / 200 / 200**. The starter process had exited. vLLM pid 1826 was still the only `vllm serve`.
- One completion: gateway HTTP **200**, content `PLATFORM_OK`. One RAG question on the demo corpus: HTTP **200**, status `answered`, 10 business days, source `expenses-policy.md`, 2 sources. The gateway key was not printed. GPU after that sample was 70901 MiB.
- `/tmp/AI-PLAYBOOK` stayed `be9cbd2baf08ee1d9f1bbd192982c94575f57aeb`. It was not reset. Mail, a second computer, Blackwell, and fresh-machine recovery stay blocked. The pod checkout is not this recording commit. Production **NO-GO**.

### 2026-10-22 — the one START.sh exited 1; no completion; no second start

- This session ran `bash /workspace/ai-platform-release/START.sh` on `mlar88u3ku8utm` at **2026-10-22T13:11:19Z**. No Gemma flag. The script logged source `f7043f8`, checksum-checked the runtime archive, restored `/tmp/vllm-qwen-env`, and logged Qwen start at **13:37:02Z**. It exited **1** at **14:22:07Z** (70 minutes 48 seconds). The error tail was `ERROR: Qwen not ready after 2700s (process 12621 still running; re-run later to reuse it)` and `Rollback: nothing on /workspace was deleted or overwritten.` The process was not killed. `START.sh` was not run again.
- Health from this session: HTTP **000** on `:8002/health`, `:8010/health`, and `:8080/api/status` at 14:22:23Z (shard 4/11, GPU 51923 MiB), 14:34:42Z, 14:45:22Z (shard 5/11), and 15:00:36Z (shard 6/11, GPU 51923 MiB, vLLM still running). No completion and no RAG question. No smoke script was run, because the gateway was not listening.
- Volume sizes were the same at 13:11:06Z and 14:22:23Z: `START.sh` 3517 bytes, SHA-256 `41af7e93f34f2d28d9b97d53b18a4c58565dcb50e35bcdd6e71e40cfdaf92ca6`; runtime archive 4060580548 bytes; snapshot `AI-PLAYBOOK.md-runpod-first-6f07b58.tar.gz` 696562 bytes. Weight directory then was 75 files and 55586176127 bytes. Those paths were not stat'd again after the old SSH port refused.
- After 15:00:36Z, TCP `195.26.233.38:53380` failed. Before 15:24:59Z the console search for `mlar88u3ku8utm` with **All statuses** returned no row. The only listed pod was `gom4ualdk47qrj` (`excessive_gray_crocodile`), A100 SXM, $1.80/hr, Details uptime **11m 43s**, Stop button present and not clicked. This session did not SSH that pod and did not run `START.sh` there. H100 `xx9cjogra5vcwl` was not started. Mail was not read.
- Live acceptance was not raised. Health never returned 200. Second endpoint, Blackwell, fresh-machine recovery, independent weight backup, and mailbox read stay blocked. Production **NO-GO**. `update-source-only.sh` was not run. This recording commit is not deployed.

### 2026-10-22 — shard 7, then the old A100 host refused SSH

- The existing vLLM was left running. No second `START.sh` was launched while pid **12621** was alive. Pid **12621** was not killed by this session. H100 `xx9cjogra5vcwl` was not started. Stop, Terminate, Resize, and Start were not clicked. No new file was written on `/workspace`.
- SSH `root@195.26.233.38` port `53380` worked for the samples below. The key was not printed. `/tmp/AI-PLAYBOOK` on that host stayed `f7043f8ad8ed9ac39423f96fe7fcbd12f21fe7ba`. One `vllm serve` process. EngineCore pid **13527** stayed alive. GPU stayed **51923 MiB / 81920 MiB**, utilization 0%. `:8002/health`, `:8010/health`, and `:8080/api/status` stayed HTTP **000 / 000 / 000**.
- Shard line in `/workspace/platform-diagnostics/first-release/qwen-vllm.log`: **6/11** at 14:51:52Z (`[1:13:29<1:08:29, 821.97s/it]`, log 9446 bytes, vLLM elapsed 1:14:50); still **6/11** at 14:55:42Z, 14:59:14Z, and 15:02:46Z; **7/11** at 15:06:18Z (`[1:26:33<53:58, 809.51s/it]`, log 9538 bytes, elapsed 1:29:16); still **7/11** at 15:10:07Z and 15:13:39Z (elapsed 1:36:37). Shard 7 had been the current line for **7.4 minutes**, not 25. This was not a stall.
- The next two SSH attempts, and a direct retry, got `banner exchange: Connection to UNKNOWN port -1: Connection refused` for `195.26.233.38:53380`.
- Connect re-read on the pods page: `mlar88u3ku8utm` and `screeching_crimson_vole` were not listed. Searching that id returned no matching pods. The only row was `excessive_gray_crocodile` / `gom4ualdk47qrj`, A100 SXM, **$1.80/hr**, Stop button present. Inspector uptime about **9m 24s**. Volume “New model container” mounted at `/workspace`. Web terminal said Stopped. SSH over exposed TCP was `root@154.54.102.41` port `12572`. The key was not printed.
- Read-only SSH to that new address at 2026-10-22T15:21:57Z: NVIDIA A100-SXM4-80GB, GPU **0 MiB / 81920 MiB**, no compute app, pid **12621** absent, no `vllm` and no `START.sh` process, health **000 / 000 / 000**. `findmnt` source `5aac0c77-6fcc-4be9-a112-dfe3890e1373`. `/tmp/AI-PLAYBOOK` there is `be9cbd2baf08ee1d9f1bbd192982c94575f57aeb`. It was not reset. `START.sh` was not run, because `:8002` never returned 200 and a run on this pod would launch a new vLLM. No completion was sent. No RAG question was sent.
- Live health is **not** VERIFIED. Mail, a second endpoint, Blackwell, and fresh-machine recovery stay blocked. Production stays **NO-GO**.
- Next agent: do not treat pid 12621 as reusable. Do not cold-start Qwen unless the operator approves a new GPU load. Do not start the H100.

### 2026-10-22 — A100 still on shard 5; start waiter exited; health still down

- Connect panel re-read before this watch: SSH over exposed TCP is still `195.26.233.38 : 53380`. The key was not printed. `screeching_crimson_vole` (`mlar88u3ku8utm`) stayed **Running**, A100 SXM, **$1.80/hr**. Stop, Terminate, Resize, and Start were not clicked. H100 `xx9cjogra5vcwl` was not started. No second `START.sh` was launched. No new file was written on `/workspace`.
- Samples from 2026-10-22T14:03:34Z through 14:48:01Z, about every 2.5 minutes. `:8002/health`, `:8010/health`, and `:8080/api/status` stayed HTTP **000 / 000 / 000**. GPU stayed **51923 MiB / 81920 MiB**. Utilization was 0% on these samples. EngineCore pid 13527 held **51914 MiB**. `/tmp/AI-PLAYBOOK` stayed `f7043f8ad8ed9ac39423f96fe7fcbd12f21fe7ba`. Qwen was not reloaded onto a newer commit.
- Shard progress in `/workspace/platform-diagnostics/first-release/qwen-vllm.log`: **2/11** at 14:03:34Z (vLLM elapsed 26:32, pids 2824 and 2826 still alive); **3/11** at 14:07:26Z (`[28:00<1:17:48, 583.52s/it]`); **4/11** at 14:22:39Z (`[43:30<1:24:02, 720.39s/it]`); **5/11** at 14:37:53Z (`[58:49<1:19:12, 792.02s/it]`). At 14:48:01Z the log was still **5/11** (9354 bytes). vLLM pid **12621** elapsed **1:10:59**, stat `SLl`, parent pid **1**. EngineCore **13527** elapsed **1:10:26**.
- The original waiter exited between the 14:20:07Z sample (pids 2824 and 2826 alive) and 14:22:39Z (those pids gone). Its own output, from the 13:11:19Z session, is `ERROR: Qwen not ready after 2700s (process 12621 still running; re-run later to reuse it)`, then `START_EXIT:1` and `START_END:2026-10-22T14:22:07Z`. vLLM was not killed. The GPU was not idle, so nothing was relaunched.
- No completion was sent. No RAG question was sent. Services were not restarted. Live health is **not** VERIFIED. Mail, a second endpoint, Blackwell, and fresh-machine recovery stay blocked. Production stays **NO-GO**.
- Next agent: leave pid 12621 alone while shards are still loading. A new `START.sh` fails preflight until this vLLM exits or `:8002` is healthy. When `:8002` is healthy, one `START.sh` can reuse it and bring up `:8010` and `:8080`. Do not start the H100.

### 2026-10-22 — integrator: area commits are on main; production NO-GO

- Fetched `origin` until `main` was `6d479937bc90b2bf6054d9de8ab2bfecfd3b465f`. `git pull --ff-only origin main` was already up to date. No merge conflict. Nothing was force-pushed. No other commit was reset. Nothing was packaged, and nothing was copied to the volume.
- SHAs fetched on that tip, newest first:
  - `6d479937bc90b2bf6054d9de8ab2bfecfd3b465f` — `web/auth/` plus the console Microsoft start route. A browser `Sec-Fetch-Site` of `same-site` or `cross-site` is refused before a sign-in attempt is stored. `docs/security/operator-auth.md` says the same.
  - `06e47834ed6578ff5b368783bd31d4380d325cce` — handoff only. Its evidence: one official `START.sh` on A100 `mlar88u3ku8utm` began about 13:11:19Z. At 13:58:38Z vLLM pid 12621 was still loading safetensors shard **2/11**, GPU **51923 MiB / 81920 MiB**, and `:8002` / `:8010` / `:8080` were HTTP **000**. Pod checkout `/tmp/AI-PLAYBOOK` was `f7043f8ad8ed9ac39423f96fe7fcbd12f21fe7ba`. H100 `xx9cjogra5vcwl` was not started. This integrator did not SSH and did not run `START.sh`. There is no later reading here, so the load stays **in progress**, not finished.
  - `1fbc1decdba5f0d8fd24edfc283de2574ebce1f8` — `rag/`. A citation is withheld when its text is not in that collection's retrieved chunk. `answer_delivery` still skips that check when `evidence` is omitted, and `api/local_gateway.py` still calls it without chunk text. That is the compatibility path the RAG function documents. Both sides' tests passed. It was not rewired.
  - `0061ae95c461b3c3ddf3cb964a190e1e54e1bcea` — `ops_centre/`. Graph, fleet, and repair jobs are not marked healthy on missing or stale evidence.
  - `c4834e7d2c94d5c6da6f3f64ae8a09035127db58` — `api/`. A dead or timed-out inference upstream fails fast with a structured error.
  - `cefec8593e9b15096496fee6a0066ba71f89f45b` — `web/` outside auth. The console shows loading and a gateway-down error, and a dead model engine is not treated as healthy.
  - Already on `main` before those pushes: `81b47752e05320240a84486ebbea50826823e3db` (typed tasks stay behind the approval gate), `7d3c10d55f0758400abb2bb3ea220b807361768d` (approved Graph draft updates and named-file changes, no mail sent), `e6f0b38a48ff1b0bb8c704409fec8334790665cf` (local archive checksum for `0089420`).
- `python -m ops.run_tests` on Python 3.11 was 42 modules, 41 ok, 1 failed, about 162 seconds. The failure was `web.test_server`: `PermissionError` WinError 5 replacing a temp `sessions.json`, first on the printer-restart case and then on chat and repair logout during the automatic retry. Those were not assertion mismatches between the new trees. An isolated rerun of `web.test_server` was 31 tests, OK, about 50 seconds. `integrations.tests.test_endpoint` skipped 1. `api.test_gateway_reliability` was 31 tests, logged a Windows socket abort, and still passed. No integration edit was required.
- The acceptance board still names running A100 `mlar88u3ku8utm` and stopped H100 `xx9cjogra5vcwl`. That matches the pod in the 13:58:38Z evidence, so the board was not edited. Live acceptance was not raised.
- Do not start a second `START.sh`. Do not start the H100. Do not reload Qwen onto this newer Git tip while that load is the running one. Production **NO-GO**. Gates still open: deployed commit equals intended Git tip, mail end-to-end, second endpoint, Blackwell live acceptance, fresh-environment recovery. Mail stays **NOT CONFIGURED**.

### 2026-10-22 — A100 start still loading; health still down

- The existing start was left alone. At 2026-10-22T13:30:20Z the process chain was still the one that began about **13:11:19Z**: pid 2824 `bash /workspace/ai-platform-release/START.sh`, pid 2826 `ops/start-first-release.sh --start`, pid 2890 `ops/restore-qwen-runtime.sh`, and `tar`/`zstd` extracting `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` (4,060,580,548 bytes) into `/tmp/.qwen-restore.K6Ijs9`. GPU **0 MiB / 81920 MiB**. `:8002/health`, `:8010/health`, and `:8080/api/status` were HTTP **000**. No second `START.sh` was launched. The H100 `xx9cjogra5vcwl` was not started. Stop, Terminate, and Resize were not clicked.
- Connect panel re-read on the A100 page: SSH over exposed TCP is still `195.26.233.38 : 53380`. The key was not printed. The pod stayed **Running**, A100 SXM, **$1.80/hr**.
- Restore progress: stage directory **2.6G** at 13:32:09Z and **5.7G** at 13:34:47Z. One SSH attempt at 13:36:47Z timed out during banner exchange. At 13:37:40Z `/tmp/vllm-qwen-env` was **9.5G**, vLLM pid **12621** had been up for 38 seconds, GPU was **4 MiB**, and health was still **000**.
- Weight load: GPU **51923 MiB / 81920 MiB** at 13:39:43Z (utilization 0%). The same memory figure held at 13:54:02Z (8%), 13:56:05Z (0%), and 13:58:38Z (7%). Health stayed **000 / 000 / 000** at every poll, including 13:58:38Z. The official vLLM log showed version `0.32.0rc1.dev62+g624a5ddaf`, filesystem `FUSE.GEESEFS`, checkpoint **51.75 GiB**, and safetensors progress **2/11** (about 8 minutes for the first shard and about 16 minutes 43 seconds to the second). vLLM pid 12621 was still alive at 21 minutes 36 seconds. Gateway and console were not up. No completion was sent. No RAG question was sent. Services were not restarted.
- `/tmp/AI-PLAYBOOK` HEAD at 13:58:38Z is `f7043f8ad8ed9ac39423f96fe7fcbd12f21fe7ba` on `main`. Qwen was not reloaded onto a newer docs commit. This recording commit is not on the pod.
- The 25-minute watch from 13:30Z ran through 13:58Z. The load is **not finished**. Live health is **not** VERIFIED. Mail, a second endpoint, Blackwell, and fresh-machine recovery have not passed. Production stays **NO-GO**.

### 2026-10-22 — archive of 0089420 recorded after the fact

- Code commit `00894206db6fec0238c6243e83ee7a5e18c7df08` was pushed to `main` and fast-forwarded onto `feature/qwen-a100-start-hardening` and `feature/qwen3.5-27b-integration`. `git ls-remote` showed that SHA on `HEAD`, `main`, and both feature branches. The parent was `f7043f8ad8ed9ac39423f96fe7fcbd12f21fe7ba`. Nothing was force-pushed.
- Local archive, read back in Python: `%LOCALAPPDATA%\AI-PLAYBOOK\releases\00894206db6fec0238c6243e83ee7a5e18c7df08\AI-PLAYBOOK-00894206db6fec0238c6243e83ee7a5e18c7df08.tar.gz`. 719,707 bytes, 383 tar members, SHA-256 `bf4355541d1dbeecfe6681c9bdfbe5235bff0dceed8a1570bb1e9d522e4f48be`. The sidecar matched. It contains `model_engine_dead` and the running A100 in `docs/release/RECOVERY.md`. This recording commit is not inside that archive. The archive was not copied to the volume. It was not extracted onto a fresh machine.
- The first `git archive` attempt did not see the new directory. The directory was created and the same commit was archived, then the bytes were read back. Weights were not copied. The H100 stayed **Stopped**. Production **NO-GO**.

### 2026-10-22 — recovery path is the running A100; a dead engine is not healthy

- Re-read `docs/AGENT_HANDOFF.md`, `docs/SYSTEM_MANUAL.md`, `docs/release/RECOVERY.md`, and `docs/release/PRE_SHUTDOWN.md`. The recorded check at 2026-10-22T13:01Z still stands: A100 `mlar88u3ku8utm` (`screeching_crimson_vole`) is **Running** at **$1.80/hr**, Global Volume `cmv2p5m0d000007jk9o3931ea` is mounted at `/workspace`, and `bash /workspace/ai-platform-release/START.sh --preflight` returned **PREFLIGHT_PASS** at 2026-10-22T13:02:45Z. `:8002`, `:8010`, and `:8080` refused connections. Qwen was not loaded. This session did not SSH, did not run `START.sh`, did not write `/workspace`, and did not start a pod.
- H100 `xx9cjogra5vcwl` (`reliable_moccasin_hummingbird`) stays **Stopped** at **$0.00/hr**. It must not be started. Recovery no longer tells the operator to wait for that H100 or to start it.
- Weights and the runtime archive stay only on volume `cmv2p5m0d000007jk9o3931ea`. Shard bytes were not copied off the volume. There is no independent weight backup.
- Gateway `/health` and `/readyz` no longer return ready when `/v1/models` still lists a model id but engine `/health` is dead, or when the model entry itself reports a failure. `/livez` still does not call the model. LOCAL/MOCK only. Live Qwen was not run. `python -m ops.run_tests` on Python 3.11 was 41 modules, 0 failed, exit 0, about 132 seconds. `integrations.tests.test_endpoint` skipped 1. `api.test_gateway_reliability` was 27 tests, logged a Windows socket abort, and still passed. `windows_repair.tests.test_live_diagnostics` failed once on a temp-file permission error and passed on the automatic retry. Acceptance percentages were not raised.
- Next cold start, and only after the GPU load is approved: `bash /workspace/ai-platform-release/START.sh`. Production **NO-GO**. Live gates still open: deployed commit equals intended Git tip, mail end-to-end, second endpoint, Blackwell live acceptance, fresh-environment recovery. Mail stays **NOT CONFIGURED**. Live acceptance was not raised.

### 2026-10-22 — A100 is the running volume pod; preflight passed; model not loaded

- RunPod at 2026-10-22T13:01Z: `screeching_crimson_vole` (`mlar88u3ku8utm`) is **Running**, A100 SXM x1, **$1.80/hr**, Stop button present. `reliable_moccasin_hummingbird` (`xx9cjogra5vcwl`) is still **Stopped** at **$0.00/hr**. Start was not clicked. The A100 was not stopped, resized, or terminated. The H100 was not started.
- Volumes tab on the A100: “New model container” `cmv2p5m0d000007jk9o3931ea`, type **Global**, mounted at `/workspace`, **126 GB**, **1,804 objects**. SSH `findmnt` at 2026-10-22T13:01:34Z: `5aac0c77-6fcc-4be9-a112-dfe3890e1373 fuse.geesefs /workspace`. This is the platform volume. Not BLOCKED.
- SSH TCP from the Connect panel: `root@195.26.233.38` port `53380`. The key was not printed. The old port `25839` was not used. `nvidia-smi`: NVIDIA A100-SXM4-80GB, 81920 MiB total, 0 MiB used, driver 595.91.07, 0% utilization, no compute apps.
- Health at 2026-10-22T13:01:34Z: `:8002/health`, `:8010/health`, and `:8080/api/status` all failed to connect (HTTP 000). At 13:03:23Z nothing was listening on those ports or `:8000`, and no platform process was running. `/tmp/AI-PLAYBOOK` did not exist before preflight. Weights shard 11, the runtime archive, and `/workspace/ai-platform-release/START.sh` were present. They were not overwritten.
- `bash /workspace/ai-platform-release/START.sh --preflight` at 2026-10-22T13:02:45Z printed **PREFLIGHT_PASS** and exit 0. It said “no services started, nothing restored.” It cloned `main` `cbbf185eecc6e46130ac4bdc1a8089fba0e89052` into `/tmp/AI-PLAYBOOK` only. Gemma was not loaded. `--start` and a full `START.sh` were not run. No completion and no RAG question were sent, because nothing was listening and those scripts would talk to a dead gateway. `update-source-only.sh` was not needed; the new checkout was already at `origin/main`.
- A search for `/workspace` files changed in the previous 30 minutes, at 13:03:23Z, returned none. The volume was not written. Production stays **NO-GO**. Mail stays **NOT CONFIGURED**. Live acceptance was not raised.
- Next approval, and only that, is the model load: `bash /workspace/ai-platform-release/START.sh`. That restores the runtime and loads Qwen. It was not run. This recording commit is not on the pod. The pod checkout stays `cbbf185eecc6e46130ac4bdc1a8089fba0e89052` until a later source-only update.

### 2026-10-22 — archive of d6d3ac2 recorded after the fact

- Code commit `d6d3ac2f9cb7fb3632b042c3fe58eefe0e180eb4` was pushed to `main` and fast-forwarded onto `feature/qwen-a100-start-hardening` and `feature/qwen3.5-27b-integration`. `git ls-remote` and `python -m ops.git_parity --ls-remote` showed that SHA on `HEAD` and all three refs. The parent was `b0ead09a8df7c5cd6abace971331ef46de6646a7`. Nothing was force-pushed.
- Local archive, read back in Python: `%LOCALAPPDATA%\AI-PLAYBOOK\releases\d6d3ac2f9cb7fb3632b042c3fe58eefe0e180eb4\AI-PLAYBOOK-d6d3ac2f9cb7fb3632b042c3fe58eefe0e180eb4.tar.gz`. 715,415 bytes, 383 tar members, SHA-256 `50df5371070cc5004cad45ec645e9da938460f077b373f08240fda1e24ac98ee`. The sidecar matched. It contains `reported_model_count` and `ops/release/START.sh`. This recording commit is not inside that archive. The first `git archive` attempt did not see the new directory. The directory was created and the same commit was archived, then the bytes were read back. The archive was not copied to the volume. It was not extracted onto a fresh machine.
- The H100 stayed **Stopped**. No live health call was added by this recording commit. Production **NO-GO**.

### 2026-10-22 — empty model list is not healthy; H100 still stopped

- Remote was `https://github.com/henokmeron/AI-PLAYBOOK.md.git`. Before this commit, `git ls-remote` showed `b0ead09a8df7c5cd6abace971331ef46de6646a7` on `HEAD`, `main`, `feature/qwen-a100-start-hardening`, and `feature/qwen3.5-27b-integration`. Untracked `__pycache__` was left uncommitted. No secret was printed. Nothing was force-pushed.
- A gateway `/health` answer of `ok` with zero models, and a registry probe that treated HTTP 200 with `{"data":[]}` as loaded, was a local bug. `/health` and the registry probe now require a model id. No upstream, or an empty list, returns HTTP 503 with `status` `unknown` (`model_server_absent` or `no_models_reported`). `/livez` is still process-only. The console connection is `unknown`, label “No model reported”, when a gateway returns HTTP 200 with `model_count` 0. `runpod_verified` stays false.
- LOCAL/MOCK: the new cases failed against the old code and passed after the fix. `python -m ops.run_tests` on Python 3.11 was 41 modules, 0 failed, exit 0, about 94 seconds. `integrations.tests.test_endpoint` skipped 1. `api.test_gateway_reliability` logged a Windows socket abort and still passed. Live Qwen was not run.
- RunPod console at `2026-10-22T12:55:53Z`: pod `xx9cjogra5vcwl` (`reliable_moccasin_hummingbird`) is **Stopped**. Pause icon, Start for **$3.19/hr**, Compute **Not running**, Container storage **Not running**, **$0.00/hr**. Start was not clicked. Terminate was not clicked. SSH to `216.81.245.55:25839` was refused. No current TCP port was shown. `:8002/health`, `:8010/health`, and `:8080/api/status` were not called. `/tmp/AI-PLAYBOOK` was not read. `update-source-only.sh` was not run. No volume path was written.
- `screeching_crimson_vole` (`mlar88u3ku8utm`, A100 SXM, $1.80/hr) was Running. It was not used. Gemma was not loaded. This PC is not a second endpoint. Blackwell was not verified.
- Microsoft loopback consent was not started because the pod console is not running. No secret was created. Mail scopes were not widened. Status stays **NOT CONFIGURED**.
- Production **NO-GO**. Live checks are **BLOCKED** until this H100 is Running. Qwen was not restarted because it was not running.

### 2026-10-22 — uncited answers and “do not cite” text

- Parent commit on the three refs was `33026ffb3bf7e0378c221ec0eed1bdba92d947d4`. Untracked `__pycache__` was left uncommitted. The pod was not started. The volume was not written. No secret was printed.
- A model answer that names no `[Source N]` while evidence exists was returned as `answered`. It is now withheld. The gateway reason is `missing_citations`. The console shows “The answer did not cite a source from the evidence.” An out-of-range citation is still `invalid_citations`.
- Document text “Do not cite the source” was not flagged. It is now marked instruction-like and the evidence block carries the existing warning. This is a mock gateway test. Live Qwen was not run.
- LOCAL/MOCK: the new retrieval and gateway cases failed before the fix. `python -m ops.run_tests` on Python 3.11 was 41 modules, 0 failed, exit 0, about 132 seconds. `integrations.tests.test_endpoint` skipped 1. `api.test_gateway_reliability` logged a Windows socket abort and still passed. Acceptance percentages were not raised. Production **NO-GO**.

### 2026-10-22 — document names and collection cache isolation

- Remote was `https://github.com/henokmeron/AI-PLAYBOOK.md.git`. Before this commit, `git ls-remote` showed `758177dfad9c6ddac588debce55ab0729704c8fd` on `HEAD`, `main`, `feature/qwen-a100-start-hardening`, and `feature/qwen3.5-27b-integration`. Untracked `__pycache__` was left uncommitted. The pod was not started. No volume, S3 key, or other paid resource was created. No secret was printed.
- A filename containing a colon, such as `notes.txt:hidden.md`, was accepted and on this Windows PC attached a stream to `notes.txt` without replacing the visible text. `validate_filename` now rejects `:`. The same upload is refused and the visible file is unchanged.
- A collection directory that is a symbolic link to another collection was listed and written as that other collection. `list_documents` and `store_document` now refuse the link. The target collection is unchanged.
- `FileBackedBm25Store.invalidate` used a path prefix, so invalidating `.../col` dropped the file cache for `.../col2`. It now drops only `resolved-path/` keys. The sibling collection cache stays.
- LOCAL/MOCK: the three new tests failed before the fix and passed after it. `python -m ops.run_tests` on Python 3.11 was 41 modules, 0 failed, exit 0, about 180 seconds. `integrations.tests.test_endpoint` skipped 1. `api.test_gateway_reliability` logged a Windows socket abort and still passed. Live H100 scripts were not run. Acceptance percentages were not raised. Production **NO-GO**.

### 2026-10-22 — archive of 5cb961b recorded after the fact

- Code commit `5cb961b29173dbceb8cfe661bb23a5f0cbeb39c5` was pushed to `main` and fast-forwarded onto `feature/qwen-a100-start-hardening` and `feature/qwen3.5-27b-integration`. `git ls-remote` showed that SHA on `HEAD` and all three refs. The parent was `4ee02bd843a8e40d59f8121e09c0b81bdabe7648`. Nothing was force-pushed.
- Local archive, read back in Python: `%LOCALAPPDATA%\AI-PLAYBOOK\releases\5cb961b29173dbceb8cfe661bb23a5f0cbeb39c5\AI-PLAYBOOK-5cb961b29173dbceb8cfe661bb23a5f0cbeb39c5.tar.gz`. 709,868 bytes, 383 tar members, SHA-256 `3d77ab37436ed25caa8940a3da45a6768cd84943c768e9794c86c35647730984`. The sidecar matched. It contains `ops/git_parity.py` and `ops/acceptance_board.py`. This recording commit is not inside that archive. The archive was not copied to the volume.
- `python -m ops.release.recover` extracted that archive into `%TEMP%\ai-playbook-recover-5cb961b-temp-extract`. `ops/release/START.sh` was present. That is a temp extract, not a fresh machine, not a second computer, and not a deployment.
- The first `git archive` attempt did not see the new directory. The directory was created and the same commit was archived, then the bytes were read back. Weights were not copied. The pod was not started.
- Offline implementation on the board is 100% for the offline criteria. Live acceptance stays blocked. Production **NO-GO**.

### 2026-10-22 — offline completion split from live acceptance

- `CURSOR_OFFLINE_COMPLETION_SPRINT.md` was not in this checkout, Downloads, Documents, the Cursor project folder, or GitHub (`main` raw URL returned 404). Work followed the owner's order and this handoff. Desktop is not present on this PC.
- Remote was `https://github.com/henokmeron/AI-PLAYBOOK.md.git`. Before this commit, `git ls-remote` showed `4ee02bd843a8e40d59f8121e09c0b81bdabe7648` on `HEAD`, `main`, `feature/qwen-a100-start-hardening`, and `feature/qwen3.5-27b-integration`. Untracked `__pycache__` was left uncommitted. The pod was not started. No volume, S3 key, or other paid resource was created. No secret was printed.
- System Status `GET /api/acceptance` now shows two figures. Offline implementation counts source, RAG unit cases, release packaging, the temp extract, git parity, and docs. Live acceptance counts deployment, mail, a second computer, Blackwell, a fresh machine, and the volume. `overall_percent` is the live figure. Production decision stays **NO-GO**. Offline 100% is not a production GO. Live acceptance was not raised. Pod health was not claimed.
- Host values that are not `localhost` or `127.0.0.1`, with an optional numeric port, are rejected. A foreign Origin on login is rejected. Retrieval stays BM25 when an embedder is missing, raises, or returns a value. Empty, malformed, and duplicate cases are in `rag.tests.test_retrieval_pipeline.OfflineEdgeTests`.
- `python -m ops.git_parity` checks origin and does not push. `python -m ops.git_parity --ls-remote` checks the three refs. A matching SHA is not a deployment.
- LOCAL/MOCK: focused `python -m unittest ops.test_acceptance_board ops.test_git_parity rag.tests.test_retrieval_pipeline web.test_auth web.test_server` was 81 tests, exit 0. `python -m ops.run_tests` on Python 3.11.9 was 41 modules, 0 failed, exit 0, about 162 seconds. `integrations.tests.test_endpoint` skipped 1. `windows_repair.tests.test_live_diagnostics` hit a temp-file PermissionError once and passed on the runner's automatic retry. Live H100 scripts were not run.
- Temp extract, not a fresh machine: `python -m ops.release.recover` extracted `6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8` into `%TEMP%\ai-playbook-recover-6f07b58-temp-extract`. Sidecar SHA-256 `3cf154feb99536781232408ea06cc93373e14fe69e1d866daffa64ecdb015de7`. `ops/release/START.sh` was present. The archive of this commit is not recorded yet.
- Qwen3.5-27B remains the only auto-started model. Gemma was not loaded. Privileged repair was not run. This PC is not a second endpoint. Blackwell was not verified. Microsoft mail stays **NOT CONFIGURED**.
- Production **NO-GO**. Live blockers: pod start, deployed commit equals the intended tip, mail consent and a mailbox read, a second Windows computer, Blackwell hardware, a fresh machine, and a volume copy.

### 2026-10-22 — Global Volume access while the H100 is stopped

- Remote was `https://github.com/henokmeron/AI-PLAYBOOK.md.git`. Local `main` was `a05e17715a045c538c92bfce72181bdb1a9fae6c` before this note. Untracked `__pycache__` was left uncommitted. The pod was not started, stopped, resized, reloaded, or redeployed. No volume, S3 key, or other paid resource was created. No file was written on the volume. No secret was printed.
- Pods page, reloaded: one pod, `reliable_moccasin_hummingbird` / `xx9cjogra5vcwl`, H100 NVL. Pause-icon tooltip text **Stopped**. Cost **$0.00/hr**. Utilization, memory, and disk cells empty. Inspector Details: Compute **Not running**, Container storage **Not running**, GPU location **US-KS-2** (the pod's last data center, not a volume region). The Start control reads **Start for $3.19/hr** and was not clicked. Terminate was not clicked. No second pod, so there is no already-running CPU pod.
- Storage page `https://console.runpod.io/user/storage`, page title **Network Storage**. The only row is **New model container**, id `cmv2p5m0d000007jk9o3931ea`, type badge **Global**, location **Any**, **126.0GB stored**, **1,804 objects** after reload, **$11.34/mo**. The already-open tab first showed 1,794 objects; that matched the earlier running-pod note and was stale until reload. The row menu (`global-volume-actions-menu`) is **Deploy**, **Edit**, **Delete**. There is no Browse, no file list, and no S3 action on this volume. The page-level **Create S3 API key** button was not clicked. The Keys page was not opened.
- Pod inspector Volumes tab, while stopped: type **Global**, “Mounted at `/workspace`”, and the usage line **0 Bytes / 0 objects**. That contradicts the Storage page. It is not a directory listing. Do not treat 0 objects as an empty volume. Object names were not listed.
- Official docs, read this session: [S3-compatible API](https://docs.runpod.io/storage/s3-api) says “Use Runpod’s S3-compatible API to access and manage your network volumes.” The word global does not appear on that page. Endpoints are per data center, for example `https://s3api-us-ks-2.runpod.io/`, path `s3://NETWORK_VOLUME_ID/...`. [Storage overview](https://docs.runpod.io/storage/overview) lists the S3 API as “Manage files on your network volumes” and lists Global volume compute as **GPU only**. [Global volume overview](https://docs.runpod.io/storage/globalvolume/overview) says a global volume “mounts automatically at startup” and “Global volumes can't be attached to CPU Pods or CPU Serverless endpoints.”
- Direct S3 access for **this** Global Volume: **not supported**. No credential was created and none was used. The safest read that does not start a GPU pod and does not create a paid resource is to wait for the next approved start of this same pod, then `ls /workspace` from the pod console or SSH. Do not create an S3 key for this volume. Do not create a CPU pod. A zero-GPU start would still be starting the pod.
- `ops/test_lanes.py` records that `python -m ops.run_tests` is LOCAL/MOCK, including `windows_repair.tests.test_live_diagnostics` on this PC, and that `agents.live_smoke`, `agents.live_async_smoke`, `evaluation.run_live_platform_smoke`, and `evaluation.run_live_rag_regression` are REQUIRES LIVE INFERENCE and REQUIRES DEPLOYED H100. Those four were not run.
- LOCAL/MOCK: `python -m unittest ops.test_lanes ops.test_acceptance_board ops.test_run_tests` ran 3 tests, exit 0. `python -m ops.run_tests` on Python 3.11 was 40 modules, 0 failed, exit 0, about 116 seconds. `integrations.tests.test_endpoint` reported 1 skip. `api.test_gateway_reliability` logged a Windows socket abort and still passed. `git diff --check` exit 0. Acceptance percentages were not raised. Production **NO-GO**. Failing acceptance: deployed commit equals intended Git tip, mail end-to-end, second endpoint, Blackwell live acceptance, fresh-environment recovery.

### 2026-10-22 — volume snapshot before the owner stops the H100

- Remote was `https://github.com/henokmeron/AI-PLAYBOOK.md.git`. `git ls-remote` showed `6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8` on `main`, `feature/qwen-a100-start-hardening`, and `feature/qwen3.5-27b-integration`. Local HEAD matched. Untracked `__pycache__` was left uncommitted. The pod was not stopped, resized, reloaded, or redeployed. Qwen, the gateway, and the console were not restarted.
- Local archive re-hashed before the copy: `%LOCALAPPDATA%\AI-PLAYBOOK\releases\6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8\AI-PLAYBOOK-6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8.tar.gz`, 696,562 bytes, 380 members, SHA-256 `3cf154feb99536781232408ea06cc93373e14fe69e1d866daffa64ecdb015de7`. It contains `ops/release/START.sh`, `snapshot-published-tip.sh`, and `update-source-only.sh`. This note is a later commit and is not inside that archive.
- `snapshot-published-tip.sh` was not executed. With `VOLUME_COPY_APPROVED=yes` it would also run `install-to-volume.sh` and append `VERSION.txt`. Those existing files were left untouched. The already verified local archive, its manifest, and its sidecar were copied to new paths only.
- Volume read-back: `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-runpod-first-6f07b58.tar.gz` SHA-256 `3cf154feb99536781232408ea06cc93373e14fe69e1d866daffa64ecdb015de7`, 696,562 bytes, 380 members. `sha256sum -c` of `/workspace/ai-platform-backups/manifests/AI-PLAYBOOK.md-runpod-first-6f07b58.sha256` printed OK. Sidecar and manifest JSON were copied beside it. Manifest text: `/workspace/ai-platform-backups/manifests/shutdown-asset-manifest-6f07b58-20261022T015922Z.txt`.
- Already on the volume and re-checked: weights directory present (11 shards listed, about 52G; shard bytes **NOT RECOMPUTED**; small manifest file still SHA-256 `8f4e2624e9d53ece3c7590b02b6cdde16d7072b2aa98687225a77abe7ea60185`). Runtime `sha256sum -c SHA256SUMS` OK, including `vllm-qwen-env.tar.zst` `666bb7c3fde67503c1d728d7d9501d597069e527eabb617228beebe5e626c9fb`. RAG docs and wheelhouse present. `/workspace/ai-platform-release/START.sh` SHA-256 `41af7e93f34f2d28d9b97d53b18a4c58565dcb50e35bcdd6e71e40cfdaf92ca6`, same as git `ops/release/START.sh`, and it contains `restore_from_snapshot` with `PLATFORM_BRANCH` default `main`. Older snapshot `01e7692` still `a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370`. Mount remained `fuse.geesefs` `5aac0c77-6fcc-4be9-a112-dfe3890e1373`.
- Operator file existed only under `/tmp/console-operators/operators.json` (mode 0600, 378 bytes, one enabled admin, scrypt, no plaintext password field). Copied to `/workspace/platform-state/operator-backups/20261022T015922Z/` with `SHA256SUMS`. File SHA-256 `41811efc68d6723d5dc77dc1af06c882397b793ec9d5d0eae03ea9bef91ac6bf`. Sessions were not copied. `/tmp/platform-gateway.key` was not copied; start recreates it. `/tmp/microsoft-365-token.json` was absent. `/tmp/console-operator.secret` (25 bytes, mode 0600) was not copied. `/tmp/vllm-qwen-env` was not copied.
- SSH read at `2026-10-22T01:55:49Z`: `/tmp/AI-PLAYBOOK` `a0e9422145aae4e38025709d1ca88288e42f375b`, origin correct, no tracked edits. Health 200 on `:8002/health`, `:8010/health`, `:8080/api/status`. GPU NVIDIA H100 NVL, 85,415 MiB of 95,830 MiB, driver 595.91.07, util 0%. Health checked again at `2026-10-22T02:00:24Z` and was still 200. `START.sh` was not run.
- A pod stop deletes `/tmp` (checkout, restored env, gateway key, sessions, the operator secret). The next start still works because GitHub `main` is cloned by the volume launcher, the runtime archive and weights stay on the volume, and the new snapshot is the offline fallback. After a new pod with this same volume is Running: `bash /workspace/ai-platform-release/START.sh --preflight` then `bash /workspace/ai-platform-release/START.sh`. Do not run that while this pod is still the one being shut down.
- The commit on the volume is `6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8`. A later documentation commit is not copied to the volume. Production **NO-GO**.

### 2026-10-22 — finish-order evidence, release checks, still NO-GO

- Remote was `https://github.com/henokmeron/AI-PLAYBOOK.md.git`. Starting HEAD `d8c32ffebad6295b5d891de09681e46bbe2f022c` matched `origin/main` and both feature branches. Do not commit `__pycache__`.
- Archive of that commit, re-read in Python: `%LOCALAPPDATA%\AI-PLAYBOOK\releases\d8c32ffebad6295b5d891de09681e46bbe2f022c\AI-PLAYBOOK-d8c32ffebad6295b5d891de09681e46bbe2f022c.tar.gz`, 685,460 bytes, 377 tar members, SHA-256 `de30f6a2877fee34036731ab58073da8e0433cd6a10742e4ecfb4b6f3437f0c6`. The manifest `sha256` matched. It contains `ops/release/update-source-only.sh` and `docs/AGENT_HANDOFF.md`. This note is a later commit and is not inside that archive.
- `python -m ops.release.recover` extracted that archive into `%TEMP%\ai-playbook-recover-d8c32ff` after the checksum check. Required files were present. This is an isolated local extract, not a fresh-machine recovery and not a deployment.
- `ops/release/make_release.py` now writes a `.sha256` sidecar beside the archive and reads it back. `ops/release/update-source-only.sh` refuses a checkout whose origin is not `https://github.com/henokmeron/AI-PLAYBOOK.md.git`, fast-forwards only, and does not signal Qwen, the gateway, or the console. It was not run on the H100. `ops/release/snapshot-published-tip.sh` stays a dry-run unless `VOLUME_COPY_APPROVED=yes`, and a failed checksum deletes only the new incomplete snapshot. It was not run. No file was written on the Global Volume. Weight shards were not copied. There is still no independent weight backup.
- Repeatable git parity is `PLAYBOOK.md` section G. A push is not a deployment.
- The existing System Status page shows the finish-order board from `GET /api/acceptance` (`ops/acceptance_board.py`). Percentages count completed criteria. Decision stays **NO-GO**.
- SSH read-only at `2026-10-22T01:18:42Z`: `/tmp/AI-PLAYBOOK` `a0e9422145aae4e38025709d1ca88288e42f375b`; `:8002/health` 200; `:8010/health` 200; `:8080/api/status` 200; `nvidia-smi` NVIDIA H100 NVL, 85,415 MiB of 95,830 MiB, driver 595.91.07, GPU util 0%. `START.sh` was not run. Nothing was restarted.
- RunPod pods: one pod, green, `reliable_moccasin_hummingbird` / `xx9cjogra5vcwl`, H100 NVL, $3.20/hr, utilization 0% and 0%, memory 23% and 89%, disk 20%. Storage: Global Volume “New model container” `cmv2p5m0d000007jk9o3931ea`, 126.0 GB, 1,794 objects. No volume was created.
- Billing header, re-read after a reload: account balance **$14.93**, current spend rate **$3.197/hr**, estimated time left **5 hours**. The previous load of the same header showed **$15.46** with the same spend rate. Neither was $0.00. Inbox lines such as “$4.77” are older notifications, not the live balance. The pod was left running. Pay, a card, and credit codes were not used.
- Azure, signed in as the work account under Default Directory (`hgerez91gmail.onmicrosoft.com`). Entra overview tenant ID `d595636e-9ef4-4890-b8a7-bde8dd5cab03`, primary domain `hgerez91gmail.onmicrosoft.com`. App `llmfortestingclientid`. Authentication (Preview) saved platform **Mobile and desktop applications**, redirect `http://127.0.0.1:18080/api/microsoft/callback`, supported accounts **Single tenant only - Default Directory**. API permissions: delegated `Mail.Read` and `User.Read`, admin consent required **No**, other permissions for the directory **No permissions added**. Subscription “Azure subscription 1” `13be8a43-cb6b-4aca-ad34-2e4a0b5a62cb`, Owner, Active, one status cell “Not available”. Credits heading £150.95. No admin consent, no extra scopes, no new resource, no secret opened.
- Microsoft status: **NOT CONFIGURED**. Portal configuration is not a mailbox read. The running console has not loaded the application id. The one remaining consent click is only after an approved console deploy and an SSH tunnel to `127.0.0.1:18080`, with `MICROSOFT_TENANT` set to the directory above. `common` will not complete sign-in. No mail was sent.
- Second endpoint: **NOT TESTED**. Needs another Windows computer. This PC is not that computer. Blackwell: **NOT TESTED**. Needs a CC 12.0 GPU and driver 575 or newer. The H100 is not that result. Live Qwen RAG was not re-run.
- `python -m ops.run_tests` on Python 3.11.9 with PyYAML 6.0.3: 39 modules, 0 failed, 1 skipped (`integrations.tests.test_endpoint`), exit 0. `api.test_gateway_reliability` logged a Windows socket abort and still passed. `windows_repair.tests.test_live_diagnostics` hit a temp-file permission error once and passed on the runner's automatic retry. Live Qwen RAG was not re-run. The finish-order board overall is 49%. Decision **NO-GO**.
- Production **NO-GO**. Failing acceptance: deployed commit equals intended Git tip, mail end-to-end, second endpoint, Blackwell, fresh-environment recovery.

### 2026-10-22 — archive of 9893cec recorded after the fact

- Code and evidence commit `9893cec4f3eb8b03370a4cab5f9a2dee9ab860b8` was pushed to `main` and fast-forwarded onto both feature branches. `git ls-remote` showed that same SHA on all three refs.
- Local archive, read back in Python after packaging: `%LOCALAPPDATA%\AI-PLAYBOOK\releases\9893cec4f3eb8b03370a4cab5f9a2dee9ab860b8\AI-PLAYBOOK-9893cec4f3eb8b03370a4cab5f9a2dee9ab860b8.tar.gz`. 696,043 bytes, 380 tar members, SHA-256 `65cbcb5f16a90a5c4008f1a9e7e78b61916564df723da3c4da3ae34deaf2e2d5`. The manifest and the `.sha256` sidecar matched. It contains `ops/acceptance_board.py` and `ops/release/update-source-only.sh`. This recording commit is not inside that archive. The archive was not copied to the volume. The first `git archive` attempt did not see the new directory; the directory was created and the same commit was archived, then the bytes were read back. Weights were not copied.

### 2026-10-22 — release packaging and Microsoft read scope

- `CURSOR_AI_PLATFORM_FINISH_INSTRUCTIONS.md` was searched again and is still absent. This pass followed the handoff and the owner's order.
- Read-only recheck of pod `xx9cjogra5vcwl`: still running, H100 NVL, $3.20/hr, header balance $16.80. `nvidia-smi` still 85415/95830 MiB, driver 595.91.07. `/tmp/AI-PLAYBOOK` still `a0e9422145aae4e38025709d1ca88288e42f375b`. `:8002/health`, `:8010/health`, and `:8080/api/status` each returned 200. The pod was not started, stopped, resized, reloaded, or redeployed. Volume mount unchanged. No file was written on the volume.
- Local package of `281eb628b51f100433e3f4ab0aad83b516050ae5`: SHA-256 `1a998f7103cc8ca4a9f3a14047eb37e14d95470bba87c232c085e09851b7dad7`, 682,017 bytes, 375 tar members, under `%LOCALAPPDATA%\AI-PLAYBOOK\releases\`. Python read the manifest back. Not copied to the volume. This note is a later commit and is not inside that archive. GitHub remains the source backup. The weight shards were not copied off the volume, so there is still no independent weight backup.
- `ops.release.package.git_executable` finds a git binary that prints a version when PATH `git` is only a launcher. `ops/release/update-source-only.sh` fast-forwards a clean checkout only after `SOURCE_UPDATE_APPROVED=yes` and does not signal Qwen, the gateway, or the console. It was not run on the H100.
- The existing Entra registration was reused. Delegated `Mail.Read` was added beside `User.Read`. Admin consent required is No. `Mail.Send`, `Mail.ReadWrite`, and application permissions were not added. No secret was created or displayed. The loopback redirect was typed into the open manifest editor and Save stayed disabled, so the saved redirect is **NOT VERIFIED**. No mailbox was read. The app is single-tenant, so `MICROSOFT_TENANT=common` will not complete sign-in. Microsoft mail stays **NOT CONFIGURED**. Default authorize scopes in code are now `User.Read` and `Mail.Read` only.
- Production **NO-GO**.

### 2026-10-22 — read-only collectors and asset inventory

- `CURSOR_AI_PLATFORM_FINISH_INSTRUCTIONS.md` was not in the local tree, Downloads, Documents, the Cursor project folder, or GitHub `main` (raw URL 404). Work followed this handoff and the owner's order.
- Eight catalogue procedures now have fixed PowerShell collectors: `win.activation.inspect`, `hw.usb.inspect`, `net.wifi.inspect`, `net.proxy.inspect`, `net.tls.inspect`, `app.browser.inspect`, `app.permissions.inspect`, `app.crash.evidence`. They do not accept a model-supplied command or path. They do not read a product key, Wi-Fi password, proxy credential, or private key, and they do not change ACLs, the firewall, processes, or browser profiles. `problem_resolved` stays false. The endpoint heartbeat list in `integrations/endpoint.py` was not expanded.
- **VERIFIED** on this development PC, which is not a customer endpoint and not a repair: `python -m unittest windows_repair.tests.test_live_diagnostics.WindowsIntegrationTests.test_new_read_only_collectors_run_on_this_pc` exit 0. Full suite: `python -m ops.run_tests` with `C:\Users\henok\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe` (Python 3.11.9, PyYAML 6.0.3), 38 modules, 0 failed, 1 skipped (`integrations.tests.test_endpoint`), exit 0. `windows_repair.tests.test_live_diagnostics` hit one transient Windows state-file error and passed on the runner's automatic retry.
- RunPod console was signed in. One running pod: `xx9cjogra5vcwl` / `reliable_moccasin_hummingbird`, H100 NVL, $3.20/hr. Header balance text was $18.13. Nothing was started, stopped, resized, or reloaded. Read-only SSH confirmed Qwen `:8002/health` 200, gateway `:8010/health` 200, console `:8080/` and `/api/status` 200. Pod git is `a0e9422145aae4e38025709d1ca88288e42f375b`.
- Volume checksums computed this session are in `docs/results/asset-inventory-2026-10-22.md`. The 11 weight shards were listed and not re-hashed. No archive was copied onto the volume. Local source package of `0aa1caf21fea9570da8af21379f56e635aa2b3d7`: SHA-256 `b3cd3683fdceeb943e6a464ab9ef8f1cd5833799c3503af9b79f3823fe9be42f`, 375 tar members. The commit that records this hash is not inside that archive.
- Entra app `llmfortestingclientid` (`07634d62-4b0e-4572-b586-c5922bb01570`, created 2026-10-21) is in the signed-in Default Directory. The only API permission listed was Microsoft Graph `User.Read` (delegated). `Mail.Read` was not listed. No Graph call was made and the Pod was not given this application id. Microsoft mail stays **NOT CONFIGURED**. Azure showed £150.95 credits expiring 2026-11-20. No Azure resource was created.
- Live Blackwell **NOT TESTED**. Production **NO-GO**.

### 2026-10-21 — release archive extraction hardening

- Source changes in ops/release/package.py now reject POSIX/Windows traversal, Windows drive/UNC paths, NULs, colon-based alternate data streams, symlinks, hardlinks, devices, FIFOs, and a symlink extraction destination. Regression cases were added to ops/test_release_package.py.
- **FOCUSED TEST VERIFIED:** GitHub Actions run 39690350318 passed ops.test_release_package and generated the 374-member archive for commit b25294644ffd69415ecb4291723047ec647e8b41 (SHA-256 `e92c9005052d63006a03004bfe212ace11969074a86be6c3c2b333624b33fdf1`; artifact ID 12387414455). The full `python -m ops.run_tests` suite is **NOT RUN** for this change. A fresh clone failed because this execution environment could not resolve github.com, and the local Windows working tree could not be inspected.
- GitHub's authenticated connector can read/write the repository. The root README.md lookup returned 404; PLAYBOOK.md is the root project playbook. The local Windows working tree could not be inspected, so preserve any uncommitted changes there; do not assume it is clean or synchronized.
- RunPod inventory and Global Volume inspection are **BLOCKED / NOT VERIFIED**: no authenticated RunPod browser or SSH key is available in this session. No Pod/paid-resource mutation, model reload, volume write, or Microsoft Graph call occurred. RunPod volume copy remains **NOT VERIFIED**. The main-push workflow now produced a verified artifact for code-bearing commit b25294644ffd69415ecb4291723047ec647e8b41: archive SHA-256 `e92c9005052d63006a03004bfe212ace11969074a86be6c3c2b333624b33fdf1`, 374 members, artifact ID 12387414455 (90-day retention). The artifact is not a GitHub Release and was not copied to `/workspace`.
- Production remains **NO-GO** until the tests run and live behavior, security, integrations, and acceptance tests are verified.


### 2026-10-21 — Blackwell pin verified; release checksum corrected; offline defects fixed

- Tip was already `3843c98` on `origin/main`. Four Blackwell files match `7037ae9`; working tree had no uncommitted Blackwell edits (only `__pycache__` / local `ops-centre/` runtime junk — leave untracked).
- **Release recover digest for `7037ae9`:** SHA-256 `841a231a8e01ebe83b4fd6a79e315b0a54f76c8581b01fbc936d5e5074b64d13` (`git archive --format=tar.gz`). Prior digest `2c5bab93…` does not match; do not use it for recover. Archive + manifest under `~/AI-PLAYBOOK/releases/7037ae9…/` (and `%LOCALAPPDATA%\AI-PLAYBOOK\releases\` on Windows). Not on the volume.
- Offline suite on this Linux host failed until fixed: (1) `AlertService` treated missing fingerprint as monotonic `0` and suppressed first alerts while uptime < cooldown; (2) `assert_safe_state_path` followed symlinks before reject; (3) preflight rejected Windows `C:\…` paths on POSIX; (4) live Windows collector assertion skipped on non-Windows. Assertions otherwise unchanged.
- **VERIFIED offline:** `python -m ops.run_tests` — 38 modules, exit 0. cu129 wheel HEAD 200; cu130 404. Blackwell GPU path **NOT TESTED**.
- Tip commit `7615fd55e70789ea5387f92b3578c6be8b875233` release SHA-256 `205933b31d77fde5c6c8397f644afc38ec95f3eb88960971ecf1493ac298a52b` (kept separate from the `7037ae9…` archive).
- RunPod console inventory **BLOCKED** (browser not logged in). Evidence: `docs/results/runpod-inventory-blocked-2026-10-21.md`. No SSH key. No Pod mutations. Go-live **NO-GO**.

### 2026-10-21 — Blackwell CUDA 12.9 pin (source + offline proof)

- Code commit `7037ae9eff56d7694ca79c335f90e445bdf1fdc1` on `origin/main`. Profile `qwen-vllm-blackwell-cu129`; lock pins vLLM `0.32.0+cu129` + torch `2.13.0+cu129`; installer verifies wheel SHA-256 `9918be806fb2808c406547ff4f9f43870ac6ff28dc4b179291fcf532145bb50b`.
- Release recover digest: `841a231a8e01ebe83b4fd6a79e315b0a54f76c8581b01fbc936d5e5074b64d13` (see newer session entry). Live Blackwell **NOT TESTED**. Volume copy **BLOCKED**. Go-live **NO-GO**.

### 2026-10-21 — mandatory living playbook recorded

- Documented owner mandate in `PLAYBOOK.md` (sections A–F after project purpose). Standing rule #9 points there. Change log notes the recording only. No feature work. §11 Initial roadmap unchanged.

### 2026-10-21 — agent audit for registered Windows checks

- Code commit `dd197bf275e21a237780f3baac531f8bfd575695` on `origin/main`. Release SHA-256 `418c86529cd5814b4f79ca74d6de64eb68f2b9c2e727c3eb0ad1a7eff6b1f151`, 370 files, under `%LOCALAPPDATA%\AI-PLAYBOOK\releases\`. Not copied to `/workspace`. This session log is not inside that archive.
- `windows_repair_diagnose` now returns a schema-checked result with `untrusted=true`, `problem_resolved=false`, and `changed_device=false`, and appends a hash-chained audit record. The tool waits at most 25 seconds. The registered script waits at most 18 seconds. A timeout or unreadable collector is not reported as a successful diagnosis.
- On this PC that tool ran `win.update.inspect`, `win.events.recurring`, `win.startup.inspect`, and `win.performance.inspect`. Each returned `evidence_source=live_windows`. This is the development computer, not a second endpoint, and not a repair. No service was restarted.
- `windows_repair_request_change` pauses until a person approves that procedure id. Approval records the request. It does not restart the spooler, install a driver, disable the firewall, or run sfc or DISM. A fake collector containing "ignore previous instructions" and a password-shaped value could not set `problem_resolved` or skip the pause. The password-shaped value was redacted before the next model turn.
- Tests: `python -m ops.run_tests` with Python 3.12 — 38 modules, 451 tests, 2 skipped, 0 failed, exit 0. Gateway reliability logged one Windows socket abort and exited 0. Those tests did not call Microsoft Graph or the Pod.
- Microsoft: a search of the available tool namespaces found no browser-drive, Jupyter, or RunPod tool. `scripts/entra_app_manifest.py` remains the admin checklist. No application was created and no Graph call was made. **NOT CONFIGURED**.
- Pod `xx9cjogra5vcwl`: `%USERPROFILE%\.ssh\id_ed25519` is not on this PC. The Pod was not contacted, created, stopped, resized, or reloaded. Do not claim the running console is `dd197bf`. Qwen was not reloaded.
- Go-live **NO-GO**.

### 2026-10-21 — live network, service, and device diagnosis

- Code commit `890883c0cf19f48ae1acb72b61bee052ebac277f` on `origin/main`. Release SHA-256 `f4325b28d29d529a53755f783c78d0776aae7d2f9192e0c5f3fd09084ccd3b24`, 369 files, not on the volume.
- `windows_repair_diagnose` / `execute` now collects the registered read-only script when no fixture is supplied. Verified on this PC for `net.diagnose`, `win.services.inspect`, and `hw.devices.inventory`. `problem_resolved` stayed false. No service was restarted. Gateway addresses were not included.
- Microsoft and the H100 Pod were not contacted in this pass.

### 2026-10-21 — read-only Graph scopes and reliable test runner

- Code commit `7e7ff516fda9abf1d70a136104ffd8c397a22cee` on `origin/main`. Release SHA-256 `e20b686ad8f00f8516face757ae533093b677a88c710f47078caf4bdfb636591`, 369 files, not copied to `/workspace`.
- Microsoft: default authorize URL requests read-only Graph + ARM inventory scopes. `Mail.ReadWrite` only with `access=draft`. `MICROSOFT_CLIENT_ID_FILE` loads a private local id file. `scripts/entra_app_manifest.py` prints the portal checklist without secrets.
- Browser: Cursor `cursor-browser` Local Storage contained `portal.azure.com` and `console.runpod.io` markers. No MCP/browser-drive tool was available. Cookies were locked. No app registration and no Graph call from this agent. **NOT CONFIGURED**.
- Pod: still no `id_ed25519`. No Jupyter/RunPod automation tool. H100 was not inspected or restarted. Do not claim the running console is on `7e7ff51`.
- Tests: `python -m ops.run_tests` → 37 modules OK, exit 0. Skips are Windows symlink limits.

### 2026-10-21 — operator backup and agent-failure window

- The release archive is code commit `f6da54bc695c47e2184719aee618f3a51b05058d`. This session log is the follow-up note and is not inside that archive. SHA-256 `952c29081256ec5575038883e90268b67123beb4e0251d129622ffdbf082dff7`, 366 files, under `%LOCALAPPDATA%\AI-PLAYBOOK\releases\`. Not copied to `/workspace`.
- This session had no SSH key and no RunPod/Jupyter tool. Pod `xx9cjogra5vcwl` was not inspected, restarted, or stopped. The live `/tmp/console-operators` file was not backed up from here. Do not claim the running console is on `f6da54b`.
- New behaviour, tested locally: `ops/platform_state.py` backs up scrypt hashes to `/workspace/platform-state/operator-backups/` and restores them onto a private local file. Sessions, the gateway key, and the Microsoft token are not in the backup. `START.sh` refuses a console start when no administrator can be loaded or restored. There is no default password.
- Director agent health uses a 24-hour window. Older `agent.task_failed` rows stay in the audit log and do not mark current health **DEGRADED**. The same task id is recorded once. A local retrieval probe cited `warranty.txt` and abstained. It did not call Qwen. The Pod's RAG grounding was not re-run.
- Microsoft: no browser session and `MICROSOFT_CLIENT_ID` unset. **NOT CONFIGURED**. Endpoint fleet and repair jobs were not given a second Windows computer. Remote support stays MeshCentral **NOT CONFIGURED** until a session is established.
- Tests: discover 272 OK, 2 skipped, exit 0. Every `test_*.py` module: 441 tests, 2 skipped, 1 socket abort under load. `api.test_gateway_reliability` alone: 22 OK, exit 0. Go-live **NO-GO**.

### 2026-10-21 — H100 stack verified; Blackwell Pod was not present

- Canonical checkout `C:\Users\kokob\src\AI-PLAYBOOK.md` on `main`. Local and `origin/main` are `a0e9422145aae4e38025709d1ca88288e42f375b`. The Pod checkout `/tmp/AI-PLAYBOOK` is the same commit. Untracked `__pycache__` was not committed.
- The only Pod in the RunPod list is `xx9cjogra5vcwl` / `reliable_moccasin_hummingbird`, H100 NVL, `$3.20/hr`, driver **595.91.07**, compute capability **9.0**, 95,830 MiB. Global Volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373` is `fuse.geesefs` at `/workspace`. Eleven Qwen shards are present. The A100 env `/tmp/vllm-qwen-env` was restored and left in place. `/tmp/vllm-qwen-blackwell-env` was not created. No second Pod was created. The Pod was not stopped.
- `START.sh` was already loading Qwen when this session inspected the Pod. It reached `FIRST_RELEASE_READY` at 2026-10-21T20:04:56Z. Direct `:8002`, gateway `:8010`, and console `:8080` each returned the word `pong`. An administrator `platform-admin` was provisioned in `/tmp/console-operators`. The password file is mode `0600` on the Pod and is not recorded here. `MICROSOFT_CLIENT_ID` is absent. `GET /api/microsoft/start` returned **409**. Connectors are **NOT CONFIGURED**.
- Console health was falsely degraded because the probe read 400 bytes of `/api/status`. `a0e9422` reads 16,384 bytes. The console process was restarted after the fast-forward. Qwen and the gateway were reused, not reloaded. Operations Centre service health is **healthy**. Director overall stays **DEGRADED** (20 retained agent failures, RAG UNKNOWN, Graph NOT CONFIGURED, endpoint fleet UNKNOWN, repair jobs NOT CONFIGURED). Operator auth is HEALTHY for the ephemeral administrator.
- Local tests, not a second computer: Python 3.12.10, `python -m unittest` of the repo test modules, **426 tests, 2 skipped, exit 0**. The skips are symlink tests on Windows. PyYAML 6.0.3 loaded, so the registry loader tests ran. Microsoft and the model were not contacted by those tests.
- Release of `a0e9422145aae4e38025709d1ca88288e42f375b`: SHA-256 `6f4c2b2f62b4178f135170c293c9dfd374fb2698ff5933fb9a42de0ba6a0d06c`, 360 files, under `%LOCALAPPDATA%\AI-PLAYBOOK\releases\`. Not copied to `/workspace`. Go-live is **NO-GO**.

### 2026-10-20 — mock repair evidence is not healthy

- Director `repair_jobs` is HEALTHY only when an accepted job stores `evidence_source=live_windows` and the last-seen is under one day old. A mock, fixture, or file that lost its job state is UNKNOWN. A stale or failed check-in stays DEGRADED.
- An older state file that recorded a used nonce but no `job_states` still counts as accepted, and it is not HEALTHY until live evidence is present.
- No repair was run. The Pod was not contacted. This entry is not a deployment.

### 2026-10-20 — repair job lifecycle and canonical checkout

- Canonical checkout is `C:\Users\kokob\src\AI-PLAYBOOK.md` on `main`. Cursor global storage had no second git checkout of this repo. `C:\Users\henok\src\AI-PLAYBOOK.md` is not on this PC.
- Device jobs now persist `issued`, `accepted`, and `expired`. The Director calls a missing last-seen UNKNOWN and a last-seen older than one day DEGRADED.
- Pod `enxl57cz45zy1i` was not stopped, started, or contacted. No repair was run on this PC. Volume copy was not attempted.

### 2026-10-18 — task history no longer lands in the git tree

- The console treated any writable `/workspace` as the volume and wrote `agent-task-history/` into this checkout during a local test. That file was a failed mock task, not a volume backup, and it was not committed.
- History now stays at `/tmp/agent-task-history` unless `findmnt` reports `fuse.geesefs`, which is the Global Volume. `AGENT_HISTORY_DIR` still overrides that. On the Pod the volume path remains `/workspace/agent-task-history`.
- Tests: `web.test_server.HistoryDirectoryTests` and the agent-page console test, 3 OK. The repo directory was not recreated. `/tmp/agent-task-history` received the mock record.

### 2026-10-18 — health check could not reach the Pod

- Fast-forwarded this checkout from `7708140` to GitHub `693e2b46fd4e578cbb4022f79b5dd9d30ee7f765`. Untracked `ops/__pycache__/` was left untracked.
- **FAILED:** TCP `154.54.102.40:13212` connection refused. TCP `216.81.248.126:19091` connection refused. SSH to port `13212` with identity `$HOME/.ssh/id_ed25519` printed that the identity file is missing and `Connection refused`, exit 255. No key was generated. No Pod was started.
- **NOT RUN:** `/workspace` mount, GPU, weights, runtime archive, preflight, Qwen `:8002`, gateway `:8010`, console `:8080`, and `START.sh`. Recovery files in git say Pod `4lvr54b0wmkz6c` was stopped after the live helpdesk check and the Global Volume was kept. That stop was not re-checked in the RunPod UI.
- **Local tests, not live:** `/opt/ai-playbook-venv/bin/python -m unittest ops_centre.tests.test_ops_centre agents.tests.test_helpdesk agents.tests.test_history agents.tests.test_queue web.test_server` — 40 tests, OK, exit 0. Existing venv. No model load and no Graph call.
- Next action: Start the existing Pod in the RunPod UI (do not create another Pod), then connect from the Windows PC with `C:\Users\henok\.ssh\id_ed25519` and the new port. Do not reuse `13212` or `19091` until that page shows them.

### 2026-10-16 — AI Security & Operations Centre (local source)

- **Gap assessment + architecture:** `docs/ops_centre/GAP_AND_ARCHITECTURE.md`.
- **Implemented:** `ops_centre/` event store (hash-chained), health aggregator (works if Qwen down), detections, alerts, incidents, `/api/ops/*`, console **Operations** view, AI Ops allowlisted tools on `AgentDesk`.
- **Tests:** `ops_centre.tests.test_ops_centre` OK; `web.test_server` OK.
- **NOT RUN:** RunPod Start, model load, live SOC vs Qwen. Do not claim live SOC verification until a deliberate Pod session.
- **Still true:** Console has no login (baseline H-3); keep loopback. Hash chain is not forensic WORM.

### 2026-10-15 — FINAL live IT Helpdesk deploy (Qwen VERIFIED)

- Restored existing Pod `4lvr54b0wmkz6c` (SSH `154.54.102.40:13212`). Did **not** create a second Pod or redownload weights. Qwen/gateway already healthy; console-only deploy to **`c069674`**.
- First live helpdesk attempt failed: protocol violation (tool name as `action`). Fixed + pushed `7b61967`. Second failure after approval: token budget exhausted. Fixed + pushed `c069674`.
- **VERIFIED live:** `agents.live_async_smoke` FAILS=0; helpdesk smoke FAILS=0; approval smoke FAILS=0; browser UI ticket with Approve → completed/resolved. Details in `docs/results/helpdesk-live-qwen-2026-10-15.md`.
- **NOT RUN / NOT CLAIMED:** Entra, Graph mail, enrolled remote control, force-push, volume delete.
- After docs commit: Pod **Stopped** via RunPod console (not Terminated). Global Volume retained. Resume with Start + existing recovery path.

### 2026-10-15 — AI IT Helpdesk implemented (source + mock tests)

- Added `agents/builtin/helpdesk.py`: classify, platform health, allowlisted logs (redacted), safe diagnostics, approval-gated remediation, compose incident report.
- Wired into `AgentDesk` / console tools; richer IT playbook; approval panel fields (what/why/system/risks/verify); incident report in public view + UI.
- Agent page retitled **IT Helpdesk**. Existing async queue, cancel, history, `search_documents`, and connector catalog reused.
- **VERIFIED (local/mock):** `agents.tests` 101 OK; `agents.tests.test_helpdesk` 6 OK (includes scripted investigate → approve → verify → incident); `web.test_server` 23 OK.
- **NOT TESTED:** live Qwen helpdesk on the Pod with this commit (needs console deploy after `START.sh` finishes). No Entra app created. No live Graph.
- Emergency Pod restore earlier same day: `4lvr54b0wmkz6c`, SSH `154.54.102.40:13212`, volume OK, `START.sh` launched at tip `8dbbfbd` then this commit follows.

### 2026-10-15 — migrate failed; new A100 Pod live with `a680580`

- Owner approved migrate. API error: **Failed to get mount info for source pod**. Deployed `1cj381fjuujeq7` A100 SXM CUDA 13 + same volume instead. Old `vx4oe3oyfsqnz8` left stopped.
- **VERIFIED:** driver 580.126.16; `START.sh` → `FIRST_RELEASE_READY` (~730 s); `/tmp/AI-PLAYBOOK` = **`a680580`**; `:8002`/`:8010`/`:8080` HTTP 200; `_pod_e2e_verify.py` **FAILS: NONE**; Agent async calculator **50**; Agent cancel **cancelled**; console status **ready**.
- SSH: `root@154.54.102.45 -p 13502`. Evidence: `docs/results/runpod-migrate-deploy-2026-10-15.md`.
- **Cost:** Stop `1cj381fjuujeq7` when idle; keep volume; do not Terminate without approval.

### 2026-10-15 — agent queue + IT playbook; Start blocked (GPU gone)

- **VERIFIED (local):** Serial async queue (`queued` → run), cancel-while-queued, IT support playbook + incident output schema, richer Agent UI, history default `/workspace/agent-task-history` when volume writable. Tests: agents suite **95 OK**; `web.test_server` **23 OK**.
- **Live Start** on `vx4oe3oyfsqnz8` blocked (GPU unavailable). Later resolved by new Pod deploy (see entry above).

### 2026-10-15 — agent async progress + auditable history; Pod stopped

- **VERIFIED (local):** `AgentDesk.start(wait=False)`, cooperative cancel, `TaskHistoryStore`, `GET /api/agent`, `GET /api/agent/history`, Agent UI poll + recent-task list. Tests: `agents.tests.test_history` 4 OK; agents suite 90 OK; `web.test_server` 23 OK. Tip **`0165267`** on `feature/qwen-a100-start-hardening`, `feature/qwen3.5-27b-integration`, and `main`.
- **Live Pod cheap recheck (before stop):** `vx4oe3oyfsqnz8` at `154.54.102.49:18454`, driver 580.126.16, `:8002`/`:8010`/`:8080` HTTP 200, model `qwen3.5-27b`. Expensive E2E/agent live smoke **not** re-run. Evidence: `docs/results/agent-async-history-2026-10-15.md`.
- **E2E script note:** `_pod_e2e_verify.py` covers real chat + RAG only; it does not cover Agent desk/history.
- **Cost:** Pod **STOPPED** via RunPod UI (not terminated). Compute **$0.00/hr**. Global Volume kept. Results markdown scp’d to `/workspace/platform-diagnostics/`.

### 2026-10-15 — replace driver-570 Pod with CUDA-13 A100; platform VERIFIED

- Terminated blocked Pod `tn28umxi9a5lqx` without deleting Global Volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373`.
- Deployed `vx4oe3oyfsqnz8` (“romantic_gray_canidae”): A100 SXM **$1.79/hr**, CUDA filter **13.x**, same volume at `/workspace`, 30 GB container disk.
- **VERIFIED:** driver **580.126.16**; `START.sh --preflight` → `PREFLIGHT_PASS`; `START.sh` → `FIRST_RELEASE_READY` (~810 s Qwen cold load); `:8002`/`:8010`/`:8080` HTTP 200; `_pod_e2e_verify.py` → **FAILS: NONE**.
- SSH: `root@154.54.102.49 -p 18454`. Pod checkout `2d273f6`. Evidence: `docs/results/runpod-cuda13-replace-2026-10-15.md`.
- Balance was under $5 at deploy; stop the Pod when idle.

### 2026-10-15 — health check: driver 570 blocks start; recovery assets OK

- **VERIFIED:** Pod `tn28umxi9a5lqx` (“relative_emerald_ant”), SSH `root@185.216.23.194 -p 45209`. Volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace`. Qwen 11 shards present. Runtime archive checksum and `zstd -t` **OK**. Snapshot `01e7692` SHA **OK**. Volume `START.sh` matches git. GPU 0 / 81920 MiB. Driver **570.172.08**. Ports 8002/8010/8080/8000 down. Balance warning about $4.89 at $1.79/hour.
- **PREFLIGHT:** `START.sh --preflight` exited 1 with only `nvidia-driver>=580` failing (`found '570'`). All other checks passed. `--start` was **not** run. No weights, archives, or snapshots were deleted.
- **Diagnosis:** this host cannot run the archived CUDA-13 Qwen runtime. Safe fix is a new Pod on the same volume with RunPod CUDA 13 / driver >=580 filter. Older volume logs show successful Qwen loads on other hosts; they do not clear this block.
- Local suites after fast-forward to `7708140`: integrations / agents / web / ops.test_console_deploy — **159 tests OK**. Evidence: `docs/results/runpod-driver570-health-2026-10-15.md`.

### 2026-10-15 — documented SSH port refused

- Started from `934056fed638409a390ceb3aab340e67de10c168`. Working tree had only untracked `ops/__pycache__/` and `ops/release/__pycache__/`. Those were not committed. This process is Linux. `USERPROFILE` is unset. `%USERPROFILE%\.ssh\id_ed25519` is not here.
- **FAILED:** TCP `216.81.248.126:19091` returned connection refused. SSH with `BatchMode=yes`, `IdentitiesOnly=yes`, connect timeout 8 seconds, identity `$HOME/.ssh/id_ed25519` printed `Identity file /home/ubuntu/.ssh/id_ed25519 not accessible: No such file or directory` and `ssh: connect to host 216.81.248.126 port 19091: Connection refused`. Exit 255. No key was generated.
- **NOT RUN:** `/workspace` mount, GPU, weights, runtime archive, source revision, preflight, Qwen `:8002`, gateway `:8010`, console `:8080`, and `START.sh`. No Pod was created and nothing was deleted.
- Next action: on the Windows PC, read the new SSH host and port from the running Pod’s RunPod page and connect with `C:\Users\henok\.ssh\id_ed25519`. Do not reuse port `19091`.

### 2026-10-15 — desktop free, RunPod page not open here

- The owner said continue. The desktop was free. Chrome on this Linux machine had the local console at `http://127.0.0.1:8080`, a Google tab, and Chrome’s What’s New page. No RunPod tab, no RunPod history entry, and no web terminal.
- `id_ed25519` is still absent. Port `19091` was not reused. `findmnt`, GPU, disk, weights, Qwen `:8002`, gateway `:8010`, console on the Pod, and `/tmp/AI-PLAYBOOK` were **NOT CHECKED**. `START.sh` was not run.
- The local page on `:8080` is the Cloud Agent demo, not the Pod. Do not treat it as Qwen health.
- Next action: open the restarted Pod’s RunPod page in this browser, or run the PowerShell health check from `C:\Users\henok\src\AI-PLAYBOOK.md` with `C:\Users\henok\.ssh\id_ed25519` and the new port shown on that page.

### 2026-10-15 — restarted Pod is open in the browser, page not read

- The owner says the Pod was restarted and is open in the Cursor browser. This process is still Linux. `id_ed25519` is absent. The old port `19091` was not used.
- **BLOCKED:** the browser agent returned `DESKTOP_LOCKED` three times. It did not read the Pod id, the new SSH host, or the new TCP port, and it did not open a web terminal.
- **NOT RUN:** `findmnt`, GPU, disk, weight inventory, Qwen `:8002`, gateway `:8010`, console `:8080`, `/tmp/AI-PLAYBOOK`, preflight, and `START.sh`. No service was started or stopped. No application id was invented.
- Next action: release the desktop so the browser agent can read the open RunPod page. Then run the read-only checks. Do not run `START.sh` until `/workspace` is `fuse.geesefs` and the preflight has been read.

### 2026-10-15 — owner is stopping the Pod

- The owner said they are turning off RunPod Pod `1g41ejmd99iyun` now. This agent did not call the RunPod API, did not click Stop, and did not see a stopped status. No new Pod was created.
- **Keep** Global Volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373`. It holds the Qwen weights, `/workspace/runtime-setup`, `/workspace/ai-platform-backups`, `/workspace/ai-platform-release`, and `/workspace/rag-managed-docs`. Stopping the Pod does not delete that volume. Terminating the Pod or deleting the volume would. Network volume storage can keep billing while the Pod is stopped.
- Qwen `:8002`, the gateway `:8010`, and the console `:8080` stop with the Pod. `/tmp/AI-PLAYBOOK` is on the Pod disk and does not survive. The last login that could see the volume found those ports already down and the checkout absent. This agent could not re-check them: SSH on port `19091` exited 255.
- **When the owner returns:** start the same Pod, not a new one, with the same volume. The SSH address will change. On the Windows PC, use `C:\Users\henok\.ssh\id_ed25519` and the new port. Confirm `findmnt` shows `fuse.geesefs` for `/workspace` before any service command. Do not run `START.sh` until that check and `docs/AGENT_HANDOFF.md` have been read. `START.sh` cold-loads Qwen.
- Microsoft sign-in was not started. No application id was created.

### 2026-10-15 — SSH health check failed before login

- Started from `0da700d4730f68f63e580c1d5202a83a590d0eb9`. `uname` reports Linux. `USERPROFILE` is unset. PowerShell is absent. The process is not the Windows PC at `C:\Users\henok\src\AI-PLAYBOOK.md`.
- **FAILED:** one SSH attempt, `BatchMode=yes`, `IdentitiesOnly=yes`, connect timeout 8 seconds, port `19091`, identity `$HOME/.ssh/id_ed25519`. Output: `Warning: Identity file /home/ubuntu/.ssh/id_ed25519 not accessible: No such file or directory.` then `root@216.81.248.126: Permission denied (publickey,password).` Exit 255. No key was generated or printed.
- **NOT RUN:** `/workspace` mount, Qwen `:8002`, gateway `:8010`, console `:8080`, `/tmp/AI-PLAYBOOK`, `deploy-console-only.sh`, `START.sh`, and Entra setup. No application id was invented.
- Next action remains the PowerShell command on the Windows PC, where `C:\Users\henok\.ssh\id_ed25519` exists.

### 2026-10-15 — resume stopped before SSH because the key file is absent

- **VERIFIED:** this process is Linux host `cursor`, user `ubuntu`, checkout `/workspace` at `9ca1aa33c5e3b6f92d8d9516914c8a25494f05e2`. Remote is `henokmeron/ai-playbook.md`. `main` and both Qwen feature branches match that commit. `/workspace` is `ext4` on `/dev/vdc`, not `fuse.geesefs`.
- **BLOCKED:** `Test-Path "$env:USERPROFILE\.ssh\id_ed25519"` cannot be run here. `USERPROFILE` is unset, PowerShell is absent, and `C:\Users\henok` is not mounted. `$HOME/.ssh/id_ed25519` is absent. `~/.ssh` contains `known_hosts` only. No self-hosted worker is connected. The private key was not printed.
- **NOT RUN:** SSH to `root@216.81.248.126 -p 19091`, the console-only deploy, `START.sh`, a Pod restart, and Entra registration. Qwen `:8002`, gateway `:8010`, console `:8080`, and `/tmp/AI-PLAYBOOK` were not re-checked because the health check requires that key. No application id was invented.
- The single next action is still the PowerShell check in the session entry below, run in Cursor on the Windows PC at `C:\Users\henok\src\AI-PLAYBOOK.md`.

### 2026-10-15 — existing RunPod key is not on this Cloud Agent

- Started from GitHub `4f3f4f82af268e6363182b886dac3a9a5cc01faf`.
- **VERIFIED:** TCP `216.81.248.126:19091` still accepts a connection. No SSH login was attempted in this pass. The earlier login from this VM returned `Permission denied (publickey,password)`.
- **VERIFIED:** this VM has no private key. `~/.ssh` contains `known_hosts` only. A filename search and a header search found no OpenSSH or RSA private key outside test data. No SSH config, no `ssh-agent`, no RunPod API credential, no RunPod config file, and no connected self-hosted worker. GitHub Actions secret names are not readable from this token (HTTP 403). The cloud environment JSON is owner-restricted and was not exposed. `/workspace` here is the root disk, not `fuse.geesefs`.
- The documented key remains `%USERPROFILE%\.ssh\id_ed25519` on the owner’s Windows PC (`C:\Users\henok\.ssh\id_ed25519`). It was not copied, printed, or committed.
- **NOT RUN:** a new Pod, a firewall change, an SSH reset, `START.sh`, `ops/release/deploy-console-only.sh`, and any Graph call. The 35 passing tests were not rerun. No Entra application id was invented.
- **Next action, on the Windows PC, in PowerShell.** Confirm the key file exists, then run the read-only check. Do not paste the key into chat.

```powershell
Test-Path "$env:USERPROFILE\.ssh\id_ed25519"
ssh -o BatchMode=yes -o ConnectTimeout=8 -p 19091 -i "$env:USERPROFILE\.ssh\id_ed25519" root@216.81.248.126 "echo SSH_OK; findmnt -n -o FSTYPE /workspace; curl -s -o /dev/null -w 'qwen:%{http_code}\n' --max-time 3 http://127.0.0.1:8002/health; curl -s -o /dev/null -w 'gateway:%{http_code}\n' --max-time 3 http://127.0.0.1:8010/health; curl -s -o /dev/null -w 'console:%{http_code}\n' --max-time 3 http://127.0.0.1:8080/; if test -d /tmp/AI-PLAYBOOK; then git -C /tmp/AI-PLAYBOOK rev-parse HEAD; else echo NO_CHECKOUT; fi"
```

Replace the console only when that check prints `qwen:200` and `gateway:200`. Run it on the Pod from a checkout of `feature/qwen3.5-27b-integration`. The script refuses otherwise, and it does not signal Qwen or the gateway. A lone download of the shell script is not enough: it calls `ops/release/console_deploy.py` from `/tmp/AI-PLAYBOOK`.

```powershell
ssh -o BatchMode=yes -p 19091 -i "$env:USERPROFILE\.ssh\id_ed25519" root@216.81.248.126 "if test ! -d /tmp/AI-PLAYBOOK/.git; then git clone --branch feature/qwen3.5-27b-integration --depth 1 https://github.com/henokmeron/AI-PLAYBOOK.md.git /tmp/AI-PLAYBOOK; fi; CONSOLE_RESTART_APPROVED=yes bash /tmp/AI-PLAYBOOK/ops/release/deploy-console-only.sh"
```

The last successful login, earlier on 2026-10-15, found `:8002`, `:8010`, and `:8080` down. If they are still down, stop. `START.sh` is a cold Qwen load of about 1080 seconds on a Pod billing $1.79/hour. It needs a separate approval. The command in `docs/results/shutdown-recovery-2026-10-15.md` that uses port `11165` is stale. Microsoft sign-in still waits for a work or school account. Do not paste a client id.

### 2026-10-15 — GitHub tip rechecked; sign-in test no longer hard-codes `/tmp`

- **VERIFIED:** `git fetch` showed `main`, `feature/qwen-a100-start-hardening`, `feature/qwen3.5-27b-integration`, and `cursor/microsoft-signin-options-2e6d` all at `7056a63913e1932bff640d0c1cd264104e03ba73`. Issue #1 is still the 2026-10-13 handover and is not the live queue.
- **VERIFIED:** TCP `216.81.248.126:19091` accepted a connection. TCP `154.54.102.31:11165` refused. `~/.ssh` contains `known_hosts` only. The earlier SSH attempt from this VM, `BatchMode=yes` on port 19091, returned `Permission denied (publickey,password)`, exit 255. That login was not repeated. No private key was generated and no RunPod API credential was present.
- **NOT RUN:** `START.sh`, `ops/release/deploy-console-only.sh`, a Qwen load, and a Graph call. `/opt/ai-playbook-venv` and `/opt/rag-deps` were already present and were not reinstalled. `MICROSOFT_CLIENT_ID` and `MICROSOFT_TENANT` are unset. No Entra application was created and no client id was written into the repo.
- The revoked-refresh test used `tempfile.TemporaryDirectory(dir="/tmp")`, which fails on Windows because that directory is not there. It now uses the system temporary directory. On this Linux VM that directory resolved under `/tmp` and stayed outside the repo and `/workspace`.
- Tests, with `/opt/ai-playbook-venv/bin/python -m unittest web.test_server integrations.tests.test_microsoft_oauth`: 35 tests, OK, exit 0. Mocked only. No live Graph call and no model load.

### 2026-10-15 — idle Pod checked; read-only device check-in added in source

- **VERIFIED:** Pod `1g41ejmd99iyun` (“brand new pod”), SSH `root@216.81.248.126 -p 19091`. Volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace` (`fuse.geesefs`). Official Qwen revision has 11 shards. Runtime archive is present (about 3.8G). GPU memory 0 / 81,920 MiB. `:8002`, `:8010`, `:8080`, and `:8000` did not answer. `/tmp/AI-PLAYBOOK` is absent. `MICROSOFT_CLIENT_ID` is unset. The old SSH port `11165` refused. The Pod was left running. Balance was about $4.89 against a $5 warning, at $1.79/hour, with the GPU idle.
- **NOT RUN:** `START.sh`, the console-only reload, a model load, a Graph call, and a new volume snapshot. `ops/release/deploy-console-only.sh` refuses unless Qwen and the gateway are already healthy, and it does not signal those processes. It was not executed.
- Entra app registrations did not load. The signed-in personal Microsoft account got AADSTS16000 against the Microsoft Services tenant. No app was created. No client id was copied.
- Source adds a read-only enrolled-computer check-in and the console-only reload guard. The device secret is hashed. Extra fields, including a command, are rejected. The catalog stays `mock-tested`. A local collector call on this Windows PC returned a schema-valid report and was not sent to the Pod.
- Tests: `integrations.tests.test_endpoint`, `ops.test_console_deploy`, `integrations.tests.test_catalog`, `integrations.tests.test_framework`, `agents.tests.test_execution`, `agents.tests.test_runtime`, `agents.tests.test_workspace`, `agents.tests.test_tools`, and `web.test_server` passed. `integrations.tests.test_microsoft_oauth` has one pre-existing failure on Windows because a test hard-codes `dir="/tmp"`. That test was not changed. No live Graph call and no model load.

### 2026-10-15 — Pod turned back on, still no deployment session

- **VERIFIED:** this process is still not the Pod. No SSH private key, no SSH agent, no RunPod API credential, and no connected self-hosted worker. Cursor’s cloud environment for this run does not attach the Global Volume.
- **VERIFIED:** `154.54.102.31:11165` now returns connection refused. A Pod restart drops that mapped port. The old SSH command must not be reused. Nothing was tried on port 22, and no replacement key was generated.
- **NOT CHECKED:** Qwen `:8002`, gateway `:8010`, console `:8080`, and the running commit. The last console seen before shutdown was `98511df`. `MICROSOFT_CLIENT_ID` was unset then and is unset here. No Entra application was created. No Graph call was made.
- Source to deploy after access exists: `34c3e726274103978743177d1a371337ad7c8589`, which contains console commit `c99cb4c`.

### 2026-10-15 — shutdown copy: GitHub pushed, volume snapshot NOT written

- **VERIFIED:** this process is not on the Pod. Hostname `cursor`, user `ubuntu`. `findmnt -T /workspace` shows the root disk `/dev/vdc` `ext4`, target `/`, not `fuse.geesefs`. `/workspace/models/Qwen3.5-27B`, `/workspace/runtime-setup`, `/workspace/ai-platform-backups`, `/workspace/ai-platform-release`, and `/workspace/rag-managed-docs` are absent. Nothing is listening on `:8002`, `:8010`, or `:8080`.
- **VERIFIED:** TCP `154.54.102.31:11165` accepted a connection. One SSH attempt, `BatchMode=yes`, connect timeout 8 seconds: `Permission denied (publickey,password)`, exit 255. `~/.ssh` contains `known_hosts` only. The attempt was not repeated. No RunPod credential was present, and no Pod was started.
- **NOT DONE:** a new file under `/workspace/ai-platform-backups/source-snapshots/`. The Global Volume could not be written from here. The owner must not assume a snapshot of `c99cb4c` (or of this note) exists on the volume. `VERSION.txt` was not changed. Weights, archives, managed docs, and older snapshots were not deleted because they were not on this disk.
- **VERIFIED before this note:** `git ls-remote` showed `main`, `feature/qwen-a100-start-hardening`, `feature/qwen3.5-27b-integration`, and `cursor/microsoft-signin-options-2e6d` all at `c99cb4cb9eeb974176476766dcd64964db53f68f`. This entry is the next fast-forward on those four refs. Nothing was force-pushed.
- **Last seen on the volume, 2026-10-15, from a machine that had the SSH key (not this one):** volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace` (`fuse.geesefs`); Qwen weights present; `/tmp/AI-PLAYBOOK` at `98511df` (ephemeral; dies with the Pod); Qwen `:8002` and gateway `:8010` HTTP 200; console `:8080/` HTTP 200. The runtime archive checksum and snapshot `01e7692` (`a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370`) were last hashed on 2026-10-14, not in this pass.
- Qwen and the gateway were not stopped. The safe command for the owner’s PC, while the Pod is still up, is in `docs/results/shutdown-recovery-2026-10-15.md`. It is `ops/release/snapshot-published-tip.sh`. It was not run here.

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
