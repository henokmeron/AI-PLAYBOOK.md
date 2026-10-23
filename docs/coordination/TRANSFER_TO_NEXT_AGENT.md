# Transfer to the next agent

Read this file before any other work. Then read `docs/coordination/AGENT_HANDOFF.md` and `docs/coordination/BOT_ROSTER.md`. Do not start by exploring at random. The owner is opening a new chat so this session can be continued without losing the path that took all day to reach.

Updated: 2026-10-23 22:40 UK. GitHub `main` at the start of this file was `e8f966534a7f7d5b8409793bbdbede19596a0e78`. This PC's `git rev-parse HEAD` before the durable-state commit was `f14d3bb6dfe62ded38dde103d80369b89689a6cd`, and that commit was `origin/main`. Confirm with `git rev-parse HEAD` before trusting either SHA.

The acceptance board was recalculated. It is 3/9 live and 3/8 mandatory, production NO-GO. Do not repeat the older 4/9 figure. Deployment parity is one of the gates that failed that recalculation.

Operator hashes and the device list now have checksummed volume mirrors in the working tree. The pod does not have that code until `main` is fast-forwarded there and the console is reloaded. Qwen stays up. See `docs/results/durable-console-state-2026-10-23.md`.

## Urgency and the job

This is urgent. The owner has already paid for the struggle of getting a second Windows laptop enrolled and a model loaded. The next agent must make advance progress in the same session, not write another plan and stop.

The product goal is a copy that can be stood up again from what is already saved. Code is on GitHub. A runtime archive is on the volume. Weights stay on that same volume. A release archive is on this PC. The next agent saves the next reproducible piece the same way: versioned, checksummed, and pushed, before calling the step done.

Be effective. One real gap, tested, committed, and pushed, is progress. A score change without new evidence is not.

Be wise about cost. The running GPU is about $1.80 per hour. The volume is about $11.34 per month. Do not create a second pod, start the old H100, start Blackwell, copy the 52 GB weights, or add paid Azure resources unless the owner has approved that exact spend in this file or in the handoff log. Low RunPod balance has already been visible. Do not add funds unless asked.

Think past the next hour. The business needs an architecture that still works after this pod is stopped: saved source, saved runtime, saved operator state, a second computer that can check in again, and a written cost for anything that is not already paid for. Quick fixes that live only in `/tmp` or only in a chat are how this platform gets lost.

## What "start within seconds" means

The owner wants a start that is replicable and fast. Treat that as the design target. Do not report that it is already true.

Measured fact: restoring the code and the runtime archive is the fast part. Loading Qwen weights is not seconds. Historical cold loads were 7 to 21 minutes. On this pod the successful load read 11 shards from FUSE and took much longer. The start script waits up to 45 minutes (2,700 seconds). A prefetch load was tried and ran out of memory. Do not promise a few-second GPU start. Do not restart a healthy Qwen to chase a faster load. Do not add `--safetensors-load-strategy=prefetch` unless a later kill proves the default cannot finish.

The long-term way to get a fast return is to keep one known-good pod warm while the owner is working, keep the runtime archive and weights on the volume, and make the console, enrolment, and Microsoft sign-in survive a pod stop. Killing the model to "start clean" throws away the expensive part.

## What is running tonight

Pod `1jyrnyxpb0n93s`, name `continuous_green_cephalopod`, A100-SXM4-80GB, about $1.80/hr. The owner started it. SSH: `root@195.26.233.96` port `48443`. Key on this PC: `C:\Users\henok\.ssh\id_ed25519`. Do not click Stop. Do not start H100 `xx9cjogra5vcwl`. The previous A100 `gom4ualdk47qrj` cannot get a GPU. Leave it.

Global Volume `cmv2p5m0d000007jk9o3931ea` is mounted at `/workspace`. Weights: `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654`. Runtime archive: `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` (about 4.0 GB, vLLM `0.32.0rc1.dev62+g624a5ddaf`, torch `2.13.0+cu126`). Restored runtime runs from `/tmp/vllm-qwen-env`, not `/workspace/vllm-env`.

Last known healthy processes, confirm before acting: Qwen API pid 6739, EngineCore pid 7123, port 8002. Gateway pid 6497, port 8010. Console was reloaded later for enrolment and must be rechecked. Do not start a second vLLM. The first process on this pod, pid 3237, was killed during shard 1 of 11. The default load, pid 6739, is the one that reached health 200.

Next cold start, only when the pod is actually off and the owner wants it on:

```bash
bash /workspace/ai-platform-release/START.sh --preflight
bash /workspace/ai-platform-release/START.sh
```

`/tmp` is the container disk and dies when the pod stops. `/workspace` is the volume and survives. Git checkout on the pod is `/tmp/AI-PLAYBOOK` and is lost on stop. Source of truth is GitHub `main`.

These secrets are on `/tmp` only and were not copied into git: Microsoft token `/tmp/microsoft-365-token.json`, client id `/tmp/microsoft-client-id`, gateway key `/tmp/platform-gateway.key`, endpoint list `/tmp/endpoint-devices.json`, operator accounts `/tmp/console-operators`. After a pod stop, Microsoft sign-in and the gateway key must be created again. An operator backup that did persist is `/workspace/platform-state/operator-backups/20261023T005638542019Z`. There is no supported volume path for the Microsoft token or the gateway key. Do not invent one by copying secrets into the repo.

## Three places, and which window

1. This PC, user `henok`, computer `BANYA-FAMILY-PL`. Repo: `C:\Users\henok\src\AI-PLAYBOOK.md`. This folder contains `integrations` and `.git`. Console URL here: `http://127.0.0.1:18080/` through an SSH tunnel to the pod's `127.0.0.1:8080`. Nothing listens on port 8080 on this PC. `http://127.0.0.1:8080/` here is connection refused.
2. The pod. Linux. Do not treat it as the second Windows computer.
3. The other laptop, Windows user `kokob`, display name Office PC. The parent `C:\Users\kokob\src\AI-PLAYBOOK.md` is not a git checkout and does not contain `integrations`. The package is in `C:\Users\kokob\src\AI-PLAYBOOK.md\AI-PLAYBOOK.md-main`. That inner folder is a downloaded copy, not a clone, so `git pull` fails there too. Python on that laptop is 3.12. The tunnel window must stay open with no password prompt. The website on that laptop is `http://127.0.0.1:8080/`. Commands go in a second PowerShell whose prompt shows the inner folder.

This PC cannot open folders on Kokob-laptop. Ping to `192.168.1.219` failed. Do not hang on `\\Kokob-laptop\C$`.

Git on this PC is not the `git` on PATH. Use:

`C:\Users\henok\AppData\Local\GitHubDesktop\app-3.5.4\resources\app\git\mingw64\bin\git.exe`

with `-C C:\Users\henok\src\AI-PLAYBOOK.md`. Never run git from `C:\Users\henok`. Python here:

`C:\Users\henok\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe`

`git pull` with no branch fails because `main` has no upstream. Use `git pull --ff-only origin main`. Fast-forward `feature/qwen-a100-start-hardening` and `feature/qwen3.5-27b-integration` when pushing `main`. Never force-push, reset, clean, or rewrite git config.

This PC pushes. The Cursor on the other laptop does not push. It only helps with that laptop's console. Grok bots are not this chat. They read `docs/coordination/AGENT_HANDOFF.md` (the ASSIGNMENTS section) and `docs/coordination/BOT_ROSTER.md`. They do not follow `docs/AGENT_HANDOFF.md` for live work. That file still describes pod `gom4ualdk47qrj` and a 4/9 board. They cannot hear this conversation. Leave their jobs in the coordination handoff. Do not download random repair tools.

## Office PC check-in, already done

Device `bead5785f3674aaeb92c189f8c1b5b8c`, display name Office PC, fixture label empty, status enrolled, tenant `local-console`. A report from the inner folder on 23 Oct 2026 was stored. Eight checks, all `ok`, evidence `live_windows`:

- `win.storage.space`: disks=1
- `win.services.inspect`: services=6
- `win.update.inspect`: events=5
- `hw.devices.inventory`: present_count=164, problems=0
- `print.diagnose`: spooler=Running, printers=3
- `net.diagnose`: gateway_ok=True, dns_localhost_ok=True, addresses=4
- `win.events.recurring`: events=8
- `win.startup.inspect`: `status=collected` only

The report also has Windows 10.0.26200, disk free about 167 GB of 255 GB, and memory about 7.9 GB. The worker printed `acceptance_role=not-recorded-as-second-endpoint` and "this computer is not recorded as the second Windows endpoint". That line means the worker does not mark the acceptance gate. The diagnostic was still stored. Do not enrol again. Do not run `reset-password`. Do not enrol `BANYA-FAMILY-PL`. A fixture named `not-the-second-endpoint` does not count.

The startup line is thin because the other laptop's downloaded folder does not contain commit `e8f9665`. That commit keeps boot time, free memory, and CPU in the summary. Getting it onto Office PC means a real git clone or a fresh copy of `main` in a folder that contains `integrations`, then another `report` from that folder. Do not `git pull` from the parent.

Repeat check-in, only in the inner folder, tunnel window left open:

```powershell
cd C:\Users\kokob\src\AI-PLAYBOOK.md\AI-PLAYBOOK.md-main
python -m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file="$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
```

The report is one-way. The laptop does not get a path back into this PC or the pod. Do not print the device secret or an enrolment code. Codes last 600 seconds and work once. A code that starts with `-` must be passed as `--code=<code>`.

Operator sign-in is username `platform-admin`, not an email. The password file is only on this PC, beside the releases folder: `C:\Users\henok\AppData\Local\AI-PLAYBOOK\operator-password.txt`. Do not open it into chat. Do not reset it unless login fails. The website password is not the SSH key and not `root@195.26.233.96`'s password.

## Acceptance, still NO-GO

Do not raise scores by weakening `ops/acceptance_board.py`. Recalculate from `docs/results/acceptance-evidence.json`. Do not copy an old score into a new claim.

Last honest board before the Office PC report was described as 4/9 live and 4/8 mandatory. Recalculated from `docs/results/acceptance-evidence.json` on 2026-10-23: 3/9 live and 3/8 mandatory, production NO-GO. Passing mandatory gates were live health, inference completion, and cited RAG plus abstention. Deployment parity failed against the checkout tip. The Office PC report is real evidence and has not been written into the board. Do not mark `second_endpoint_worker_ok`. The board passes that gate only when a record has `evidence_kind` `live` and `result` `second_endpoint_worker_ok` inside 168 hours. The evidence list is empty. `acceptance_role` returns `not-recorded-as-second-endpoint` when the fixture label is empty, and that function says the run is not recorded evidence. `second_endpoint_status` does not pass the gate. `counts_as_second_endpoint` is false and is not evidence. Mandatory gates still open until proven:

- Live health and deployment parity must be rechecked against the pod's current checkout. A push is not a deploy.
- Inference completion and cited RAG plus abstention were proven on an earlier pod. Reconfirm on this pod before calling them current. Qwen pid 6739 must stay up while you do it.
- Microsoft mailbox content match is not proven. A list was HTTP 200 with count 9. Searches for "the" were HTTP 200 with count 0. Do not search for "the" again. Do not send mail. Do not add scopes. Do not create an Entra app. Power Automate stays NOT TESTED until a real flow succeeds. The owner must supply one harmless phrase that is already in the mailbox. Mail hardening from pull request 10 is on `main` (`docs/coordination/mail-agent-completion-2026-10-23.md`). Its own report says live mailbox is blocked until a browser sign-in. That merge is not `mailbox_content_match_ok`.
- Second Windows endpoint: Office PC has reported. The gate is not marked.
- Blackwell: blocked until the owner names the GPU and accepts the hourly charge and the load time.
- Fresh recovery: a 41/41 run on this same PC does not pass. The gate needs a fresh machine or a new pod.
- Independent weight backup is not mandatory and is not done. One volume is a single point of failure. Copying about 52 GB needs an approved destination and a storage cost. Do not copy until then.

## Long-term work, in order

Do these as architecture, with tests and a saved commit. Do not restart Qwen for them.

1. Enrolment, the device list, and operator accounts. Done on the running pod for this session. Live files stay on `/tmp`. Checksummed mirrors are `/workspace/platform-state/operator-backups/20261023T213720989628Z` and `/workspace/platform-state/endpoint-backups/20261023T213725366204Z`. A restore drill returned 1 administrator and 1 device. Sessions, the gateway key, the Microsoft token, and the client id were not copied. Console pid 34991 was started from `cb920b3a703196eb86cfceaf6974367af90ee462`. Qwen pid 6739 was not restarted. Do not invent a volume path for the token or the gateway key.
2. Give Office PC a real clone of `main`, so the next report includes the startup summary and the next fix does not require a zip. This PC cannot write that disk. The exact PowerShell is in `docs/coordination/office-pc-clone.md`. Wait for the owner to run it.
3. The acceptance board was re-read. The Office PC report was not recorded as `second_endpoint_worker_ok`. The board is 3/9 live and 3/8 mandatory, production NO-GO.
4. Deployment parity was rechecked and was not marked passed. At the console reload, pod HEAD was `cb920b3a703196eb86cfceaf6974367af90ee462` and matched `origin/main`. No `deployed_sha_read` record was added. The gateway and Qwen processes were not reloaded. A later docs commit does not by itself move those processes.
5. Microsoft positive match, only after the owner gives the phrase. Record HTTP status, count, and whether the phrase was present. No subject, no body.
6. The costed decision for a weight copy and for Blackwell is `docs/results/costed-decisions-2026-10-23.md`. Do not buy either.
7. Keep release archives. The last shutdown archive on this PC is `C:\Users\henok\AppData\Local\AI-PLAYBOOK\releases\cf92c292b31698661658abdd5f90341c444f17ba\`. Later commits exist. A new archive is due after the next real commit if the owner is about to stop the pod. Do not stop the pod unless the owner says so.

## Never

- Do not print or commit passwords, tokens, gateway keys, device secrets, mailbox subjects, or mailbox bodies.
- Do not force-push, hard-reset, clean, or discard the owner's files.
- Do not restart healthy Qwen. Do not write or delete `/workspace` weights.
- Do not install drivers, disable firewall or antivirus, reboot, or download an untrusted repair agent.
- Do not run `reset-password` on the other laptop. A short local password there does not change the pod.
- Do not treat this development PC or the Linux pod as the second endpoint.
- Do not mark production GO while a mandatory gate is open.
