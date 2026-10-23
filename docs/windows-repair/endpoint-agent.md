# Windows endpoint check-in

This is a read-only worker for a computer you choose. It is not a Windows service, and enrolling it does not allow a repair.

The worker only talks to `http://127.0.0.1` or `http://localhost` with a port. On a Pod, that means an SSH tunnel from the endpoint to the console. It will not post to a public address.

## Supported Windows versions

The endpoint worker and registered collectors are designed for:
- Windows 10 (version 1809 or later)
- Windows 11 (all versions)
- Windows Server 2019 or later

Collectors use Windows Management Instrumentation (WMI), PowerShell cmdlets (Get-Service, Get-WindowsUpdateLog, Get-WmiObject, Get-NetAdapter), and Windows APIs. Older Windows versions may work but are not tested.

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

## Secret storage

**Windows (default):** Device secrets are encrypted using Windows Data Protection API (DPAPI / CryptProtectData) and stored in a JSON file. The encrypted blob is user-scoped; only the Windows user account that enrolled the device can decrypt it.

**Non-Windows / Development:** Secrets are stored in a private file (mode 0600 on POSIX) with restricted ACL.

**Migration:** Old plaintext secret files are automatically migrated to DPAPI storage on Windows when you run `report` or `jobs`. The plaintext file is removed after successful migration.

**Recovery:** If the DPAPI blob is lost (user profile deleted, disk encryption key lost, machine re-imaged), the device must re-enrol with a new secret. The old device_id will remain revoked.

Secrets are never printed to stdout or logged after creation. The console stores only a hash (SHA-256) of the device secret.

## Install

### First enrolment

1. Create an enrolment code in the signed-in console (`POST /api/devices/enrolment`). The code expires in 600 seconds.

2. On the endpoint (PowerShell as your user, not Administrator unless required):

```powershell
$secret = "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
python -m integrations.endpoint_worker enrol --console http://127.0.0.1:8080 --code "<one-time-code>" --name "Office PC" --token-file $secret
```

The device secret is written to the token file using DPAPI (Windows) and is not printed. Do not commit that file. The `--name` must be 1-40 alphanumeric characters, spaces, dots, or dashes.

3. Test the first report:

```powershell
python -m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file $secret
```

### Scheduled reports

To run it on a schedule, create a Windows Scheduled Task that executes the `report` command:

```powershell
$action = New-ScheduledTaskAction -Execute "python" -Argument "-m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file $env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U
Register-ScheduledTask -TaskName "AI-PLAYBOOK Device Report" -Action $action -Trigger $trigger -Principal $principal -Description "Submit diagnostics to AI-PLAYBOOK console"
```

This runs every 15 minutes as your user account (not SYSTEM). Adjust the interval and console URL as needed.

**Do not install a Windows service for this worker.** Scheduled Tasks are sufficient and easier to troubleshoot.

## Device jobs (on-demand diagnostics)

The worker can also pull on-demand diagnostic jobs from the console:

```powershell
$cred = "$env:LOCALAPPDATA\AI-PLAYBOOK\device-job-credential"
# The credential file is created when the console issues a job for this device
python -m integrations.endpoint_worker jobs --console http://127.0.0.1:8080 --credential $cred
```

Device jobs are read-only diagnostics (same registered collectors as heartbeat). They cannot execute repairs or commands.

## Troubleshooting

### "device secret file is not private"

The secret file has incorrect permissions. On Windows, the file must have a protected ACL allowing only your user account. On POSIX, mode must be 0600.

**Fix (Windows):**
```powershell
$path = "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
icacls $path /inheritance:r /grant:r "${env:USERNAME}:F"
```

**Fix (Linux/macOS):**
```bash
chmod 600 /path/to/device-secret
```

### "console refused the check-in (401)"

The device secret is invalid or the device is revoked. Check the console logs. If revoked, re-enrol.

### "console could not be reached"

- Check that the SSH tunnel to the console is running.
- Verify the console is listening on `127.0.0.1:8080` (or your configured port).
- Test with `curl http://127.0.0.1:8080/health` (if the console has a health endpoint).

### "the console certificate was rejected"

HTTPS with a self-signed certificate is rejected. Loopback may use HTTP. Remote endpoints require HTTPS with a valid certificate.

To trust a custom CA certificate:
```powershell
$env:ENDPOINT_CA_FILE = "C:\path\to\custom-ca.pem"
python -m integrations.endpoint_worker report --console https://console.example:443 --token-file $secret
```

### Collector fails: "unavailable" evidence_source

The collector could not run on this system. Common causes:
- Non-Windows OS (most collectors require Windows)
- Missing PowerShell cmdlets (Windows Server Core, minimal installs)
- Insufficient permissions (some WMI queries need local admin)

Check the collector summary in the report for error details.

### DPAPI decrypt failed

The DPAPI blob cannot be decrypted by the current user. This happens if:
- You enrolled as UserA but are running as UserB
- The user profile was deleted or corrupted
- The machine was re-imaged and the encryption keys are gone

**Fix:** Re-enrol the device:
```powershell
Remove-Item "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret" -ErrorAction SilentlyContinue
# Then enrol again with a new code
```

Revoke the old device in the console.

## Upgrades

When the worker code is updated:

1. Pull the latest code: `git pull origin main`
2. Re-run a report to confirm: `python -m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file $secret`

The device secret and device_id stay the same. The worker sends `agent_version` and `schema_version` with each report, so the console knows which version is active.

If the new worker requires re-enrolment (breaking change), the release notes will say so. Otherwise, upgrades are backward-compatible.

## Revocation

To revoke a device (stops accepting new reports):

1. In the console: `POST /api/devices/revoke` with `{"device_id": "..."}`
2. On the endpoint: Delete the local secret (optional):

```powershell
python -m integrations.endpoint_worker remove --token-file "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
```

The `remove` action deletes the local file but does not revoke the server record. Revoke in the console to fully stop the device from checking in.

## Safe uninstall

1. Revoke the device in the console (see above).
2. Delete the Scheduled Task (if created):

```powershell
Unregister-ScheduledTask -TaskName "AI-PLAYBOOK Device Report" -Confirm:$false
```

3. Delete the local secret file:

```powershell
Remove-Item "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret" -ErrorAction SilentlyContinue
Remove-Item "$env:LOCALAPPDATA\AI-PLAYBOOK\device-job-credential" -ErrorAction SilentlyContinue
```

4. (Optional) Remove the AI-PLAYBOOK directory if empty:

```powershell
Remove-Item "$env:LOCALAPPDATA\AI-PLAYBOOK" -Recurse -Force -ErrorAction SilentlyContinue
```

No registry keys, drivers, or services are installed, so uninstall is just removing files.

## Code signing (future)

The endpoint worker is currently distributed as Python source. For production deployment, consider:

- **Installer:** Package as a standalone executable with PyInstaller or cx_Freeze, sign with an Authenticode certificate.
- **Script signing:** Sign the PowerShell enrollment script with `Set-AuthenticodeSignature`.
- **Verification:** Users should verify the signature before running: `Get-AuthenticodeSignature setup.exe`.

**Do not download untrusted binaries.** Clone from the official repository and review the source.

**Do not disable Windows Defender or SmartScreen** to run the worker. If Defender blocks it, submit the file for analysis or sign it with a valid certificate.

## Re-enrol

To rotate the device secret (e.g., after a suspected compromise):

1. Create a new enrolment code in the console.
2. Remove the old secret file.
3. Run `enrol` again (see "First enrolment" above).

This creates a **new device_id**. The old device_id stays revoked. There is no in-place secret rotation that preserves the device_id.

## Redaction

Before upload, the worker automatically redacts:
- Usernames (from paths like `C:\Users\Alice`)
- Home directory paths
- Email addresses
- Security identifiers (SIDs)
- Long tokens (40+ characters)
- GUIDs

The redacted report still contains enough context for diagnosis. If you need to preserve specific values for troubleshooting, temporarily disable redaction (not recommended for production).

## What this is not

No repair job is sent to this worker. Impactful repairs stay on the approval workflow and are not run by this check-in. A dedicated test machine and an explicit approval are required before any repair that changes the computer.

**Remote repair is NOT production-ready.** The repair proposal workflow (see below) is for audit and review only. Execution on the endpoint is not implemented and is not enabled.

## Repair proposals (audit only, not for execution)

The repair approval workflow allows operators to:
1. **Propose** a repair action with diagnostic evidence, impact explanation, exact action/target, risk classification, operator identity, preconditions, rollback plan, and expiry.
2. **Review** the proposal (approval or rejection is recorded in audit logs).
3. **Execute** (NOT IMPLEMENTED): Execution requires explicit approval recorded in the audit log and must NOT enable arbitrary PowerShell or silent execution.

Repair proposals are **NOT executed on the endpoint automatically**. Device jobs remain read-only allowlist (registered collectors only). The `net.firewall.disable` action is explicitly denied.

Permissions are separated:
- **view**: Read device diagnostics and job status
- **diagnose**: Propose diagnostic jobs (read-only collectors)
- **approve**: Approve proposed repairs (recorded in audit, not executed)
- **execute**: NOT IMPLEMENTED (future: run approved repairs with explicit consent)

This is the proposal/audit path. Execution is a future feature and is not safe to deploy until a second Windows endpoint is enrolled and tested.

## Limitations

- **One PC tested:** This worker is mock-tested in unit tests. Only one physical Windows PC (the development machine) has been enrolled. A second Windows PC is required to close the acceptance gate.
- **Loopback only:** The worker only talks to `http://127.0.0.1` or `http://localhost`. Remote deployment requires an SSH tunnel.
- **No service install:** This is a Scheduled Task, not a Windows service. Service installation is not documented or supported.
- **Read-only:** No repair commands are executed on the endpoint. Repair execution is not implemented.
- **No remote control:** No screen capture, no shell access, no file browser. The worker submits only the fixed diagnostic schema.
- **No second endpoint:** The second Windows PC gate is still open. Fresh recovery on the same PC does not satisfy that gate.
- **Not production-ready for remote repair:** Repairs require explicit approval, a second test machine, and code review before any execution on an enrolled device.

## Security decisions

- **DPAPI user scope:** Secrets are encrypted for the enrolling Windows user. If the user profile is lost, re-enrol.
- **No Administrator required:** Enrolment and heartbeat run as a normal user. Some collectors (registry, event log) may need elevated permissions for full results; when they fail, the worker reports "unavailable" instead of crashing.
- **Redaction always on:** Usernames, paths, tokens, and PII are stripped before upload. The server never sees the raw collector output.
- **TLS verification required:** HTTPS endpoints must have valid certificates. `ENDPOINT_CA_FILE` is for custom CAs (enterprise environments), not for disabling verification.
- **No command injection:** The worker does not accept commands, paths, or scripts in the report schema. Device jobs can only run registered read-only collectors (allowlist).
- **Revocation is immediate:** Revoked devices cannot submit new reports. The server rejects them at authentication.
- **No automatic repair:** Repair proposals are audit-only. Execution requires explicit approval (not implemented on the endpoint).

## Next steps

- **Second endpoint:** Enrol a second physical Windows PC (not this dev machine, not BANYA-FAMILY-PL, not a Linux pod) and verify heartbeat + device jobs.
- **Fresh recovery:** Test that a fresh Windows install can enrol, report, and run device jobs without manual fixes.
- **Installer:** Package the worker as a signed executable for easier deployment.
- **Repair execution:** Implement the execute path with approval gates, rollback plans, and audit logs (after second endpoint is proven).
- **Remote deployment:** Document SSH tunneling for remote endpoints (beyond loopback).
