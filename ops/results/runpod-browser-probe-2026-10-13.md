# RunPod Cursor-browser probe — 2026-10-13

## Purpose
Validate what the agent can see and do when RunPod is open in Cursor’s built-in Browser (plan: RunPod browser access). Read-only; no Pod deploy; no credit spend.

## Observed in Cursor Browser
- Logged-in RunPod console reachable in tab `glass-browser-c10fc5d7-e953-4a53-8563-5081f201abf9`.
- Starting URL was Deploy (`https://console.runpod.io/deploy`), not a Pod web terminal.
- Navigated to `https://console.runpod.io/pods` (My Pods): no running Pod listed (page briefly empty / no terminal controls).
- Navigated to `https://console.runpod.io/user/storage`: Global Volume **New model container** (`cmv2p5m0d000007jk9o3931ea`) present — **66.4GB stored**, 1,551 objects, Global / Any, ~$5.97/mo. Consistent with preserved `/workspace` Gemma assets.
- Account balance shown as **$-0.23**. Inbox also has prior low-balance warnings. Deploy Pod button was disabled on the deploy form when no GPU selected; starting compute would require added credits and explicit approval.

## SSH check (parallel)
- `216.81.245.29:48480` — TCP connect failed / connection refused (same as prior session).

## What this proves about browser access
| Capability | Result |
| --- | --- |
| See RunPod UI in Cursor Browser | Yes (snapshot + screenshot) |
| Navigate console pages | Yes |
| See Global Volume inventory | Yes |
| Open Pod web terminal / type shell commands | **No** — no running Pod terminal was available |
| Run `nvidia-smi` / health curls on Pod | **Not possible** without a running Pod |
| Deploy new Pod from browser | **Not done** (negative balance + unapproved financial action) |

## Qwen Stage 2 resume status
**Blocked.** Need (1) positive RunPod balance / ability to start the existing Pod with the Global Volume attached, (2) Pod running with web terminal or SSH, (3) approval before stopping Gemma if it is loaded, then `ops/download-qwen3.5-27b.sh` etc. Weights were not downloaded in this probe.

## Main services
Not modified (`:8010` / `:8080` / Gemma). No model restart attempted.
