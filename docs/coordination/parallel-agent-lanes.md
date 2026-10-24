# Parallel agent lanes

Updated: 2026-10-24 UK.

Several agents can work at the same time. They do not share a git checkout. Each lane below has its own worktree path under `C:\Users\henok\src` and its own branch. An agent must not checkout the main workspace `C:\Users\henok\src\AI-PLAYBOOK.md` while another agent is in it. Do not switch that folder's branch. Do not merge to main. Do not push main.

Create a free lane with `scripts/new-agent-worktree.ps1`. The script starts the new branch at `origin/main`. It stops if the path exists or the branch exists. It does not merge, push, or enrol.

This file's own checkout is `C:\Users\henok\src\AI-PLAYBOOK-parallel-lanes` on `feature/parallel-agent-lanes`. That checkout is the coordination lane. It is not one of the bot lanes below.

## Existing bot roles

Six bots. A new chat reads `docs/coordination/TRANSFER_TO_NEXT_AGENT.md`, then `docs/coordination/AGENT_HANDOFF.md` and `docs/coordination/BOT_ROSTER.md`. The roster names what each bot is for. The lane table is the only tree that bot may change while another agent is working. Do not follow `docs/AGENT_HANDOFF.md` for live work.

Shared standing limits:

- Do not print or commit passwords, tokens, device secrets, gateway keys, or `__pycache__`.
- Do not force-push, reset, or discard another worker's files.
- Do not edit `ops/acceptance_board.py`. Production stays NO-GO. The board stays 3/9 live and 3/8 mandatory.
- Do not restart Qwen. Do not signal the gateway. Do not copy weights. Do not create a pod.
- Do not SSH. Do not touch a laptop. Do not change device or printer settings. Do not enrol. Do not enrol Office PC `bead5785f3674aaeb92c189f8c1b5b8c` or this development PC, BANYA-FAMILY-PL.
- Do not send mail, add Microsoft scopes, or create an Entra app.

| Bot | Role on the roster | This lane may change | This lane must not |
| --- | --- | --- | --- |
| Director (Agent 1) | Owns priority and the CURRENT section. No application code. Reads the log, names the next safe task, and keeps the acceptance score honest. | `docs/coordination/AGENT_HANDOFF.md`, CURRENT only, and only after the old CURRENT text has been copied into the log | Edit product code, start pods, or mark a gate passed without evidence in the log |
| Console (Agent 2) | Owns `web/`, the operator console, tickets, and document upload/download. Does not change the model server, RAG ranking, or Microsoft scopes. | One dated note under `docs/coordination/` | Any edit under `web/` |
| Model (Agent 3) | Owns `rag/`, `eval/`, `evaluation/`, and document question-answering quality. Measures retrieval, citations, abstention, and truncation. | `eval/rag` offline only, including results under `eval/rag/results/` | Contact the gateway, restart Qwen, or run `eval/rag/run_e2e.py` |
| Endpoint (Agent 4) | Owns `windows_repair/`, the endpoint worker, and the Windows runbook. A pass needs a report from a different physical Windows PC. | Docs only | Any edit under `integrations/` or `windows_repair/`. Enrolment |
| Mail (Agent 5) | Owns the Microsoft mail boundary. Records HTTP status, count, and whether a match was present. Power Automate stays NOT TESTED. | `docs/coordination/mail-positive-match-waiting.md` only | Send mail, store subjects or bodies, or search for the word "the" |
| Liaison (Agent 6) | Owns `docs/coordination/` and records what the group finished. The 00:26 UK assignments also call this seat Integration. This lane does not land or merge. | Append the LOG in `docs/coordination/AGENT_HANDOFF.md` only | Edit CURRENT, delete log entries, or implement product features |
| Repair jobs | Already in use. Not a free bot seat. | Nothing. Leave the existing edit alone. | `integrations/remote_work.py`, `integrations/remote_worker.py`, `windows_repair/safe_fixes.py`, `windows_repair/approval.py` |

## Lane table

Director and Liaison are the one pair that share a file. They must not write `docs/coordination/AGENT_HANDOFF.md` at the same time. Director copies the old CURRENT into the log and then replaces CURRENT. Liaison only appends new LOG lines. Every other pair uses different paths and can run together.

| Lane | Branch | Worktree | State |
| --- | --- | --- | --- |
| Director | `feature/agent-lane-director` | `C:\Users\henok\src\AI-PLAYBOOK-lane-director` | Free. Create it with the script. |
| Console | `feature/agent-lane-console` | `C:\Users\henok\src\AI-PLAYBOOK-lane-console` | Free. Create it with the script. One new dated note only, for example `docs/coordination/console-note-2026-10-24.md`. |
| Model | `feature/agent-lane-model` | `C:\Users\henok\src\AI-PLAYBOOK-lane-model` | Free. Create it with the script. Offline `eval/rag` only. |
| Endpoint | `feature/agent-lane-endpoint` | `C:\Users\henok\src\AI-PLAYBOOK-lane-endpoint` | Free. Create it with the script. A docs note that is not `AGENT_HANDOFF.md` and not `mail-positive-match-waiting.md`. |
| Mail | `feature/agent-lane-mail` | `C:\Users\henok\src\AI-PLAYBOOK-lane-mail` | Already created. Do not add a second mail worktree. |
| Liaison | `feature/agent-lane-liaison` | `C:\Users\henok\src\AI-PLAYBOOK-lane-liaison` | Free. Create it with the script. Append the handoff LOG only. |
| Repair jobs | `feature/agent-lane-repair` | `C:\Users\henok\src\AI-PLAYBOOK-lane-repair` | Already in use. Do not create this worktree. Do not edit the four repair files from any checkout. |

Do not reuse these occupied checkouts:

- `C:\Users\henok\src\AI-PLAYBOOK.md` on `main`. An agent is already in this folder and may merge to main.
- `C:\Users\henok\src\AI-PLAYBOOK-parallel-lanes` on `feature/parallel-agent-lanes`.
- `C:\Users\henok\src\AI-PLAYBOOK-lane-mail` on `feature/agent-lane-mail`.
- `C:\Users\henok\src\AI-PLAYBOOK-device-dashboard` on `feature/device-monitor-dashboard`.
- `C:\Users\henok\src\AI-PLAYBOOK-session-playbook` on `feature/session-playbook`.
- `C:\Users\henok\src\AI-PLAYBOOK-check-breadth` on `feature/windows-check-breadth`.
- `C:\Users\henok\src\AI-PLAYBOOK-driver-health` on `feature/windows-driver-health`.
- `C:\Users\henok\src\AI-PLAYBOOK-remote-it-work` on `feature/remote-it-work`.
- `C:\Users\henok\src\AI-PLAYBOOK-safe-fixes` on `feature/windows-safe-fixes`.

## Create one worktree

Run this from an existing checkout of this repo. Do not run it in a way that checks out `C:\Users\henok\src\AI-PLAYBOOK.md`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\new-agent-worktree.ps1 -Branch feature/agent-lane-console -Path C:\Users\henok\src\AI-PLAYBOOK-lane-console
```

The new branch starts at the fetched `origin/main` and does not track `origin/main`. Push only that lane branch, with no force:

```powershell
git push -u origin feature/agent-lane-console
```

Use the GitHub Desktop git executable, not a `git` found on `PATH`:

`C:\Users\henok\AppData\Local\GitHubDesktop\app-3.5.4\resources\app\git\mingw64\bin\git.exe`
