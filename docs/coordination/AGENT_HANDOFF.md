# Agent handoff

Read this file before starting. Append to the log when you finish. Do not delete log entries. Only the Director moves the old CURRENT block into the log and writes a new CURRENT block.

## CURRENT

Updated: 2026-10-23T16:15Z

The owner started a new RunPod pod because the previous A100, gom4ualdk47qrj, could not get its GPU. The new pod is 1jyrnyxpb0n93s, name continuous_green_cephalopod, A100-SXM4-80GB, about $1.80/hr. The existing Global Volume is mounted at /workspace. Weights are at /workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654. SSH for this pod: root@195.26.233.96 port 48443. The console on the owner's PC is http://127.0.0.1:18080/ through an SSH tunnel to the pod's 127.0.0.1:8080. That page is blank until the console process is listening.

Preflight passed at 2026-10-23T14:55:25Z: A100 81920 MiB, driver major 595, ports 8002, 8010, and 8080 free, runtime archive present. START.sh was then started and was restoring the runtime into /tmp/vllm-qwen-env. Source checked out by that start was f38cbef. GitHub main at the last save before this file was cf92c292b31698661658abdd5f90341c444f17ba. Confirm both SHAs before trusting them.

Acceptance was 4/9 overall and 4/8 mandatory. Production is NO-GO. Microsoft content match is not proven. The second Windows PC is not enrolled. Fresh recovery on this same PC does not close that gate. Model weights were not copied.

Next safe work: finish bringing up this pod's console, then continue product work that does not need a new GPU or a weight copy.

## LOG

- 2026-10-23T16:15Z Liaison file created. No product code in this commit. Cursor was starting the new pod. The local page was down because no tunnel was listening; a tunnel to port 18080 was opened from the owner's PC.
- 2026-10-23T15:45:20Z Console: operator console bring-up evidence on pod 1jyrnyxpb0n93s (continuous_green_cephalopod). Runtime restore present (/tmp/vllm-qwen-env). Source on pod: /tmp/AI-PLAYBOOK at f38cbefe375b5b2554b7d36461fe6bbbc3c04176. Processes: web/server.py PID 6499 and local_gateway.py PID 6497 (~13m uptime). Ports: 127.0.0.1:8080 LISTEN, 127.0.0.1:8010 LISTEN. On-pod curl: GET http://127.0.0.1:8080/api/status → HTTP 200; GET http://127.0.0.1:8010/health → HTTP 503 (model upstream not ready). Owner PC tunnel ssh -L 18080:127.0.0.1:8080 (BatchMode, key id_ed25519, port 48443) listening; GET http://127.0.0.1:18080/ → HTTP 200 (Business AI HTML); GET http://127.0.0.1:18080/api/status → HTTP 200 (ui=ok, gateway_reachable=true, upstream=unavailable, model_alive=false, runpod_verified=false). vLLM serve PID 6739 still loading safetensors (1/11 shards at log sample; :8002 not LISTEN yet) — not restarted (healthy-process rule). No pod create/resize, no weight copy. Live vs offline: console LIVE through tunnel; model OFFLINE/loading. Files changed: docs/coordination/AGENT_HANDOFF.md (LOG append only). Tests: none (ops evidence). Blocker for chat answers: vLLM weight load in progress on GeeseFS (slow). Next: Director update CURRENT; Model/ops wait for :8002 200 — Console may resume front-end polish after CURRENT acknowledges live console.
