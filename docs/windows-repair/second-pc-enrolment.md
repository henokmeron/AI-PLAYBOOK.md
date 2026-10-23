# Second Physical Windows PC Enrolment Runbook

## Purpose

This runbook validates that the endpoint worker can enrol a **different physical Windows computer** (not the dev PC, not BANYA-FAMILY-PL, not a Linux pod) and submit heartbeat reports with DPAPI encryption and PII redaction.

## Acceptance Gate

**BLOCKER:** No second physical Windows PC is currently enrolled.

Until a second PC completes this runbook, `counts_as_second_endpoint=false` for all devices, and **remote repair is NOT production-ready**.

## Prerequisites

### Required

- [ ] One physical Windows PC (Windows 10 1809+ or Windows 11 or Windows Server 2019+)
- [ ] **NOT** the development machine where this code was written
- [ ] **NOT** BANYA-FAMILY-PL (Linux system)
- [ ] **NOT** a Linux pod or VM
- [ ] Network access to console (SSH tunnel to `http://127.0.0.1:8080` or direct HTTPS)
- [ ] Python 3.8+ installed on the Windows PC
- [ ] Git clone of this repository on the Windows PC

### Optional

- [ ] osquery 5.13.1 MSI (if Founder approved osquery dependency)
- [ ] MeshCentral agent (if remote desktop is needed for troubleshooting)

## Step-by-Step Enrolment

### Step 1: Prepare Console

On the **console server** (Pod or local machine):

```bash
# Start the console if not already running
cd /workspace
python3 -m web.server

# The console should be listening on 127.0.0.1:8080
# Confirm with: curl http://127.0.0.1:8080/health
```

### Step 2: Create Enrolment Code

On the **console server**:

```bash
# Generate an enrolment code via API (expires in 600 seconds)
curl -X POST http://127.0.0.1:8080/api/devices/enrolment \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your-session-cookie>" \
  | jq '.enrolment_code'

# Save the code (example: "AbC123dEf456GhI789")
```

**OR** via Python REPL:

```python
from integrations.endpoint import DeviceRegistry
registry = DeviceRegistry.from_env()
result = registry.create_enrolment("local-console")
print(f"Code: {result['enrolment_code']}")
print(f"Expires in: {result['expires_in_seconds']} seconds")
```

### Step 3: Set Up SSH Tunnel (If Remote)

If the Windows PC is not on the same network as the console, set up an SSH tunnel:

**On the Windows PC** (PowerShell):

```powershell
# Replace <pod-ip> and <pod-port> with your Pod's SSH details
ssh -L 8080:127.0.0.1:8080 root@<pod-ip> -p <pod-port>

# Keep this terminal open
# Test: Invoke-WebRequest http://127.0.0.1:8080/health
```

### Step 4: Enrol the Windows PC

**On the Windows PC** (PowerShell as normal user, NOT Administrator):

```powershell
# Clone the repository (if not already done)
cd $env:USERPROFILE\Documents
git clone https://github.com/henokmeron/AI-PLAYBOOK.md.git
cd AI-PLAYBOOK.md

# Set the secret file path
$secretPath = "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"

# Enrol with the code from Step 2
python -m integrations.endpoint_worker enrol `
  --console http://127.0.0.1:8080 `
  --code "<enrolment-code-from-step-2>" `
  --name "Office-PC-2" `
  --token-file $secretPath

# Expected output:
# enrolled device <32-char-hex-id>
# the device secret was saved and is not printed
# acceptance_role=not-recorded-as-second-endpoint
# this computer is not recorded as the second Windows endpoint
```

**Verification after enrolment:**

```powershell
# Check that the secret file was created with DPAPI encryption
Test-Path $secretPath
# Should return: True

# Check ACL (should be private to current user)
Get-Acl $secretPath | Format-List

# DO NOT print the secret file contents (it's encrypted DPAPI blob)
```

### Step 5: Submit First Heartbeat Report

**On the Windows PC** (PowerShell):

```powershell
# Submit a diagnostic report
python -m integrations.endpoint_worker report `
  --console http://127.0.0.1:8080 `
  --token-file $secretPath

# Expected output:
# stored diagnostic for <device-id>
# acceptance_role=not-recorded-as-second-endpoint
# this computer is not recorded as the second Windows endpoint
```

**What gets uploaded:**
- OS family, version (redacted PII)
- Disk free/total bytes
- Memory total bytes
- Boot time
- Registered checks (8 collectors: storage, services, update, devices, print, network, events, startup)
- `schema_version: 1`
- `agent_version: "0.2.0"`
- **Redacted:** Usernames, home paths, emails, tokens, SIDs, GUIDs

### Step 6: Verify on Console

**On the console server**:

```bash
# List enrolled devices
curl -X GET http://127.0.0.1:8080/api/devices \
  -H "Cookie: session=<your-session-cookie>" \
  | jq '.devices[] | {device_id, display_name, diagnostic_coverage, counts_as_second_endpoint}'

# Expected output:
# {
#   "device_id": "<32-char-hex>",
#   "display_name": "Office-PC-2",
#   "diagnostic_coverage": "registered",
#   "counts_as_second_endpoint": false
# }
```

**OR** via Python REPL:

```python
from integrations.endpoint import DeviceRegistry
registry = DeviceRegistry.from_env()
devices = registry.public_devices("local-console")
for device in devices:
    print(f"Device: {device['device_id']}")
    print(f"  Name: {device['display_name']}")
    print(f"  Coverage: {device['diagnostic_coverage']}")
    print(f"  Second endpoint: {device['counts_as_second_endpoint']}")
    print(f"  Last report: {device['last_report_at']}")
```

### Step 7: Verify DPAPI Encryption (Windows Only)

**On the Windows PC** (PowerShell):

```powershell
# Read the secret file (should show DPAPI metadata, not plaintext)
$content = Get-Content $secretPath -Raw
$parsed = $content | ConvertFrom-Json

# Check storage type
$parsed.metadata.storage_type
# Expected: "dpapi"

# Attempt to decrypt as a different user (should fail)
# This proves DPAPI user-scoping works
# (Optional test: create a second Windows user, try to read the secret file)
```

### Step 8: Verify PII Redaction

**On the console server**:

```bash
# Fetch the latest report
curl -X GET http://127.0.0.1:8080/api/devices/<device-id> \
  -H "Cookie: session=<your-session-cookie>" \
  | jq '.report'

# Check for redacted fields (should NOT contain):
# - Your Windows username
# - Your home directory path (C:\Users\<username>)
# - Email addresses
# - Long tokens (>40 chars)
# - SIDs like S-1-5-21-...
# - GUIDs

# Should contain generic placeholders:
# <USERNAME>, <HOME>, <EMAIL>, <TOKEN>, <SID>, <GUID>
```

### Step 9: Test Scheduled Heartbeat (Optional)

**On the Windows PC** (PowerShell as Administrator):

```powershell
# Create a Scheduled Task for 15-minute heartbeat
$action = New-ScheduledTaskAction `
  -Execute "python" `
  -Argument "-m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file $env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"

$trigger = New-ScheduledTaskTrigger `
  -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 15)

$principal = New-ScheduledTaskPrincipal `
  -UserId $env:USERNAME `
  -LogonType S4U

Register-ScheduledTask `
  -TaskName "AI-PLAYBOOK Heartbeat" `
  -Action $action `
  -Trigger $trigger `
  -Principal $principal `
  -Description "Submit diagnostics to AI-PLAYBOOK console every 15 minutes"

# Verify the task was created
Get-ScheduledTask -TaskName "AI-PLAYBOOK Heartbeat"

# Test run immediately
Start-ScheduledTask -TaskName "AI-PLAYBOOK Heartbeat"

# Check task history
Get-ScheduledTaskInfo -TaskName "AI-PLAYBOOK Heartbeat"
```

## Acceptance Criteria

- [ ] Windows PC is **NOT** the development machine
- [ ] Windows PC is **NOT** BANYA-FAMILY-PL or any Linux system
- [ ] Enrolment succeeded (device_id returned)
- [ ] DPAPI secret file created at `$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret`
- [ ] First heartbeat report submitted successfully
- [ ] Console shows `diagnostic_coverage: "registered"` (8 checks)
- [ ] `schema_version: 1` and `agent_version: "0.2.0"` present in report
- [ ] PII redacted in report (no usernames, home paths, emails visible on console)
- [ ] `counts_as_second_endpoint: false` (expected until gate-passing logic is updated)
- [ ] No secrets or device tokens logged or printed to stdout

## Current Status

❌ **BLOCKER:** No second physical Windows PC has completed this runbook.

**Evidence required:**
- Screenshot of `Get-Acl $secretPath` showing private ACL
- Screenshot of console `/api/devices` response showing `diagnostic_coverage: "registered"`
- Confirmation that the Windows PC is a different physical machine (hostname, IP, not dev PC)

**Until this gate is closed:**
- `counts_as_second_endpoint=false` for all devices
- Remote repair is NOT production-ready
- No repair execution on enrolled devices

## Troubleshooting

### "device secret file is not private"

**Cause:** The secret file has incorrect ACL permissions.

**Fix:**
```powershell
$path = "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
icacls $path /inheritance:r /grant:r "${env:USERNAME}:F"
```

### "console refused the check-in (401)"

**Cause:** Device secret is invalid or device is revoked.

**Fix:**
- Check console logs for authentication errors
- If revoked, re-enrol with a new code
- Verify SSH tunnel is still active

### "console could not be reached"

**Cause:** SSH tunnel closed or console not running.

**Fix:**
- Verify SSH tunnel: `Test-NetConnection 127.0.0.1 -Port 8080`
- Check console is running: `curl http://127.0.0.1:8080/health`
- Restart SSH tunnel if needed

### "collector failed: unavailable"

**Cause:** Collector could not run on this system.

**Fix:**
- Check if Windows version is supported (10 1809+, 11, Server 2019+)
- Run as normal user (not Administrator) for most collectors
- Some collectors (registry, event log) may need elevation; they report "unavailable" when blocked

### "the console certificate was rejected"

**Cause:** HTTPS with self-signed certificate is rejected.

**Fix:**
- Use `http://127.0.0.1:8080` for loopback (allowed)
- OR add custom CA: `$env:ENDPOINT_CA_FILE = "C:\path\to\custom-ca.pem"`
- OR get a valid certificate for the console

## Recovery: DPAPI Blob Lost

If the DPAPI-encrypted secret file is lost (user profile deleted, disk encryption key lost, machine re-imaged):

1. **Revoke the old device** in the console:
   ```bash
   curl -X POST http://127.0.0.1:8080/api/devices/revoke \
     -H "Content-Type: application/json" \
     -H "Cookie: session=<your-session-cookie>" \
     -d '{"device_id": "<old-device-id>"}'
   ```

2. **Re-enrol** with a new code (follow Step 2-5 above). This creates a **new device_id**. The old device_id stays revoked.

## Safe Uninstall

To remove the endpoint worker from the Windows PC:

```powershell
# Stop and delete the Scheduled Task
Unregister-ScheduledTask -TaskName "AI-PLAYBOOK Heartbeat" -Confirm:$false

# Delete the secret file
Remove-Item "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret" -ErrorAction SilentlyContinue

# (Optional) Remove the repository clone
Remove-Item "$env:USERPROFILE\Documents\AI-PLAYBOOK.md" -Recurse -Force

# Revoke the device in the console (see above)
```

## Next Steps After Gate Is Closed

Once a second physical Windows PC completes this runbook:

1. **Update gate logic:** Set `counts_as_second_endpoint=true` for devices that are NOT the dev PC and NOT mocks
2. **Enable repair proposals:** Document repair execute path (approval + rollback + audit)
3. **Deploy to customer:** Package as MSI with code signature
4. **Monitor fleet:** Track heartbeat age, failed checks, DPAPI adoption via console dashboard

## References

- Endpoint agent docs: `docs/windows-repair/endpoint-agent.md`
- Secret storage: `integrations/secret_storage.py`
- Redaction: `integrations/redaction.py`
- DPAPI: Windows Data Protection API (CryptProtectData/CryptUnprotectData)
