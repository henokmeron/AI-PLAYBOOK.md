# Windows repair platform (local development)

This is a registered-procedure framework. It is not a claim that every Windows fault can be repaired, and it has not been tested against a physical printer, a vendor driver package, or a live remote desktop.

## Live diagnostics and the printer workflow

Read-only collectors use fixed PowerShell scripts in `windows_repair/runner.py`. The model cannot supply a command. A result with `evidence_source` of `fixture` or `mock` did not come from this computer. `live_windows` did.

From `C:\Users\kokob\src\AI-PLAYBOOK.md`:

```powershell
python -m unittest windows_repair.tests.test_windows_repair windows_repair.tests.test_live_diagnostics ops_centre.tests.test_director -v
```

The Windows integration test reads disk and printer evidence on this PC. It does not restart a service.

A device job is `issued`, then `accepted` when a read-only check finishes, `expired` when its time limit passes, or `rejected` when the device is revoked or the secret does not match. A failed collection stays `failed`. The Director report treats a missing last-seen as UNKNOWN and a last-seen older than one day as DEGRADED. A mock, fixture, unlabelled, or stale accept is not HEALTHY. HEALTHY requires an accepted job whose evidence source is `live_windows`, whose check succeeded, and whose collection time is under one day old. That is still not a repair.

One live disk check through a throwaway enrolled device, stored outside the source tree:

```powershell
python -m windows_repair.test_device self-test --state $env:TEMP\repair-device.json
```

Expected: `evidence_source` is `live_windows`, `problem_resolved` is false, and `repair_authority` is false.

To enrol a dedicated test computer later, copy this repository there and run:

```powershell
python -m windows_repair.test_device enrol --state C:\ProgramData\AI-PLAYBOOK\repair-device.json
```

Save the printed secret outside git. Enrolment does not grant repair authority and does not install a Windows service. Do not point the state file at this source tree.

`DeviceStore` issues only the registered read-only diagnostics. It rejects `print.spooler.restart` at issue time, including when an approval id is supplied. Issuing a job requires a real server-side session record for an admin or operator in the same tenant. A lookalike object is rejected. No console route calls `DeviceStore.issue`. Changing `procedure_id`, `approval_id`, or `lifecycle` in a submitted job fails the signature check, and a re-signed body that does not match the issued job is rejected before collection. A collector cannot set `problem_resolved`; device jobs record it as false.

The state file and its sibling key are written by exclusive create, flush, and replace. A failed replace leaves the previous file in place. A symbolic link is refused. Permission enforcement is not optional: POSIX mode 0600 for files and 0700 for a directory this store creates, or a Windows protected ACL that allows only the current user, and the mode or ACL is read back. If that check fails, the call fails and does not report success. Creating the file is not proof that the ACL is private. A Windows ACL does not stop an administrator who can take ownership or use backup privilege, and it is not disk encryption. An existing parent directory is not rewritten. The store reloads under a lock file so two processes cannot both collect one job. That lock is not re-entrant, and the intended runtime is one loopback process. The console route `POST /api/repair/device/issue` takes the operator from the signed-in session. A request field named operator, tenant, or approval is rejected. `POST /api/repair/device/accept` is the device credential path on loopback and runs the read-only collector on the computer that hosts the console. `REPAIR_DEVICE_STATE` must be an absolute path outside this repository. When it is unset, the route reports that it is not configured.

The printer workflow can propose `print.spooler.restart` only when the spooler is not running. A different person must approve the exact device and service. This development computer still returns `needs_administrator` and does not restart the service. `problem_resolved` is true only when the restart was attempted and a before-and-after `live_windows` read, which is not a mock or fixture, shows the spooler moved from stopped to running. A dedicated test machine may set `WINDOWS_REPAIR_ALLOW_SERVICE_RESTART=1` and run the process as administrator. Do not set that here.

Pending print jobs are not deleted.

## Remote desktop

MeshCentral 1.2.6 (published 2026-09-24) is the selected boundary. Its GitHub `master` LICENSE file is Apache-2.0, copyright 2017-2025 Intel Corporation. Apache-2.0 permits commercial use if you keep its notices. This repository has not installed that release. With no `MESHCENTRAL_URL`, the state is **NOT CONFIGURED**. A configured URL can be probed, and a probe is still not a remote desktop session.

## What you can run on this PC

From `C:\Users\kokob\src\AI-PLAYBOOK.md`:

```powershell
python -m unittest windows_repair.tests.test_windows_repair ops_centre.tests.test_director -v
```

Expected: the new tests pass. They use fixtures. `mocked: true` on a printer or network result means no device was contacted.

Read-only disk check (does not delete files):

```powershell
python -c "from windows_repair.engine import execute; import json; print(json.dumps(execute('win.storage.space'), indent=2))"
```

Expected: `problem_resolved` is false. Free space is observed. The disk fault is not declared fixed.

## Operator flow

1. Enrol a device with a secret that stays on that computer. The server stores only a hash.
2. Open a support case for that organisation and device.
3. Ask for the symptom. The planner returns procedure ids.
4. Run read-only procedures (`print.diagnose`, `net.diagnose`, `hw.devices.inventory`) against evidence or a named fixture.
5. Elevated procedures (`print.jobs.clear`, `hw.driver.install`, `win.sfc.propose`) return `approval_required` until an approval id is present, then `approved_not_run_on_this_host`.
6. `net.firewall.disable` is denied even with approval.
7. The Director report includes `remote_support`. With no `MESHCENTRAL_URL` the state is **NOT CONFIGURED**.

Console routes, after the console is running with its gateway key:

- `GET /api/repair/procedures`
- `GET /api/repair/remote`
- `POST /api/repair/plan` with `{"symptom":"printer queue stuck","fixture":"printer_stuck_usb"}`
- `POST /api/repair/execute` with `{"procedure_id":"print.diagnose","fixture":"printer_stuck_usb"}`

## Remote desktop

MeshCentral is the selected boundary because it already provides enrolment, device groups, and remote desktop. This repository does not start MeshCentral and has not opened a remote session. Set `MESHCENTRAL_URL` only when you have a server. Confirm the Apache-2.0 licence on the exact version you deploy.

## Limits

- No arbitrary shell, no hidden remote control, and no stored administrator password.
- The existing endpoint check-in remains read-only. Repair jobs are separate signed envelopes with expiry and replay rejection.
- Customer organisations cannot read each other's cases.
- Hash-chained ops logs are not tamper-proof.
