# Final mission progress (2026-10-13 evening)

## Git

| Item | Value |
| --- | --- |
| Branch | `feature/qwen3.5-27b-integration` |
| Pushed commit (picker + one-click) | `59b0b27` |
| Working tree | Additional install/driver fixes pending next commit |

## Pod inspect (VERIFIED)

| Item | Value |
| --- | --- |
| Pod | `usual_coral_ape` / `jzhsnr5uvolx55` |
| SSH TCP | `216.81.151.54:13774` |
| GPU | A100 80GB PCIe |
| Driver | **570.211.01** (CUDA 12.8) |
| Volume | Global Volume mounted at `/workspace` |
| Weights | Gemma + Qwen present |
| Archives | Gemma + Qwen checksums OK on volume |
| Host torch | `2.8.0+cu128` — CUDA **available** |

## Blocker discovered (VERIFIED)

Extracted Global Volume runtimes (`vllm-clean-env` cu130, archived Qwen nightly needing cudart 13) **do not run** on driver 570:

- Gemma extract: `CUDA available: False` / driver too old for cu130
- Qwen extract + cu13 `LD_LIBRARY_PATH`: `CUDA driver version is insufficient for CUDA runtime version`

Prior successful live Qwen run used a Pod with a newer driver class (~580).

## Mitigation in progress

- Remove incompatible `/tmp` extracts only (archives on `/workspace` preserved)
- Rebuild Qwen env with `ops/_install_qwen_env_cu128.py` against host CUDA 12.8
- Then start first-release stack (`:8002` + `:8010` + `:8080`) + E2E

## Already shipped in git (VERIFIED offline)

- Console model picker (`/api/platform/models`, UI select, explicit model id)
- Registry first-release primary = `qwen3.5-27b`
- `ops/start-first-release.sh` one/two-command bring-up
- Unit tests: 32 OK at picker commit time
