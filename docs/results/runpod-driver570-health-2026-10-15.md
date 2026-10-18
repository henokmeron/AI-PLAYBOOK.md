# RunPod health check — driver 570 blocks start

Date: 2026-10-15. Method: SSH with `%USERPROFILE%\.ssh\id_ed25519`. Nothing was started or deleted.

## Live Pod

| Item | Value |
| --- | --- |
| Name | `relative_emerald_ant` |
| Id | `tn28umxi9a5lqx` |
| GPU | A100-SXM4-80GB, **0 / 81920 MiB** used |
| Driver | **570.172.08** |
| SSH | `root@185.216.23.194 -p 45209` |
| Cost | $1.79/hr; balance warning near $4.89 |
| Old port | `216.81.248.126:19091` refused |

## Volume and recovery

| Check | Result |
| --- | --- |
| Mount | `/workspace` = `fuse.geesefs` volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373` |
| Qwen shards | **11** under revision `fc05daec18b0a78c049392ed2e771dde82bdf654` |
| Runtime archive | Present (~3.8G). `sha256sum -c SHA256SUMS` **OK**. `zstd -t` **OK** |
| RAG wheels | Present (`pypdf`, `openpyxl`, …) |
| Snapshot `01e7692` | SHA-256 `a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370` **OK** |
| Volume `START.sh` | SHA-256 `6059e4c2…` matches git `ops/release/START.sh` |
| `/tmp/AI-PLAYBOOK` | Cloned by preflight to `7708140` on `feature/qwen3.5-27b-integration` |

No model weights, archives, snapshots, or managed docs were deleted.

## Service ports

| Port | Health |
| --- | --- |
| 8002 (Qwen) | not listening |
| 8010 (gateway) | not listening |
| 8080 (console) | not listening |
| 8000 (Gemma) | not listening |

## Preflight

```text
bash /workspace/ai-platform-release/START.sh --preflight
```

Exit **1**. All checks passed except:

```text
FAIL  nvidia-driver>=580  found '570'. Archived runtime needs CUDA-13-capable driver.
```

`START.sh` was **not** run with `--start`. Qwen was not loaded. That refusal is the correct safety behaviour: the archived vLLM needs a CUDA-13-capable host (driver ≥580).

## Older logs on the volume

`/workspace/platform-diagnostics/first-release/qwen-vllm.log` and `complete/qwen-vllm.log` show earlier successful loads on other hosts. They are not evidence that this driver-570 Pod can serve.

## Safe next step

Redeploy the **same** Global Volume on a RunPod host with the CUDA **13** / driver **≥580** filter. Then:

```bash
bash /workspace/ai-platform-release/START.sh --preflight
bash /workspace/ai-platform-release/START.sh
```

Do not re-download weights. Do not unzip the runtime onto `/workspace`.
