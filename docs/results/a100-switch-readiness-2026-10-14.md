# A100 switch readiness — 2026-10-14

Goal: prepare a safe move from the H100 NVL Pod ($3.19/hr) to an A100 PCIe 80GB Pod ($1.79/hr) on the same Global Volume. The current Pod, its pricing, its live services (`:8002` Qwen, `:8010` gateway, `:8080` console), the volume contents and Azure were not changed. No other Pod was created.

## 1. Defects fixed

| Defect | Fix |
| --- | --- |
| The old volume `START.sh` overlaid `cp -a /workspace/ai-platform-release/{ops,tree}/.` onto the checkout. That made `/tmp/AI-PLAYBOOK` owned by `nobody`, so git then refused it ("dubious ownership"). `git reset --hard ... \|\| true` failures were silently ignored, and the stale overlays could replace newer code. | New canonical `ops/release/START.sh`, kept in Git and installed on the volume by `ops/release/install-to-volume.sh` with a timestamped backup. No overlays. It repairs ownership, uses `safe.directory`, only fast-forwards clean checkouts, and falls back to a checksum-verified volume snapshot when GitHub is unreachable. |
| No startup preflight. A driver-570 host, a busy GPU, Gemma being loaded, or an occupied port were only discovered mid-start. | `start-first-release.sh --preflight`, also run automatically at the beginning of `--start`. Nothing starts if any check fails. |
| No guard against two simultaneous starts. | Non-blocking `flock` per gateway port. |
| Found during the drill: the long-lived gateway/console inherited the lock file descriptor, so every later re-run was refused. | Children start with `9>&-` (commit `ae1e750`). |
| `gpu-memory-utilization` was fixed at 0.92, which is only proven on the H100. | Auto-selected: 0.90 on 80GB cards (proven on an A100 80GB), 0.92 on larger cards. Can be overridden with `QWEN_GPU_MEM_UTIL`. |
| The start called `rag/setup_pypdf.sh` / `setup_openpyxl.sh`, which do not exist, so PDF/XLSX parsers were never installed. | Calls the real `rag/setup_pdf_support.sh` / `setup_xlsx_support.sh` using the Qwen env's Python, and adds `/tmp/rag-deps` to the gateway's `PYTHONPATH`. |
| Qwen readiness timeout was too short for cold loads from the volume (417–1249 s observed). | 2700 s. The wait aborts early if the process dies. |
| Runtime restore could extract over an existing env and did not check free space. | Refuses `/workspace` targets and existing targets. Checks for 12 GiB free, verifies sha256 and `zstd -t`, then extracts into a staging folder and moves it into place. |
| `ops/_complete_bringup.py` regenerated the old buggy `START.sh` and overwrote `VERSION.txt`. | It now installs the canonical launcher, runs the preflight, and uses safe git updates. |

Commits on `feature/qwen-a100-start-hardening`: `6ebab4d`, `ae1e750` and this documentation commit.

## 2. Isolated drill (actual results)

Environment: the current H100 NVL Pod, driver 580.126.09. Drill paths were under `/tmp/drill` (checkout, runtime env, key, diagnostics, parser deps, managed docs), using gateway `:8013` and console `:8083`. The drill reused the live Qwen on `:8002` read-only, because one GPU cannot hold a second 50 GiB model.

| # | Test | Result |
| --- | --- | --- |
| T2 | `START.sh --preflight` with an empty checkout path: fresh clone of the test branch from GitHub, then all 11 checks | **VERIFIED** — PREFLIGHT_PASS |
| T1 | New preflight against the live stack (default ports; read-only) | **VERIFIED** — PREFLIGHT_PASS; healthy services detected as reusable |
| T3 | Negative test: preflight for an empty Qwen port while the GPU is in use (85,999 MiB) | **VERIFIED** — `gpu-free-before-start` FAIL, exit 1, nothing started |
| T4 | `START.sh --start`: real restore of the 10.1 GB archive into an empty folder (checksums, `zstd -t`, extract about 85 s), CUDA probe, parser install, gateway and console started | **VERIFIED** — FIRST_RELEASE_READY |
| T5 | Second `START.sh` while the first was still restoring | **VERIFIED** — refused by the lock, exit 1 |
| T6 | Second `START.sh` after the stack was up | **FAILED** the first time because of the leaked lock descriptor (fixed in `ae1e750`). After the fix: **VERIFIED**. Every service was reused, the process ID set was unchanged, and the children held 0 lock descriptors. |
| T7 | Ownership defect simulated with `chown -R nobody`: plain git refused, `START.sh` repaired it and fast-forwarded | **VERIFIED** — owner root, git works |
| T8 | Unit tests (drill checkout and env, with parsers): models 6, rag 55, RAG conversation 10, console 16 | **VERIFIED** — 87 passed |
| T9 | `_pod_e2e_verify.py` against `:8013`/`:8083`: chat, gateway/console models, console status, Gemma-while-Qwen gives 409, RAG upload/ask/delete, follow-up after delete abstains | **VERIFIED** — 9/9 PASS |
| T10 | PDF and XLSX upload, ask, delete on `:8013` | **VERIFIED** — answers cited the correct values (PDF text; XLSX sheet `Fees`, cell B2) |
| — | Live `:8002`/`:8010`/`:8080` before and after | **VERIFIED** — HTTP 200 throughout; same process IDs (7114, 20209, 17567) |

Afterwards only the drill's gateway and console were stopped. `/tmp/drill` (9.5 GB, Pod-local, disappears with the Pod) was left in place. `/tmp` had 11 GB free.

## 3. A100 80GB compatibility of the launch settings

Evidence comes from an earlier A100 80GB PCIe run with the same archived runtime:

- Weights: 50.13 GiB.
- At `gpu-memory-utilization 0.90`: 15.33 GiB KV cache, 154,202 tokens, 18.82× concurrency for 8192-token requests.
- `--max-num-seqs 256` fits under the Mamba cache-block limit.
- 8192 context fits. **Longer contexts on the A100: NOT TESTED.**
- The new launcher selects 0.90 automatically when the GPU reports less than 90,000 MiB (A100 80GB reports 81,920 MiB).

## 4. Not tested / blocked

- **NOT TESTED:** a cold start on a brand-new Pod (empty GPU, Qwen loading from the volume with the new launcher). The drill could not do this without stopping the live Qwen or paying for a second Pod.
- **NOT TESTED:** A100 with the new launcher. The A100 evidence above comes from the earlier launcher, using identical serve flags and runtime.
- **BLOCKED on such hosts:** A100 hosts with NVIDIA driver 570. The archived runtime cannot use their GPU. Preflight now fails fast with instructions (use RunPod's CUDA 13 filter).
- **Current live stack:** it was started by the old launcher, so its gateway still lacks the PDF/XLSX parsers. It was deliberately not restarted. The next `START.sh` run on a new Pod includes them.
