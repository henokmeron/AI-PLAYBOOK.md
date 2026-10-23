# Agent handoff

Read this file before starting. Append to the log when you finish. Do not delete log entries. Only the Director moves the old CURRENT block into the log and writes a new CURRENT block.

## CURRENT

Updated: 2026-10-23 22:40 UK

Durable account and device state is in the working tree and is about to be pushed. Live files stay on `/tmp`. Checksummed mirrors are `/workspace/platform-state/operator-backups/` and `/workspace/platform-state/endpoint-backups/`. Sessions, the gateway key, the Microsoft token, and the Microsoft client id are not mirrored. The pod has not loaded this commit yet. Do not restart Qwen pid 6739. Reload the console only after `origin/main` is fast-forwarded on the pod, by copying that process's environment and command line.

The acceptance board was recalculated from `docs/results/acceptance-evidence.json`. It is 3/9 live and 3/8 mandatory. Production stays NO-GO. Passing mandatory gates: live health, inference completion, cited RAG and abstention. Failing: deployment parity, Microsoft mailbox, second endpoint, Blackwell, fresh recovery. The independent weight backup is optional and has no evidence. Do not quote the older 4/9 figure.

The second-endpoint gate was re-read and was not marked. The board passes only on a live `second_endpoint_worker_ok` record. The evidence list is empty. The worker returns `acceptance_role=not-recorded-as-second-endpoint` for a report with no fixture label, and that function says the run is not recorded evidence. `second_endpoint_status` can say REPORTED and its own text says that does not pass the gate. Office PC device `bead5785f3674aaeb92c189f8c1b5b8c` stays a stored diagnostic. The exact commands for a real clone are in `docs/coordination/office-pc-clone.md`. Do not enrol again.

Weight copy and Blackwell were costed in `docs/results/costed-decisions-2026-10-23.md`. Do not buy either. Do not create a pod. Microsoft positive match still needs a phrase from the owner. Do not search for "the". Do not send mail.

Bots follow ASSIGNMENTS below. Do not mark gates passed.

## ASSIGNMENTS

These jobs are mandatory. Bots must not download random computer-repair tools, driver packs, or third-party agents. The existing endpoint worker is the integration. A library may be added only if it is pinned, tested, and safer than the current code.

- Director: no code. The board is 3/9 and 3/8, NO-GO. Do not mark the second-endpoint gate passed.
- Console: Office PC should show as enrolled with the eight read-only checks. Do not invent a device. Do not show a repair as completed. Do not restart Qwen to pick up the state mirror.
- Model: do not restart Qwen pid 6739. Offline eval only. No weight copy.
- Endpoint: do not enrol this PC. Do not use the parent folder on Office PC. The clone commands are in `docs/coordination/office-pc-clone.md`. Read-only report only, after the owner runs them.
- Mail: do not send mail or add scopes. Do not search for "the". Positive match still needs a phrase the owner confirms. Power Automate stays NOT TESTED.
- Liaison: append the log after each bot finishes. Do not implement features.

## LOG

- 2026-10-23 22:40 UK Cursor on this PC: checksummed volume mirrors for operator hashes and the device list. Local tests exited 0. Board recalculated 3/9 and 3/8, NO-GO. Second-endpoint token was not written. Office PC clone commands and the weight/Blackwell cost note were saved. Qwen was not restarted. The pod had not loaded this commit yet.

### Previous CURRENT (copied 2026-10-23 22:40 UK)

Updated: 2026-10-23 22:15 UK

A new chat must read `docs/coordination/TRANSFER_TO_NEXT_AGENT.md` first. Work is urgent. Save a replicable copy and push it. Do not promise a few-second GPU start. Qwen pid 6739 stays up. Office PC device `bead5785f3674aaeb92c189f8c1b5b8c` reported again from `C:\Users\kokob\src\AI-PLAYBOOK.md\AI-PLAYBOOK.md-main`. The parent folder has no `integrations` and no `.git`. The startup summary is still only `status=collected` because that download does not contain `e8f9665`. Production stays NO-GO. Do not mark the second-endpoint gate until the acceptance board is updated on purpose. Do not reset the operator password. Do not create a pod, copy weights, or send mail.

Bots follow ASSIGNMENTS below. Do not mark gates passed.

- 2026-10-23 22:15 UK Cursor on this PC: wrote `docs/coordination/TRANSFER_TO_NEXT_AGENT.md` for the next chat. Office PC reported again from the inner folder. Startup summary is still thin. Qwen was not restarted. Production stays NO-GO.

### Previous CURRENT (copied 2026-10-23 22:15 UK)

Updated: 2026-10-23 21:25 UK

Office PC is enrolled and has sent a live read-only report. Device id `bead5785f3674aaeb92c189f8c1b5b8c`. Fixture label is empty. Windows 10.0.26200. Eight checks were ok: disk, services, Windows Update events, device inventory (164 present, 0 problems), printers (spooler running, 3 printers), network (gateway and local DNS ok), recurring events (8), and startup. The startup line only said `status=collected` because boot time, memory, and CPU were collected and then left out of the stored summary. That summary gap is fixed in the worker for the next report. The report is one-way: the laptop sends it to the pod. The pod does not open a path back into that laptop. This PC cannot open folders on Kokob-laptop. Model pid 6739 stays up. Production stays NO-GO. Do not mark `second_endpoint_worker_ok` until the acceptance board is updated from this evidence on purpose.

The other laptop must run `python -m integrations.endpoint_worker` from the folder that contains the `integrations` directory. Not from `C:\WINDOWS\System32` and not from the parent of that folder.

Bots follow ASSIGNMENTS below. Do not mark gates passed.

- 2026-10-23 21:25 UK Cursor on this PC: Office PC device bead5785f3674aaeb92c189f8c1b5b8c reported eight live checks, all ok. Startup summary omitted boot, memory, and CPU. The worker summary now keeps those fields. The other laptop's Cursor is not pushing. Kokob-laptop still does not answer a file share. Qwen was not restarted. Production stays NO-GO.

### Previous CURRENT (copied 2026-10-23 evening UK)

Updated: 2026-10-23T16:15Z

The owner started a new RunPod pod because the previous A100, gom4ualdk47qrj, could not get its GPU. The new pod is 1jyrnyxpb0n93s, name continuous_green_cephalopod, A100-SXM4-80GB, about $1.80/hr. The existing Global Volume is mounted at /workspace. Weights are at /workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654. SSH for this pod: root@195.26.233.96 port 48443. The console on the owner's PC is http://127.0.0.1:18080/ through an SSH tunnel to the pod's 127.0.0.1:8080. That page is blank until the console process is listening.

Preflight passed at 2026-10-23T14:55:25Z: A100 81920 MiB, driver major 595, ports 8002, 8010, and 8080 free, runtime archive present. START.sh was then started and was restoring the runtime into /tmp/vllm-qwen-env. Source checked out by that start was f38cbef. GitHub main at the last save before this file was cf92c292b31698661658abdd5f90341c444f17ba. Confirm both SHAs before trusting them.

Acceptance was 4/9 overall and 4/8 mandatory. Production is NO-GO. Microsoft content match is not proven. The second Windows PC is not enrolled. Fresh recovery on this same PC does not close that gate. Model weights were not copied.

Next safe work: finish bringing up this pod's console, then continue product work that does not need a new GPU or a weight copy.

- 2026-10-23 evening UK Director: both laptops are signed into the console. `/tmp/endpoint-devices.json` was absent. NOT ENROLLED. Qwen pid 6739 returned health 200 and was not restarted. Console pid 31078 was still present and was not restarted. Production stays NO-GO.

- 2026-10-23T18:45Z Endpoint: a device report can open a helpdesk ticket. The ticket stores the device id and collection reference. A labelled fixture stays labelled. Execute without approval is still refused. Commit 0f2265c8eb8810baeb973c38e24ec5c753d53fb0. Production stays NO-GO. The second computer is still NOT ENROLLED.
- 2026-10-23T18:43Z Endpoint: a one-time code that starts with a dash is now passed with --code=, and this PC (BANYA-FAMILY-PL) cannot enrol as the second computer. The IT Helpdesk device list shows OS, disk, network, and installed software when a check-in has it. Proposed repairs stay proposals. Tests: integrations.tests.test_endpoint and the device console check passed. Commit d2f1d1d74b9c242892ab9fcb4e3afd272bfe93a5. The console device list returned 401 without a session, and /tmp/endpoint-devices.json was absent. NOT ENROLLED. Qwen was not restarted. Production stays NO-GO.
- 2026-10-23T16:56Z New pod 1jyrnyxpb0n93s: the first Qwen process (pid 3237) was SIGKILLed during shard 1/11. The container OOM counter stayed 0 and dmesg was not permitted. A prefetch relaunch failed with ENOMEM while reading the FUSE checkpoint and was replaced. The default launch, pid 6739, loaded all 11 shards in 1h16m with no extra flag. 8002 /health 200, 8010 /health 200, 8080 /api/status 200. http://127.0.0.1:18080/ returned 200, title Business AI. Weights were not changed.
- 2026-10-23T16:15Z Liaison file created. No product code in this commit. Cursor was starting the new pod. The local page was down because no tunnel was listening; a tunnel to port 18080 was opened from the owner's PC.
