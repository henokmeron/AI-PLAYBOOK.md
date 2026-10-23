# Remote IT work channel, 2026-10-23

## What changed

An enrolled laptop can receive IT work only by dialing out. The server does not scan the network and does not open a shell on an unenrolled host. Orders live in an injected in-memory store. Nothing in this change writes the live device file at `/tmp/endpoint-devices.json`. The tests use a temporary registry only.

State machine: `draft` -> `pending_approval` -> `approved` -> `claimed` -> `succeeded` or `failed`. `refused` is a separate terminal state. Creating an order leaves it pending. A diagnostic result does not approve it. Approval lasts 15 minutes, is single-use, and is bound to the device id, the action id, and the target. `poll_jobs` returns approved jobs for that device id only. `claim_job` consumes the approval. `complete_job` accepts one result; a second call is refused.

`monitor.heartbeat` posted by an enrolled device is liveness only (device id, UTC time, worker version) and does not need a second approval. A heartbeat work order can also be approved, claimed, and finished. Every mutating action requires approval. `execute` returns a plan unless the order is approved and the caller passes `live=True`. Download, install, and heartbeat call a runner only when that order is claimed and the caller injected the runner. They never use the default live runner. This module does not open a socket and does not start pnputil or Windows Update. The password for a local user is a handler input. It is not written to the order, the audit, or the result JSON.

The default live runner performs one allowlisted operation only when `REMOTE_IT_WORK_LIVE=1`, and it still refuses download, install, and heartbeat. Tests inject a runner and do not call that default. This work never passed `live=True` against this machine, the pod, or Office PC. The success tests pass `live=True` only with a fake runner, and they patch `subprocess.run` and `socket` so a mistake cannot touch this PC.

Office PC `bead5785f3674aaeb92c189f8c1b5b8c` was not contacted.

## Console calls

HTTP is wired on the loopback console. Missing authentication is a refusal.

- `POST /api/remote-work/orders` and `POST /api/remote-work/approve` require an operator session (`require_operator`, permission `connectors:manage`, CSRF). The operator id is the session user. A device secret in the body is refused and is not stored.
- `POST /api/remote-work/poll`, `/claim`, `/complete`, and `/heartbeat` require the existing device bearer check. `DeviceRegistry.authenticated_device_id` compares the stored hash from `integrations/endpoint.py` and returns the device id. It does not store the secret and does not write a diagnostic. A bearer that does not match an enrolled device is refused. No backdoor token was added.

The console functions remain:

- `integrations.remote_work.create_work_order`
- `integrations.remote_work.approve_work_order`
- `integrations.remote_work.poll_jobs`
- `integrations.remote_work.claim_job`
- `integrations.remote_work.complete_job`
- `integrations.remote_work.post_heartbeat` for liveness without a second approval

The laptop still reads a jobs file and does not open a socket:

`python -m integrations.remote_worker poll-once`

`integrations.remote_worker.exchange` polls, claims, and completes through an injected transport. Tests use a fake transport. The function does not open a socket. Without `--jobs`, `poll-once` reads stdin. The default result is a plan (`state` `planned`). `--live` is the operator switch on the laptop and still does nothing unless `REMOTE_IT_WORK_LIVE=1` and, for download, install, and heartbeat, an injected runner is what actually runs.

## What the eight actions do now

A claimed order whose approval matches, plus an injected runner, finishes the action. A mismatch stays unsucceeded.

- `monitor.heartbeat` records liveness only: device id, UTC time, and worker version. The direct post needs no second approval. A claimed heartbeat order finishes with those three fields and nothing else.
- `repair.service.restart` restarts one stopped automatic service through the injected runner (`sc.exe start` of that one name). Reboot, restart-all, a running service, and a manual service stay refused.
- `repair.printer.clear_queue` clears one named queue through the injected runner. When the order names a path, that runner deletes one `.spl` or `.shd` file in that queue's spool directory. `all`, `*`, and any other path stay refused.
- `setup.onboard.local_user` creates one local user through the injected runner. The password is a handler input. It does not appear in the order, the audit, or the result JSON.
- `setup.offboard.local_user` removes or disables one named user through the injected runner. `admin_count` below 2 is refused.
- `change.download` runs only through the injected runner, and only for an https host on that order's allowlist, a destination inside the approved staging directory, and a sha256 pin. The test runner does not open a socket. An http URL, a host off the allowlist, a destination outside staging, a missing pin, and a URL with credentials stay refused.
- `change.install` runs only through the injected runner for source `windows-update`, `pnputil`, or `staged-file` when the offered sha256 matches the approved pin. A mismatch is refused and the runner is not called. This work did not invoke pnputil or Windows Update.
- `change.delete` runs only through the injected runner for the one exact approved file path. Drive roots, `Windows\System32`, `Windows\SysWOW64`, both Program Files trees, a user-profile directory, and globs stay refused.

## Refusals the tests proved

- Unenrolled device, unknown action, and forbidden actions (`remote.desktop`, `input.keylog`, `persist.startup`, `firewall.disable`, `security.tamper`, `credential.dump`, `change.spread`).
- Reboot, restart-all, a running service, and a service that is not automatic.
- A printer path outside that queue's spool files, and queue names `all` and `*`.
- A password on the work order, and a password in the audit, the stored order, or the worker JSON. The injected runner still receives the sentinel.
- A blank local user, and offboard when `admin_count` is below 2.
- An http URL, a host that is not on the order allowlist, a destination outside the staging directory, a missing sha256, and a URL that carries credentials. Download does not call DNS or HTTP.
- An install source other than `windows-update`, `pnputil`, or `staged-file`, a sha256 that does not match, and a staged file outside the staging directory. A sha256 mismatch does not call the runner.
- Drive roots, `Windows\System32`, `Windows\SysWOW64`, `Program Files`, `Program Files (x86)`, a user-profile directory, globs, UNC paths, and a delete whose path is not the approved target.
- Approval expiry at 15 minutes, a second claim, a binding change of device, action, target, or parameters, a second complete, and a complete from another device.
- Heartbeat fields other than device id, UTC time, and worker version.
- HTTP create and approve without an operator session, and HTTP poll, claim, complete, and heartbeat without a device bearer. A bearer that is not the enrolled device secret is refused. The secret is not in the order or the audit, and authenticating does not store a diagnostic.

## What was not run

This branch does not connect to Office PC `bead5785f3674aaeb92c189f8c1b5b8c`. That laptop is not on this network. Nothing enrolled a live device, opened SSH, started a tunnel, or ran a worker against a live PC. Qwen, the gateway, and the console were not restarted. Production stays NO-GO. `ops/acceptance_board.py` and `docs/results/acceptance-evidence.json` were not edited.

The owner still has to run the worker on that laptop after this branch is merged. This work did not do that.

## Base and tests

Fetched `origin/main` is `bba59f08d4787e48a01766ff18ca165fc8089175` (`docs: Liaison LOG for PR #15 offline RAG eval land (#22)`). This branch stays on that base. It is not merged.

`python -m unittest integrations.tests.test_remote_work` from this worktree: 28 tests, OK. `python -m unittest web.test_remote_work_http`: 1 test, OK. The default live runner invocation count stayed 0. A missing operator session and a missing device bearer were refused. Office PC was not contacted.

## Next

Do not merge this branch from here. Do not push `main`. After merge, the owner runs `python -m integrations.remote_worker poll-once` on the enrolled laptop. Live changes stay off until that operator sets `REMOTE_IT_WORK_LIVE=1` and passes `--live`. Download, install, and heartbeat still need an injected runner; the default runner will not perform them.
