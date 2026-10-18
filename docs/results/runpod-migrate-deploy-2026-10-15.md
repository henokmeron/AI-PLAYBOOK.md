# RunPod resume after migrate failure — new A100 + tip `a680580`

Date: 2026-10-15.

## What happened

1. Owner approved RunPod migrate for stopped Pod `vx4oe3oyfsqnz8`.
2. `CreatePodMigration` returned **Failed to get mount info for source pod** (`mountInfo: null`).
3. Deployed a **new** A100 SXM Pod on the **same Global Volume** (same recovery path as the earlier CUDA-13 replace). Old Pod left **stopped** (not terminated).

## Live platform (VERIFIED)

| Item | Value |
| --- | --- |
| New Pod | `1cj381fjuujeq7` (“coloured_scarlet_prawn”), A100 SXM **$1.79/hr** |
| Old Pod | `vx4oe3oyfsqnz8` still present, **STOPPED**, $0.00/hr |
| SSH TCP | `root@154.54.102.45 -p 13502`, key `%USERPROFILE%\.ssh\id_ed25519` |
| Also | `ssh 1cj381fjuujeq7-64412092@ssh.runpod.io -i ~/.ssh/id_ed25519` |
| Driver | **580.126.16** |
| Volume | `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace` |
| Source | `/tmp/AI-PLAYBOOK` at **`a680580`** |
| START | `FIRST_RELEASE_READY` after ~730 s Qwen cold load |
| Health | `:8002` / `:8010` / `:8080` HTTP **200** |
| Model | `qwen3.5-27b` |

## Tests (live)

| Check | Result |
| --- | --- |
| `ops/_pod_e2e_verify.py` | **FAILS: NONE** (chat PLATFORM_OK, Gemma 409, RAG upload/ask/delete) |
| Console status | `connection=ready` |
| Console chat | `PONG` via `/api/chat` messages |
| Agent async | calculator → **50**, history lists task |
| Agent cancel | IT-support task → **cancelled** |

## Notes

- Agent queue + IT playbook from `a680580` are live on this Pod.
- Prefer **Stop** the new Pod when idle; keep Global Volume; do not Terminate unless owner says so.
