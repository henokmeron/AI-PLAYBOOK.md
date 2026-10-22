# Agent handoff — read this first

**Every new agent / new chat must read this file before changing or starting anything.**  
**Operator system map (beginner manual):** `docs/SYSTEM_MANUAL.md` — keep that file updated when architecture, paths, or operating steps change.  
**Before you finish a chat, update this file** with what you verified, what you changed, what failed, and what the next agent must not break. Do not delete older sections; add a dated entry at the top of “Session log”.

Last updated: **2026-10-22** (read-only Windows collectors for activation, USB, Wi-Fi, proxy, TLS, browser, permissions, and crash evidence ran on this development PC; full local suite **PASS**. H100 pod `xx9cjogra5vcwl` was inspected and left running. Go-live **NO-GO**.)

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
9. **Mandatory living playbook.** Every significant change is unfinished until matching playbook/docs are updated, verified for accuracy, committed, and pushed with the code. See `PLAYBOOK.md` → **Mandatory living playbook — continuously maintained** (sections A–F).

---

## Current live platform (as of last update)

| Item | Value | Status |
| --- | --- | --- |
| Active test Pod | RunPod `xx9cjogra5vcwl` (“reliable_moccasin_hummingbird”), **H100 NVL**, **$3.20/hr** | **VERIFIED** running on 2026-10-22. Pods list showed one pod, GPU util 0%, memory rings 23% and 89%, disk 20%. `nvidia-smi` reported 85,415 MiB used of 95,830 MiB, driver **595.91.07**. Not stopped, started, resized, or reloaded. |
| Prior Pod | `1cj381fjuujeq7` / `vx4oe3oyfsqnz8` | Gone from console / left alone. Do not recreate extras. |
| SSH (TCP) | `root@216.81.245.55 -p 25839`, key `%USERPROFILE%\.ssh\id_ed25519` | **VERIFIED** read-only on 2026-10-22. The key file is present on this PC. Do not print it. |
| GPU / driver | H100 NVL, **85,415 MiB used** of **95,830 MiB**, driver **595.91.07** | **VERIFIED** 2026-10-22 by `nvidia-smi`. Console GPU util was 0%. |
| Container | PyTorch 2.8.0; runtime in `/tmp/vllm-qwen-env` | Restored from volume archive. |
| Global Volume | Console id `cmv2p5m0d000007jk9o3931ea` (“New model container”), filesystem `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace` (`fuse.geesefs`) | **VERIFIED** 2026-10-22. Storage page: 126.0 GB, 1,794 objects, $11.34/mo. No volume was created or written. |
| Qwen / Gateway / Console | `:8002` / `:8010` / `:8080` | **VERIFIED** 2026-10-22: `:8002/health` 200, `:8010/health` 200, `:8080/` 200, `:8080/api/status` 200. Pod checkout `/tmp/AI-PLAYBOOK` is **`a0e9422145aae4e38025709d1ca88288e42f375b`**, behind GitHub `main`. Do not claim the running console is the latest commit. |
| Other Pod | Older idle/terminated Pods | Leave alone unless user says otherwise |

### Exact volume paths that must remain

- Weights: `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654` (11 shards, ~51.75 GiB on disk; **BF16**, no quantization).
- Runtime archive: `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` (+ `SHA256SUMS`, `vllm-version.txt`).
- RAG wheels: `/workspace/runtime-setup/rag-wheelhouse/`.
- Launcher: `/workspace/ai-platform-release/START.sh` (canonical in git: `ops/release/START.sh`).
- Managed docs: `/workspace/rag-managed-docs`.
- Source snapshot last confirmed **on the volume** is still `01e76922`:  
  `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-runpod-first-01e7692.tar.gz`  
  SHA-256: `a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370` (re-checked against the file and its manifest on 2026-10-14).  
  Older snapshots `083fa58` and `0b49946` were still on the volume then. **No newer snapshot was written on 2026-10-15.** The shutdown pass could not SSH to the Pod. See `docs/results/shutdown-recovery-2026-10-15.md`.

### Git

- **GitHub** feature branches include the Qwen routing work. `main` is fast-forwarded to the same tip and pushed. It is not force-pushed.
- `e1e360f` is the parent of **`c2323238041cea8317d2322e6d16554d0bc967bc`** (Qwen routing). That push is a fast-forward. The `ninja` PATH change itself is **`083fa58`**, already inside `e1e360f`.
- Local checkout is `feature/qwen-a100-start-hardening`. Keep `feature/qwen3.5-27b-integration` on the same commit.
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
