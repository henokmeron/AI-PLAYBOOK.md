# Final mission acceptance — 2026-10-13 (honest)

## Verdict

**Software first-release path is largely complete in Git** (Qwen primary registry, console model picker, one-click start script, recovery archives on Global Volume).  
**Live GPU inference on the newly started Pod is BLOCKED** by NVIDIA **driver 570.211.01** (CUDA 12.8). Current vLLM builds need CUDA-13-capable drivers (~580+).  
**Do not call production complete** until a driver-capable Pod serves chat + Document Q&A end-to-end.

## 1. Branch / commit / push

| Item | Status |
| --- | --- |
| Branch | `feature/qwen3.5-27b-integration` |
| Pushed | `59b0b27` (picker + start-first-release + Qwen primary registry) |
| Follow-up | Driver-gate docs + install helpers committed in the next push |
| Merge to main | **NOT DONE** (needs approval) |

## 2. Models

| Model | Downloaded | Verified on volume | Running now | Live-tested tonight |
| --- | --- | --- | --- | --- |
| Qwen3.5-27B | VERIFIED | VERIFIED | **BLOCKED** (driver) | NOT TESTED on this Pod |
| Gemma 4 31B | VERIFIED | VERIFIED | **BLOCKED** (same driver/vLLM clash) | NOT TESTED on this Pod |

Prior night (older Pod/driver class): Qwen isolated chat+RAG was VERIFIED.

## 3. Console model picker

| Item | Status |
| --- | --- |
| Code + unit tests | VERIFIED (ships in `59b0b27`) |
| Browser E2E on live Pod | **NOT TESTED** (no healthy upstream) |

## 4. Main ports 8000 / 8010 / 8080

| Port | Status |
| --- | --- |
| All | **DOWN / BLOCKED** — vLLM engine core fails on driver 570 |

## 5. Chat / Document Q&A E2E

| Path | Status |
| --- | --- |
| Browser → console → gateway → model | **BLOCKED** tonight |
| Prior isolated Qwen path (previous Pod) | VERIFIED historically |

## 6. Tests

| Suite | Result |
| --- | --- |
| Local unit (registry + web + gateway selection) at picker commit | **32 OK** |
| Live API / browser | **NOT TESTED** (GPU serve failed) |

## 7. Global Volume / snapshots

| Asset | Status |
| --- | --- |
| Mount | VERIFIED `fuse.geesefs` `/workspace` |
| Qwen weights | VERIFIED |
| Gemma weights | VERIFIED |
| Qwen runtime archive | VERIFIED checksums (cu13-era; not usable on driver 570) |
| Gemma runtime archive | VERIFIED checksums (cu130; not usable on driver 570) |
| Source snapshots | `7072cab` / `534a891` present; snapshot `59b0b27` should be cut after push |

## 8. Remaining limitations

- This Pod image/driver cannot run current vLLM (cudart 13 / UVA).
- RAG “all document types” remains the existing loader set (TXT/MD/CSV/HTML/DOCX/PDF/XLSX); no new RAG engine was built tonight (per reuse-only mission).
- One-click start cannot succeed until the host driver is sufficient.

## 9. Can the paid GPU be stopped?

**Yes.** Stop the Pod from RunPod UI. Keep Global Volume attached. No live services are providing value on this host until redeployed on a newer driver.

## 10. Single next action (approval required)

**Stop this Pod and redeploy the same Global Volume on a host/template with NVIDIA driver ≥580 (CUDA 13 capable), then run:**

```bash
bash ops/start-first-release.sh --start
```

After that, verify browser chat + Document Q&A + model picker in one pass.

## Evidence

- `/workspace/platform-diagnostics/final-mission/inspect.json`
- `/workspace/platform-diagnostics/first-release/qwen-vllm.log` (driver insufficient)
- `/workspace/platform-diagnostics/first-release/gemma-vllm.log` (same)
- Git: `ops/start-first-release.sh`, `web/*` picker, `models/registry.yaml`
