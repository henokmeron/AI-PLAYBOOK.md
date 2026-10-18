# RunPod replace — CUDA-13 A100 serves Qwen

Date: 2026-10-15. Replaced driver-570 Pod with a CUDA-13 / driver-580 A100 SXM on the same Global Volume.

## Outcome: VERIFIED

| Check | Result |
| --- | --- |
| Old Pod | `tn28umxi9a5lqx` / `relative_emerald_ant` stopped then terminated; Global Volume kept |
| New Pod | `vx4oe3oyfsqnz8` / `romantic_gray_canidae`, A100-SXM4-80GB, **$1.79/hr** |
| CUDA filter | Host advertises **13.0, 13.2** |
| Driver | **580.126.16** |
| SSH (TCP) | `root@154.54.102.49 -p 18454`, key `%USERPROFILE%\.ssh\id_ed25519` |
| Volume | `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace` (`fuse.geesefs`) |
| Preflight | `START.sh --preflight` → **PREFLIGHT_PASS** (driver major 580) |
| Start | `START.sh` → `FIRST_RELEASE_READY` after ~810 s Qwen cold load |
| Health | `:8002` / `:8010` / `:8080` → HTTP **200** |
| E2E | `/tmp/AI-PLAYBOOK/ops/_pod_e2e_verify.py` → **FAILS: NONE** (chat + RAG upload/ask/delete) |
| Commit on Pod | `/tmp/AI-PLAYBOOK` at **`2d273f6`** |
| GPU memory | ~71,091 MiB used after load |

## Non-goals held

- No second concurrent paid Pod.
- No new Global Volume; no weight re-download; no archive deletion.
- No Microsoft Entra registration.
- No Gemma load.

## Balance note

Account was under the $5 warning (~$4.89) at deploy time. Cold start used ~$0.40+ of runway. Prefer stopping the Pod when idle.
