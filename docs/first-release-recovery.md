# First-release recovery (one Global Volume folder)

This is the recoverable first-release path for the AI platform: Qwen3.5-27B primary, Gemma as selectable alternate in the registry, gateway + console, Document Q&A.

It is **not** a zip of a live Python environment. Zipping or unpacking a venv onto the Global Volume FUSE mount does not produce a runnable stack. Persistence is:

1. **Weights + archives + scripts** on `/workspace` (Global Volume)
2. **Live venv + processes** on Pod-local `/tmp` (restored from archives each Pod)

## Durability layout

| Path | Role |
| --- | --- |
| `/workspace/ai-platform-release/START.sh` | One-command entrypoint on the volume |
| `/workspace/ai-platform-release/README.md` | Operator notes (written by bring-up) |
| `/workspace/models/Qwen3.5-27B/...` | Qwen weights |
| `/workspace/gemma-4-31B-it/...` | Gemma weights |
| `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` | Restorable Qwen vLLM env |
| `/workspace/runtime-setup/` | Gemma/other runtime archives as present |
| `/workspace/rag-managed-docs` | Managed Document Q&A storage |
| `/tmp/vllm-qwen-env` | Extracted runnable env (ephemeral) |
| `/tmp/AI-PLAYBOOK` | Git checkout of platform source |

## Pod requirements

- Global Volume mounted at `/workspace`
- NVIDIA driver **≥ 580** (CUDA 13-capable) for the archived Qwen/vLLM wheels
- ≥ ~12 GiB free on local `/tmp` (overlay), preferably more
- One GPU free (do not run Gemma and Qwen together)

## Start after SSH

```bash
bash /workspace/ai-platform-release/START.sh
```

Equivalent from a fresh clone:

```bash
git clone --branch feature/qwen3.5-27b-integration --single-branch \
  https://github.com/henokmeron/AI-PLAYBOOK.md.git /tmp/AI-PLAYBOOK
bash /tmp/AI-PLAYBOOK/ops/start-first-release.sh --start
# or: python3 /tmp/AI-PLAYBOOK/ops/_complete_bringup.py
```

Check:

```bash
bash /tmp/AI-PLAYBOOK/ops/start-first-release.sh --check
```

## Console access

Services bind to `127.0.0.1` only. Tunnel:

```bash
ssh -N -L 18080:127.0.0.1:8080 -p <tcp-port> -i <key> root@<pod-ip>
```

Open `http://127.0.0.1:18080`. Model picker uses `/api/platform/models`. Selecting Gemma while Qwen is the live upstream returns HTTP 409 until you switch runtimes (see `docs/one-gpu-model-switch.md`).

## Ports (first release)

| Service | Port |
| --- | --- |
| Qwen vLLM | `8002` |
| Platform gateway | `8010` |
| Web console | `8080` |

## Transfer / replicate

To move the platform to a new Pod with the same Global Volume:

1. Attach the same volume at `/workspace`
2. Confirm driver ≥ 580 and free `/tmp`
3. Run `bash /workspace/ai-platform-release/START.sh`

To seed a new volume: copy weights + `runtime-setup/` archives + `ai-platform-release/` scripts (or re-clone git and re-archive with `ops/archive-qwen-runtime.sh` after a successful install). Do not treat a zip of `/tmp/vllm-qwen-env` left on FUSE as the runnable artifact—use the `tar.zst` archive + restore script.

## Evidence

Bring-up writes `/workspace/platform-diagnostics/complete/complete-e2e.json` (chat + models + Document Q&A upload/ask/delete).
