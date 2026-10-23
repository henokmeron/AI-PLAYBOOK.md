# Agent handoff

Read this file before starting. Append to the log when you finish. Do not delete log entries. Only the Director moves the old CURRENT block into the log and writes a new CURRENT block.

## CURRENT

Updated: 2026-10-23T16:15Z

The owner started a new RunPod pod because the previous A100, gom4ualdk47qrj, could not get its GPU. The new pod is 1jyrnyxpb0n93s, name continuous_green_cephalopod, A100-SXM4-80GB, about $1.80/hr. The existing Global Volume is mounted at /workspace. Weights are at /workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654. SSH for this pod: root@195.26.233.96 port 48443. The console on the owner's PC is http://127.0.0.1:18080/ through an SSH tunnel to the pod's 127.0.0.1:8080. That page is blank until the console process is listening.

Preflight passed at 2026-10-23T14:55:25Z: A100 81920 MiB, driver major 595, ports 8002, 8010, and 8080 free, runtime archive present. START.sh was then started and was restoring the runtime into /tmp/vllm-qwen-env. Source checked out by that start was f38cbef. GitHub main at the last save before this file was cf92c292b31698661658abdd5f90341c444f17ba. Confirm both SHAs before trusting them.

Acceptance was 4/9 overall and 4/8 mandatory. Production is NO-GO. Microsoft content match is not proven. The second Windows PC is not enrolled. Fresh recovery on this same PC does not close that gate. Model weights were not copied.

Next safe work: finish bringing up this pod's console, then continue product work that does not need a new GPU or a weight copy.

## LOG

- 2026-10-23T16:56Z New pod 1jyrnyxpb0n93s: the first Qwen process (pid 3237) was SIGKILLed during shard 1/11. The container OOM counter stayed 0 and dmesg was not permitted. A prefetch relaunch failed with ENOMEM while reading the FUSE checkpoint and was replaced. The default launch, pid 6739, loaded all 11 shards in 1h16m with no extra flag. 8002 /health 200, 8010 /health 200, 8080 /api/status 200. http://127.0.0.1:18080/ returned 200, title Business AI. Weights were not changed.
- 2026-10-23T16:15Z Liaison file created. No product code in this commit. Cursor was starting the new pod. The local page was down because no tunnel was listening; a tunnel to port 18080 was opened from the owner's PC.
- 2026-10-23T18:22Z–18:23Z Model (Agent 3): :8002 acceptance MET on pod 1jyrnyxpb0n93s without restart. vLLM PID 6739 (started 15:34Z) finished GeeseFS safetensor load 11/11 (~1h16m); Application startup complete; :8002 LISTEN. GET http://127.0.0.1:8002/v1/models → HTTP 200 (model id path Qwen3.5-27B/fc05daec…). GET http://127.0.0.1:8010/health → HTTP 200 {"status":"ok","upstream":"ok","model_count":1,"default_model_id":"qwen3.5-27b"}. GET http://127.0.0.1:8080/api/status → HTTP 200 model_alive=true connection=ready upstream=ok. Minimal chat: POST :8002/v1/chat/completions and POST gateway :8010/v1/chat/completions (model qwen3.5-27b) both returned assistant content "pong" (non-error). GPU ~71087 MiB / 81920 MiB at check; source on pod /tmp/AI-PLAYBOOK SHA f38cbefe375b5b2554b7d36461fe6bbbc3c04176. No kill/restart, no weight copy, no pod change. LIVE on pod. Offline RAG PR #9 separate. Next: Director update CURRENT; Endpoint remote Windows second-PC work can proceed per ranked backlog; Console polish unblocked after CURRENT acknowledges :8002 green.
- 2026-10-23T18:23:49Z Verified still green on pod 1jyrnyxpb0n93s, no restart. Commands (on-pod via SSH from owner PC BatchMode key id_ed25519 port 48443): ss -lntp | grep -E ':(8002|8010|8080)' → all three LISTEN (exit 0); curl -sS -m 8 -w 'models_http=%{http_code}' http://127.0.0.1:8002/v1/models → models_http=200 curl_exit=0; curl -sS -m 8 -w 'gw_http=%{http_code}' http://127.0.0.1:8010/health → gw_http=200 body {"status":"ok","upstream":"ok","model_count":1,"default_model_id":"qwen3.5-27b"} curl_exit=0; curl -sS -m 8 -w 'status_http=%{http_code}' http://127.0.0.1:8080/api/status → status_http=200 model_alive=true connection=ready curl_exit=0; curl chat/completions to :8002 → chat_http=200 curl_exit=0 content='pong'; vLLM PID 6739 still same process (elapsed ~02:49:49). Model holding feature work per Director; PR #9 review-only until CURRENT ranks quality; Endpoint/Windows is Founder primary.
