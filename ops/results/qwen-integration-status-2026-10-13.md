# Qwen integration status (honest answer) — 2026-10-13

**Short answer: partially yes — not fully “the platform.”**

Live recheck (SSH Pod): weights present (11 shards); isolated `:8002` / `:8013` / `:8083` HTTP 200; main `:8010` / `:8080` and Gemma `:8000` down.

## What is working right now

- **Model weights are on the persistent Global Volume** at `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654` (11 shards + manifests). Survives Pod stop/restart while volume `cmv2p5m0d000007jk9o3931ea` stays attached.
- **Isolated AI stack validated and still up** (prior smoke `QWEN_OK`; live recheck healthy):
  - Inference: `127.0.0.1:8002`
  - Gateway: `127.0.0.1:8013`
  - Console: `127.0.0.1:8083`
- Related evidence: `ops/results/qwen-live-stack-2026-10-13.md`; queue in `AUTONOMOUS_WORK_QUEUE.md`.

## What is *not* fully integrated

- **Not the production default.** `models/registry.yaml` still has `production: gemma-4-31b-it`. Qwen was never promoted.
- **Main platform ports are not Qwen.** `:8010` / `:8080` left down/untouched on purpose.
- **Not dual-running with Gemma.** One GPU: Qwen owns it; Gemma `:8000` is not running.
- **Runtime env is ephemeral.** `/tmp/vllm-qwen-env` is on local disk, not the Global Volume. Weights persist; the venv may need reinstall after a fresh Pod image unless archived under `/workspace/runtime-setup/qwen-vllm`.
- **Not a VLAN.** Connectivity is Pod loopback + SSH. Persistence is the **Global Volume** (`/workspace`).

## Persistence checklist

| Item | Persistent on Global Volume? |
| --- | --- |
| Qwen model weights | Yes (`/workspace/models/Qwen3.5-27B/…`) |
| Smoke/evidence JSON | Yes (`/workspace/platform-diagnostics/qwen/`) |
| Prior source snapshots | Yes (older commits under `/workspace/ai-platform-backups/…`) |
| Fresh feature-branch snapshot | Not cut yet |
| vLLM Python env | No (lives in `/tmp`) |
| Production gateway wired to Qwen | No |

## Bottom line

Working **isolated** Qwen system; weights **saved on the Global Volume**. Qwen is **not** the fully connected default production Document Q&A / main console path. Cutover needs explicit approval (stop Qwen → restore Gemma, *or* promote Qwen and point main `:8010`/`:8080` at it).
