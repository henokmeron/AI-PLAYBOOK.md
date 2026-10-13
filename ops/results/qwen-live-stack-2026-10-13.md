# Qwen3.5-27B live isolated stack (2026-10-13)

## Result
**PASS.** Isolated Qwen download + vLLM serve + smoke + gateway/console validated on RunPod. Production default remains Gemma. Main ports `:8010`/`:8080` were not started or modified.

## Endpoints (loopback on Pod)
| Service | Address | Status |
| --- | --- | --- |
| Qwen vLLM | `127.0.0.1:8002` | HTTP 200 `/v1/models` |
| Isolated gateway | `127.0.0.1:8013` | HTTP 200 `/health` |
| Isolated console | `127.0.0.1:8083` | HTTP 200 `/api/status` |
| Gemma inference | `127.0.0.1:8000` | down (not running; GPU owned by Qwen) |
| Main gateway | `127.0.0.1:8010` | down / untouched |
| Main console | `127.0.0.1:8080` | down / untouched |

## Model
- Path: `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654`
- Shards: **11** (`model.safetensors-*-of-*.safetensors`)
- Env: `/tmp/vllm-qwen-env` (vLLM `0.32.0rc1…`)
- vLLM PID (at validation): `4515`
- Requires `LD_LIBRARY_PATH` covering CUDA 13 libs under the venv `nvidia/` tree

## Smoke excerpts
Direct `:8002` chat/completions → `"content": "QWEN_OK"` (HTTP 200).  
Gateway `:8013` authenticated chat/completions → `"content": "QWEN_OK"` (HTTP 200).

Evidence on volume:
- `/workspace/platform-diagnostics/qwen/smoke-result.json`
- `/workspace/platform-diagnostics/qwen/gateway-smoke-result.json`
- `/workspace/platform-diagnostics/qwen/live-stack-evidence.json`
- `/workspace/platform-diagnostics/qwen/gateway-status.json`

## Global Volume
- Mounted at `/workspace` (attached; pod left running).
- Prior source snapshots present under `/workspace/ai-platform-backups/source-snapshots/` (latest observed include `…861086a…`, `…bd44a9d…`).
- Qwen weights + manifests under `/workspace/models/Qwen3.5-27B/`.
- No RunPod UI “create snapshot” action performed from this session; volume data itself is the live persistence layer.

## Not done / deferred
- Promote Qwen to production default (explicitly not done; `models/registry.yaml` still `production: gemma-4-31b-it`)
- Restore Gemma on `:8000` / main `:8010`/`:8080` after Qwen stop
- Fresh commit-named source snapshot of the feature branch onto the volume
- Azure upload / paid resources
