# Remote IT work channel, 2026-10-23

## What changed

An enrolled laptop can receive IT work only by dialing out. The server does not scan the network and does not open a shell on an unenrolled host. Orders live in an injected in-memory store. Nothing in this change writes the live device file or `/tmp/endpoint-devices.json`.

State machine: `draft` -> `pending_approval` -> `approved` -> `claimed` -> `succeeded` or `failed`. `refused` is a separate terminal state. Creating an order leaves it pending. A diagnostic result does not approve it. Approval lasts 15 minutes, is single-use, and is bound to the device id, the action id, and the target. `poll_jobs` returns approved jobs for that device id only. `claim_job` consumes the approval. `complete_job` accepts one result; a second call is refused.

`monitor.heartbeat` is liveness only (device id, UTC time, worker version) and an enrolled device may post it without a second approval. Every mutating action requires approval. `execute` returns a plan unless the order is approved and the caller passes `live=True`. Download and install stay plans: no DNS, no HTTP, and no shell. The password for a local user is a handler input. It is not written to the order, the audit, or the worker JSON.

The default live runner performs one allowlisted operation only when `REMOTE_IT_WORK_LIVE=1`. Tests inject a runner and do not call that default. This work never passed `live=True` against this machine.

## Console calls

HTTP is not wired. `require_operator` can guard create and approve, and `_device_bearer` only checks that a Bearer header exists. The public device registry maps a secret to a device by storing a diagnostic, and the repair device store is a different enrolment. `integrations/endpoint.py` was not changed. No backdoor token was added.

The console should call:

- `integrations.remote_work.create_work_order`
- `integrations.remote_work.approve_work_order`
- `integrations.remote_work.poll_jobs`
- `integrations.remote_work.claim_job`
- `integrations.remote_work.complete_job`
- `integrations.remote_work.post_heartbeat` for liveness

The laptop reads a jobs file and does not open a socket:

`python -m integrations.remote_worker poll-once --jobs FILE`

Without `--jobs` it reads stdin. The default result is a plan (`state` `planned`). `--live` is the operator switch on the laptop and still does nothing unless `REMOTE_IT_WORK_LIVE=1`.

## Action ids

- `monitor.heartbeat`
- `repair.service.restart`
- `repair.printer.clear_queue`
- `setup.onboard.local_user`
- `setup.offboard.local_user`
- `change.download` (plan only)
- `change.install` (plan only)
- `change.delete`

## Refusals the tests proved

- Unenrolled device, unknown action, and forbidden actions (`remote.desktop`, `input.keylog`, `persist.startup`, `firewall.disable`, `security.tamper`, `credential.dump`, `change.spread`).
- Reboot, restart-all, a running service, and a service that is not automatic.
- A printer path outside that queue's spool files, and queue names `all` and `*`.
- A password on the work order, and a password in the audit, the stored order, or the worker JSON. The injected runner still receives the sentinel.
- A blank local user, and offboard when `admin_count` is below 2.
- An http URL, a host that is not on the order allowlist, a destination outside the staging directory, a missing sha256, and a URL that carries credentials. Download does not call DNS or HTTP.
- An install source other than `windows-update`, `pnputil`, or `staged-file`, a sha256 that does not match, and a staged file outside the staging directory. Install does not call the runner.
- Drive roots, `Windows\System32`, `Windows\SysWOW64`, `Program Files`, `Program Files (x86)`, a user-profile directory, globs, UNC paths, and a delete whose path is not the approved target.
- Approval expiry at 15 minutes, a second claim, a binding change of device, action, target, or parameters, a second complete, and a complete from another device.
- Heartbeat fields other than device id, UTC time, and worker version.

## What was not run

This branch does not connect to Office PC `bead5785f3674aaeb92c189f8c1b5b8c`. That laptop is not on this network. Nothing enrolled a device, opened SSH, started a tunnel, or ran a worker against a live PC. Qwen, the gateway, and the console were not restarted. Production stays NO-GO. `ops/acceptance_board.py` and `docs/results/acceptance-evidence.json` were not edited.

The owner still has to run the worker on that laptop after this branch is merged. This work did not do that.

## Base and tests

Fetched `origin/main` is `bba59f08d4787e48a01766ff18ca165fc8089175` (`docs: Liaison LOG for PR #15 offline RAG eval land (#22)`). Local `main` was still near `9d979b6`; this branch is based on the fetched tip, not that older checkout.

`python -m unittest integrations.tests.test_remote_work` from this worktree: 26 tests, OK, about 0.025s. The default live runner invocation count stayed 0. A stdin `poll-once` with an empty job list printed `state` `idle` and did not use the network.

## Next

Do not merge this branch from here. Do not push `main`. After merge, the owner runs `python -m integrations.remote_worker poll-once` on the enrolled laptop. Live changes stay off until that operator sets `REMOTE_IT_WORK_LIVE=1` and passes `--live`.
