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

## Start after a Pod restart (or on a new Pod)

1. Start a RunPod Pod with the **same Global Volume** mounted at `/workspace`.
2. SSH into the Pod (IP and TCP port come from RunPod Connect; they change with every new Pod).
3. Check first. This starts nothing and changes nothing:

```bash
bash /workspace/ai-platform-release/START.sh --preflight
```

4. If it prints `PREFLIGHT_PASS`, start the platform:

```bash
bash /workspace/ai-platform-release/START.sh
```

What `START.sh` does, in order:

- Gets the source. It clones `feature/qwen3.5-27b-integration` from GitHub into `/tmp/AI-PLAYBOOK`. If a checkout is already there, it only fast-forwards it, and it leaves alone any checkout with local edits. If GitHub is unreachable, it uses the newest checksum-verified snapshot from `/workspace/ai-platform-backups/source-snapshots/`.
- Repairs ownership. Older launchers left the checkout owned by `nobody`, which made git refuse it with "dubious ownership". `START.sh` resets ownership to the current user automatically.
- Runs the preflight checks (listed below). If any fails, it stops before starting anything.
- Restores the Python runtime from the volume archive into `/tmp/vllm-qwen-env`. It checks the archive first with sha256 and `zstd -t`, extracts into a staging folder, and never writes onto `/workspace`.
- Starts Qwen. Only Qwen ever starts automatically; Gemma is never loaded. It waits up to 45 minutes, because a cold load from the volume took 7–21 minutes in past runs.
- Installs the PDF/XLSX parsers from `/workspace/runtime-setup/rag-wheelhouse` into `/tmp/rag-deps`.
- Starts the gateway and the console.

Re-running is safe. Healthy services on `:8002` / `:8010` / `:8080` are reused, and no duplicate processes are created. A second start launched while one is already running is refused by a lock file.

Status at any time: `bash /workspace/ai-platform-release/START.sh --check`.

### Preflight checks

| Check | Fails when |
| --- | --- |
| `global-volume-mounted` | `/workspace` is not mounted |
| `qwen-weights`, `qwen-runtime-archive`, `rag-parser-wheels` | a required file is missing on the volume |
| `nvidia-driver>=580` | the host driver is older (the archived runtime needs a CUDA 13-capable driver) |
| `gpu-vram>=80GB` | the GPU is smaller than an 80GB-class card |
| `gpu-free-before-start` | more than 2 GiB of GPU memory is already used (for example, Gemma or another vLLM is loaded) |
| `qwen-not-already-starting` | a Qwen process exists but is still loading; wait, then re-run |
| `qwen-on-port-is-qwen` | something on `:8002` answers but is not the expected Qwen revision |
| `gemma-not-loaded` | Gemma is serving on `:8000` |
| `gateway-port`, `console-port` | the port is held by a process that is not a healthy gateway or console |
| `local-disk-for-restore` | less than 12 GiB is free in `/tmp` and the runtime still needs restoring |

## Switching to a cheaper A100 80GB Pod

The release supports **A100 80GB** (PCIe or SXM) as well as H100. When choosing the Pod in RunPod:

- **GPU:** an A100 **80GB** card. A 40GB A100 is too small; preflight `gpu-vram>=80GB` fails.
- **Driver:** use RunPod's **CUDA 13** (or "CUDA version ≥ 13.0") filter so the host driver is 580 or newer. An earlier A100 PCIe Pod had driver 570, and the archived runtime could not use its GPU. Preflight `nvidia-driver>=580` now catches this before anything starts.
- **Volume:** attach the **same Global Volume**. Only choose an A100 that RunPod lets you deploy with this volume attached. Do not create a new volume or copy any weights.
- **Disk:** container disk of 30 GB or more. The runtime restore needs 12 GiB free in `/tmp`.

The launcher chooses the GPU memory setting automatically: `0.90` on 80GB cards and `0.92` on larger cards. Both values were measured on real hardware:

| GPU | gpu-memory-utilization | KV cache | Tokens in cache | Concurrent 8192-token requests |
| --- | --- | --- | --- | --- |
| A100 80GB PCIe (earlier run, same runtime) | 0.90 | 15.33 GiB | 154,202 | 18.8 |
| H100 NVL (current) | 0.92 | 31.34 GiB | 315,151 | 38.5 |

Qwen weights use 50.13 GiB in both cases. Context stays at **8192 tokens** and `--max-num-seqs 256`; longer contexts on A100 are not tested. To override the memory setting, set `QWEN_GPU_MEM_UTIL=0.88` (or another value) before `START.sh`.

Order of operations so you never pay for two Pods or lose the working one:

1. Leave the current Pod running until the A100 is proven. During the overlap, upload or delete documents on only one Pod, because both use the same `/workspace/rag-managed-docs`.
2. Deploy the A100 Pod with the same Global Volume. Run `START.sh --preflight` and then `START.sh`.
3. Check chat and Document Q&A through the console tunnel (`ssh -N -L 18080:127.0.0.1:8080 ...` with the A100's IP and port).
4. Only then stop the H100 Pod.

If the A100 fails preflight on the driver check, stop that A100 Pod and pick another host with the CUDA 13 filter. Nothing on the volume is changed by a failed preflight.

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
- If Qwen fails to start: inspect `/workspace/platform-diagnostics/first-release/qwen-vllm.log`.
- If Qwen is still loading when the start times out, its process keeps running. Re-run `START.sh` later and it will be reused.
- Keep the volume; fix the Pod/driver/disk; run `START.sh` again.
- The previous launcher is kept as `/workspace/ai-platform-release/START.sh.bak-<timestamp>`.

## What has and has not been tested

- **VERIFIED (isolated drill, 2026-10-14, H100 Pod):** fresh GitHub clone; preflight pass and fail cases; real runtime restore from the volume archive into an empty folder; second start reusing everything with no new processes; lock refusing a concurrent start; ownership repair; chat, Document Q&A, PDF and XLSX through a second gateway/console on test ports. Details: `docs/results/a100-switch-readiness-2026-10-14.md`.
- **NOT TESTED:** a cold start on a brand-new Pod, meaning Qwen loading from the volume onto an empty GPU with the new launcher. The drill reused the already-running Qwen, because a second model cannot fit on the same GPU. The first real A100 start is that test.
