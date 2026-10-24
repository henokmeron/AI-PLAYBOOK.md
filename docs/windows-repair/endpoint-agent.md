# Windows endpoint check-in

This is a read-only worker for a computer you choose. It is not a Windows service, and enrolling it does not allow a repair.

The worker only talks to `http://127.0.0.1` or `http://localhost` with a port. On a Pod, that means an SSH tunnel from the endpoint to the console. It will not post to a public address.

## What it collects

Each report includes disk, memory, and boot time, plus these registered read-only checks when the computer is Windows:

- `win.storage.space`
- `win.services.inspect`
- `win.update.inspect`
- `hw.devices.inventory`
- `print.diagnose`
- `net.diagnose`
- `win.events.recurring`
- `win.startup.inspect`

These are the heartbeat checks. On-demand device jobs can also run the other registered read-only collectors, including activation, USB, Wi-Fi, proxy, TLS, browser, permissions, and application-crash evidence. Those collectors are not part of this heartbeat list.

The console stores a short summary, the evidence source, and whether the check succeeded. `live_windows` means the registered script ran on the computer that is running the worker. `unavailable` means that check did not succeed. Fixture data is rejected. A check time more than five minutes away from the report time is rejected. The Director does not call the fleet HEALTHY when the stored collection time is missing or older than one day, or when a registered check failed. A report from this development PC is that PC, not a customer endpoint. `collection_scope` is `computer_running_the_worker`.

`repair_authority` stays false. The model cannot add a command, a path, or a credential to the report.

## Install

Another computer uses `docs/windows-repair/register-device.md` and `scripts/register-device.ps1`. That script mints or accepts a fresh code, enrols once, and starts `remote_worker serve`. Do not run it on the Office PC that is already enrolled, and do not run it on BANYA-FAMILY-PL.

Create an enrolment code in the signed-in console (`POST /api/devices/enrolment`). Then, on the endpoint:

```powershell
python -m integrations.endpoint_worker enrol --console http://127.0.0.1:8080 --code=<one-time-code> --name="Office PC" --token-file="$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
python -m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file="$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
```

Use `--code=<one-time-code>` with the equals sign. A code that starts with `-` is otherwise read as a flag and the console never sees it. This development PC, BANYA-FAMILY-PL, refuses `enrol` unless `--fixture-label not-the-second-endpoint` is also set, and that fixture does not count as the second computer. The secret file is written before the code is sent. If the console refuses the code, the new secret file is deleted and an existing secret file is not replaced.

The device secret is written to the token file and is not printed. Do not commit that file. Repeat `report` when you want a new check-in. The console keeps the latest report and the last-seen time.

To run it on a schedule, create a Windows Scheduled Task that executes the `report` command. Do not install a Windows service for this worker.

## Remove

```powershell
python -m integrations.endpoint_worker remove --token-file "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
```

Then revoke the device in the console (`POST /api/devices/revoke`). Deleting the local file does not revoke the server record. A revoked secret cannot submit another report.

## Re-enrol

Create a new enrolment code and run `enrol` again. That creates a new device id. The old id stays revoked.

## What this is not

No repair job is sent to this worker. Impactful repairs stay on the approval workflow and are not run by this check-in. A dedicated test machine and an explicit approval are required before any repair that changes the computer.
