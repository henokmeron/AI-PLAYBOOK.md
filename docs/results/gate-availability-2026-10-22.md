# Gate availability — 2026-10-22 (partial, stopped early)

The owner stopped this check early to save credit. Only reads were done. Nothing was provisioned, started, stopped, copied, committed, or pushed. No secret is recorded here.

## Second Windows endpoint: BLOCKED (no second machine found locally); remote checks NOT TESTED

Evidence gathered:

- There are two device stores in the code.
  - The endpoint registry (`integrations/endpoint.py`, `DeviceRegistry.from_env`) uses `ENDPOINT_STATE_FILE`. If that is unset, state is kept in memory only. On the pod, `ops/release/deploy-console-only.sh` defaults it to `/tmp/endpoint-devices.json`, which is pod-local and does not survive a pod stop.
  - The repair device store (`windows_repair/device_store.py`) uses `REPAIR_DEVICE_STATE`, which is read in `web/server.py` and `ops_centre/director.py`.
- On this PC, both `REPAIR_DEVICE_STATE` and `ENDPOINT_STATE_FILE` are unset. `%LOCALAPPDATA%\AI-PLAYBOOK` contains only `releases`, and there is no `device-secret`. A recursive search (depth 3) of LOCALAPPDATA, APPDATA, the user profile, and TEMP found no AI-PLAYBOOK device or endpoint state file. The only matches belonged to Edge, Codex, Docker Desktop, and grokbot.
- The existing asset inventory (`asset-inventory-2026-10-22.md`) records "A second Windows computer: **NOT TESTED**".

NOT TESTED: the pod-side `/tmp/endpoint-devices.json` (the pod is stopped and was not started), Azure VM list, the RunPod browser view, the docs-wide grep for recorded enrolments, and the local temp-directory enrolment rehearsal using this PC as a fixture.

Owner steps to enrol a real second Windows machine. These were read from the code but not rehearsed:

1. On the second machine, install Python 3.11 or newer and a copy of the repo (a release archive or a git clone).
2. Open an SSH tunnel from that machine to the console so the console is reachable at `http://127.0.0.1:8080`. The worker refuses plain HTTP to any non-loopback host and only accepts HTTPS with a verified certificate (`console_origin`).
3. In the signed-in console on loopback, as an operator with `CONNECTORS_MANAGE`, call `POST /api/devices/enrolment`. It returns a one-time `enrolment_code`.
4. On the endpoint, run:
   `python -m integrations.endpoint_worker enrol --console http://127.0.0.1:8080 --code "<one-time-code>" --name "Office PC 2" --token-file "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"`
   This generates the device secret locally (`secrets.token_urlsafe(32)`) and writes it to the token file. It is not printed. Do not paste the secret or the enrolment code into chat, docs, git, or tickets.
5. Then run `python -m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"`.
6. On the pod, set `ENDPOINT_STATE_FILE` to a persistent absolute path. The default under `/tmp` is lost when the pod stops.

## Blackwell live acceptance: BLOCKED (needs approval); browser listing and tests NOT TESTED

Evidence gathered by reading files only:

- `ops/blackwell-runtime.lock` pins vLLM `0.32.0+cu129` (wheel SHA-256 `9918be80…bb50b`), torch `2.13.0+cu129`, Python `>=3.11,<3.15`, CUDA 12.9 or newer, driver major 575 or newer, and compute capability 12 or higher. It rejects torch `2.13.0+cu126`. The cu130 vLLM wheel is absent (it returned HTTP 404 on 2026-10-21).
- `ops/install-qwen-blackwell-env.sh` installs into `/tmp/vllm-qwen-blackwell-env`. It refuses the A100 and Gemma environments and `/workspace`, and it needs at least 20 GiB free, `uv`, `curl`, and `sha256sum`.
- `ops/start-qwen-blackwell.sh` serves on `127.0.0.1:8002` with a 2,700-second readiness timeout. It does not start the gateway or the console.

Command sequence for an approved Blackwell pod with Global Volume `cmv2p5m0d000007jk9o3931ea` attached and the repo at `/tmp/AI-PLAYBOOK`:

```bash
bash /tmp/AI-PLAYBOOK/ops/install-qwen-blackwell-env.sh --install
bash /tmp/AI-PLAYBOOK/ops/start-qwen-blackwell.sh --check
bash /tmp/AI-PLAYBOOK/ops/start-qwen-blackwell.sh --infer
```

NOT TESTED: the RunPod deploy-page GPU list, price, and CUDA filter; the local run of `ops/test_qwen_blackwell_runtime.py`; and install and load time estimates taken from the docs. The approval needed is: which Blackwell GPU (for example RTX PRO 6000 96GB), its price per hour, and up to 45 minutes of model load (the script timeout) plus install time.

## Fresh-environment recovery: NOT TESTED

`wsl -l -v`, `docker version`, and the Windows Sandbox probe were interrupted before they returned, so their results are unknown. A Docker Desktop bugsnag file exists under `%APPDATA%\Docker Desktop`, which suggests Docker Desktop has been installed. That was not verified. No recovery was run.

Coordinator follow-up, 2026-10-22 18:18 UTC (UTC+1 local 19:18): `wsl -l -v` (exit 0) lists only `docker-desktop`, version 2, state Stopped. `docker version` exit 1: the Docker Desktop engine pipe is not running. So a fresh container on this PC is possible at no paid cost once Docker Desktop is started. Recovery is still NOT TESTED. The container would be CPU-only and would not cover the model weights.

## Independent backup: NOT TESTED in this session

No new hashing was done. From `asset-inventory-2026-10-22.md` (earlier the same day, not re-checked): the code exists on GitHub and in local release archives under `%LOCALAPPDATA%\AI-PLAYBOOK\releases\`. The weights (about 52G) and `vllm-qwen-env.tar.zst` are recorded only on Global Volume `cmv2p5m0d000007jk9o3931ea` (126.0 GB, $11.34/mo), with no independent weight backup. The newest two archives were not re-hashed against their sidecars. Destination, cost, and transfer-time estimates were not produced.

Coordinator follow-up, 2026-10-22 18:18 UTC: the newest archive with a `.sha256` sidecar is `758177dfad9c6ddac588debce55ab0729704c8fd`. It re-hashed to `d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82`, which matches the sidecar. The newer archives `00894206…` and `d6d3ac2f…` have no sidecar, so they are unverified. The independent weight backup is still BLOCKED. It needs owner approval of a destination and of the transfer of about 52 GB.
