# First-release acceptance — H100 NVL (2026-10-13)

## Environment

- Pod: RunPod H100 NVL (≈94 GiB), driver **580.126.09**
- Global Volume: `/workspace` (`fuse.geesefs`)
- Stack: Qwen3.5-27B on `:8002` → gateway `:8010` → console `:8080`

## Durable start (not a zip)

One-folder volume entrypoint:

```bash
bash /workspace/ai-platform-release/START.sh
```

Layout:

| Path | Role |
| --- | --- |
| `/workspace/ai-platform-release/` | Launcher + ops overlays + critical tree copies |
| `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` | Restorable env (extract to `/tmp` only) |
| `/workspace/models/Qwen3.5-27B/...` | Qwen weights |
| `/tmp/vllm-qwen-env` | Live runnable env |

## Verified E2E (`ops/_pod_e2e_verify.py`)

| Check | Result |
| --- | --- |
| Chat `PLATFORM_OK` via Qwen | PASS |
| `/v1/platform/models` default `qwen3.5-27b` | PASS |
| Console `/api/status` connection `ready` | PASS |
| Console model catalog | PASS |
| Chat request for Gemma while Qwen live | HTTP **409** PASS |
| Document Q&A upload → ask (`CEDAR-RIVER-42`) | PASS |
| Document delete | PASS |
| Ask after empty collection | abstain 200 PASS |

Evidence: `/workspace/platform-diagnostics/complete/manual-e2e.json`

## Fixes landed this session

- `--max-num-seqs 256` (Qwen3.5 Mamba cache vs default 1024)
- `LD_LIBRARY_PATH` wiring in `start-first-release.sh`
- Empty-collection RAG ask returns abstain (not 500)
- Platform models response includes `default_model_id`
- Volume release folder with ops/tree overlays for recovery without relying on a zipped venv

## Operator notes

- Driver must be ≥580 for the archived cu13 Qwen env
- Never extract the venv onto `/workspace`
- Tunnel: `ssh -N -L 18080:127.0.0.1:8080 -p <tcp> -i <key> root@<ip>`
- See `docs/first-release-recovery.md`
