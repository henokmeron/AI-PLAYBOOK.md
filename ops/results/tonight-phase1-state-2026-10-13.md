# Tonight Phase 1 — real state (2026-10-13)

Evidence: `/workspace/platform-diagnostics/tonight/phase1-state.json`

## Git (local workstation)

| Item | Value |
| --- | --- |
| Branch | `feature/qwen3.5-27b-integration` |
| Commit | `7108fecc559b1d82911630110e1237f26392dbf7` |
| Working tree | Clean of tracked edits; untracked probe/`__pycache__` only (preserved, not committed) |
| Remote | Matches `origin/feature/qwen3.5-27b-integration` at Phase 1 start |

## RunPod Pod

| Item | Value |
| --- | --- |
| Reachable | Yes (SSH) |
| Hostname | `6c310a631353` |
| GPU | NVIDIA A100 80GB PCIe — 81920 MiB total, **71089 MiB used**, 0% util |
| System RAM | ~1.0 Ti total, ~909 Gi available |
| Root/tmp disk | overlay 30G, ~21G free |
| Global Volume | **Mounted** `fuse.geesefs` at `/workspace` (source id `5aac0c77-6fcc-4be9-a112-dfe3890e1373`) |

## Models on Global Volume

| Model | Path | Size | Shards | config/index |
| --- | --- | --- | --- | --- |
| Gemma 4 31B | `/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it` | 59G | 2 | yes/yes |
| Qwen3.5-27B | `/workspace/models/Qwen3.5-27B/fc05daec…` | 52G | 11 | yes/yes |

## Services

| Port | Role | Status |
| --- | --- | --- |
| `:8002` | Qwen vLLM | **up** |
| `:8013` | Isolated Qwen gateway | **up** |
| `:8083` | Isolated Qwen console | **up** |
| `:8000` | Gemma vLLM | down |
| `:8010` | Main gateway | down |
| `:8080` | Main console | down |

## Runtime envs

| Env | Present |
| --- | --- |
| `/tmp/vllm-qwen-env` | yes |
| `/tmp/vllm-clean-env` (Gemma) | **no** on this Pod overlay (recovery archive expected on volume) |

## Prior completions (do not redo unless needed)

- Qwen download + isolated smoke + gateway smoke (2026-10-13) — VERIFIED
- Gemma weights on volume — VERIFIED present
- Production default still Gemma in registry — VERIFIED
