# First-release recovery (RunPod-first, beginner guide)

This is the **standalone first release** of the AI platform. It runs on RunPod only.
Azure is **not required**. Azure docs remain as an optional future migration plan.

## What you have

Think of four pieces that work together:

1. **Qwen model (the brain)** — answers chat and Document Q&A. Lives as large files on the Global Volume.
2. **Gateway (the front door)** — authenticated API on the Pod (`127.0.0.1:8010`). Talks to Qwen.
3. **Console (the website)** — simple browser UI on the Pod (`127.0.0.1:8080`). You reach it through an SSH tunnel.
4. **Document Q&A** — upload business files, ask questions, delete them. Stored under `/workspace/rag-managed-docs`.

Gemma may still be stored on the volume as an **optional** second model. Normal day-to-day use does **not** need Gemma.

## Persistent vs temporary

| Lives on Global Volume `/workspace` (kept when Pod stops) | Temporary on the Pod (`/tmp`, lost on recreate) |
| --- | --- |
| Qwen weights under `/workspace/models/Qwen3.5-27B/...` | Runnable Python env `/tmp/vllm-qwen-env` |
| Optional Gemma weights | Git checkout `/tmp/AI-PLAYBOOK` |
| Runtime archive `…/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` | API key file `/tmp/platform-gateway.key` |
| Launcher `/workspace/ai-platform-release/` | Running processes (vLLM, gateway, console) |
| Managed docs `/workspace/rag-managed-docs` | |

**Important:** do not unzip the runtime onto `/workspace`. Always restore into `/tmp`.

## Start after a Pod restart

1. Start the same RunPod Pod with the **same Global Volume** mounted at `/workspace`.
2. Confirm NVIDIA driver is **580 or newer** (`nvidia-smi`).
3. SSH into the Pod (IP and TCP port come from RunPod Connect; they can change).
4. Run:

```bash
bash /workspace/ai-platform-release/START.sh
```

Or check without starting:

```bash
bash /tmp/AI-PLAYBOOK/ops/start-first-release.sh --check
# if the repo is not cloned yet:
git clone --branch feature/qwen3.5-27b-integration --single-branch \
  https://github.com/henokmeron/AI-PLAYBOOK.md.git /tmp/AI-PLAYBOOK
bash /tmp/AI-PLAYBOOK/ops/start-first-release.sh --check
```

Re-running start is safe: healthy services on `:8002` / `:8010` / `:8080` are reused (no duplicate stack).

## Open the console in your browser

Services listen on the Pod’s localhost only. On your laptop, keep this tunnel open:

```bash
ssh -N -L 18080:127.0.0.1:8080 -p <tcp-port> -i <your-ssh-key> root@<pod-ip>
```

Then open: `http://127.0.0.1:18080`

If you see `ERR_CONNECTION_REFUSED`, the tunnel is not running (or the Pod IP/port changed).

## Stop compute without losing files

- **Stop / terminate the Pod** in RunPod to stop **GPU hourly charges**.
- **Keep the Global Volume** attached/retained so weights, archives, docs and the release folder stay.
- Persistent storage may still incur a smaller storage charge; that is separate from GPU compute.
- Do **not** delete the Global Volume unless you intend to destroy the platform data.
- Do **not** delete Azure resources for this task; Azure is unused by the first-release runtime.

## Model selection

- Default model ID: `qwen3.5-27b` (revision `fc05daec18b0a78c049392ed2e771dde82bdf654`).
- Choosing Gemma while Qwen is loaded returns a clear **HTTP 409** (not a silent swap).
- Only one GPU model at a time. To switch, use `docs/one-gpu-model-switch.md` / `ops/switch-gpu-model.sh`.

## Ports (first release)

| Service | Port |
| --- | --- |
| Qwen vLLM | `8002` |
| Gateway | `8010` |
| Console | `8080` |

## Complete vs optional

| Feature | Status |
| --- | --- |
| Chat via console → gateway → Qwen | Complete for first release |
| Document upload / ask / delete | Complete for first release |
| Model catalogue + unavailable-model response | Complete for first release |
| One-command volume start + archive restore | Complete for first release |
| Vision / tool calling / long context >8192 | Optional / experimental |
| Azure backup or Azure GPU hosting | Optional / deferred — not required |

## Failure rollback (safe)

- Startup failures do **not** delete `/workspace` weights or archives.
- If restore fails: check `SHA256SUMS` under `/workspace/runtime-setup/qwen-vllm/`, free `/tmp`, confirm driver ≥580.
- If Qwen fails to start: inspect `/workspace/platform-diagnostics/first-release/qwen-vllm.log` (or `…/complete/`).
- Keep the volume; fix the Pod/driver/disk; run `START.sh` again.

## Fresh-Pod recovery drill

A full “new Pod, empty `/tmp`, restore from volume only” drill is marked in acceptance reports as **VERIFIED** when archives/checksums and idempotent start are confirmed on a live volume-backed Pod, or **NOT TESTED** when a second Pod was not provisioned (cost control).
