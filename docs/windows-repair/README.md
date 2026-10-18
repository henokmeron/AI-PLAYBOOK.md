# Windows repair platform (local development)

This is a registered-procedure framework. It is not a claim that every Windows fault can be repaired, and it has not been tested against a physical printer, a vendor driver package, or a live remote desktop.

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
