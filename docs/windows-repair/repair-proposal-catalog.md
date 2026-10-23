# Repair Proposal Catalog

## Purpose

This catalog documents **proposed repair actions** with diagnostic evidence, impact explanation, exact action/target, risk classification, operator identity, preconditions, rollback plan, and expiry.

**IMPORTANT:** This is the **proposal and audit** path only. **Execution on enrolled devices is NOT implemented.** `repair_authority=false` for all devices. Remote repair is NOT production-ready.

## Permissions Model

### Roles

- **view**: Read device diagnostics and job status (no propose, no approve, no execute)
- **diagnose**: Propose diagnostic jobs (read-only collectors only, no repairs)
- **approve**: Approve proposed repairs (recorded in audit, not executed)
- **execute**: NOT IMPLEMENTED (future: run approved repairs with explicit consent)

### Separation

- Viewing diagnostics does not grant repair authority
- Proposing a repair does not execute it
- Approving a repair records consent but does not execute it (execution requires separate permission)
- Execution requires all of: operator auth, device enrollment, approval_id, recorded rollback plan, expiry

## Repair Actions (Proposals Only)

### 1. win.service.restart

**Diagnostic evidence required:**
- Service name
- Current status (stopped, running, etc.)
- Start type (auto, manual, disabled)
- Recent event log errors (if available)

**Proposed action:**
```powershell
Restart-Service -Name "<service-name>" -Force
```

**Impact:**
- Service will stop and restart
- Active connections/sessions may be interrupted
- ~5-30 seconds downtime for the service
- Other services dependent on this one may restart

**Risk classification:** LOW (reversible, standard Windows operation)

**Preconditions:**
- Service exists on the target system
- Operator has recorded customer approval for restart
- Service is not critical system service (e.g., not "wininit", "csrss")

**Rollback plan:**
1. If restart fails, service remains in stopped state
2. Manual rollback: `Start-Service -Name "<service-name>"`
3. If service does not start, check event log for dependencies
4. Worst case: Reboot the PC to restore auto-start services

**Expiry:** 1 hour from proposal (operator must re-propose if expired)

**Approval required:** Yes (recorded in `device_store.py` audit log)

**Execution:** NOT IMPLEMENTED (device jobs remain read-only allowlist)

---

### 2. win.update.install

**Diagnostic evidence required:**
- Pending update KB numbers
- Update install date (if retrying failed update)
- Available disk space (must be >10 GB)
- Windows Update error codes (if any)

**Proposed action:**
```powershell
# Search for updates
$session = New-Object -ComObject Microsoft.Update.Session
$searcher = $session.CreateUpdateSearcher()
$updates = $searcher.Search("IsInstalled=0 AND IsHidden=0")

# Install pending updates
$installer = $session.CreateUpdateInstaller()
$installer.Updates = $updates.Updates
$result = $installer.Install()
```

**Impact:**
- Windows updates will download and install
- May require reboot (proposal must include reboot consent)
- ~10-60 minutes for large updates
- PC may be unusable during install

**Risk classification:** MEDIUM (requires reboot, may fail and require manual recovery)

**Preconditions:**
- Available disk space >10 GB
- Customer approval for reboot recorded
- No pending reboot from previous updates (check `Test-PendingReboot`)
- Operator has scheduled maintenance window

**Rollback plan:**
1. If update fails, PC may boot into recovery mode
2. Manual rollback: Boot to Safe Mode, uninstall failed update via `wusa /uninstall /kb:<kb-number>`
3. If PC does not boot, customer must perform System Restore from recovery console
4. **Customer must be warned:** Update rollback may require physical access

**Expiry:** 24 hours from proposal (long window for maintenance scheduling)

**Approval required:** Yes + customer reboot consent

**Execution:** NOT IMPLEMENTED (no silent Windows Update execution)

---

### 3. hw.driver.update

**Diagnostic evidence required:**
- Device name
- Hardware ID
- Current driver version
- Problem code (e.g., Code 28 = missing driver)

**Proposed action:**
```powershell
# This is a PROPOSAL only. DO NOT execute automatically.
# Operator must:
# 1. Download signed driver from vendor website (e.g., Intel, AMD, NVIDIA)
# 2. Verify driver signature with signtool
# 3. Install via Device Manager or vendor installer
# 4. Record approval_id and rollback plan

# Example (NOT executed automatically):
# pnputil /add-driver "C:\path\to\driver.inf" /install
```

**Impact:**
- Device driver will be replaced
- Device may require reboot
- Unsigned drivers are NOT installed (Windows blocks them by default)
- Driver may not work (incompatible hardware, wrong version)

**Risk classification:** HIGH (can cause boot failure, hardware malfunction, data loss)

**Preconditions:**
- Driver downloaded from vendor website (not third-party driver sites)
- Driver signature verified with `signtool verify /pa /v driver.sys`
- Customer approval for driver update recorded
- System Restore point created before install
- Operator has physical access or remote desktop (not SSH only)

**Rollback plan:**
1. **Before install:** Create System Restore point: `Checkpoint-Computer -Description "Before driver update"`
2. If driver fails, boot to Safe Mode and roll back driver via Device Manager
3. If PC does not boot, boot to recovery console and run: `System Restore -> Select restore point`
4. **Customer must be warned:** Driver rollback may require physical access to PC

**Expiry:** 1 hour from proposal (driver updates should not be delayed)

**Approval required:** Yes + Founder approval for unsigned drivers (if any)

**Execution:** NOT IMPLEMENTED (no silent driver installs; requires manual Device Manager workflow)

**REJECT:** Silent driver downloads from third-party sites. **REJECT:** Disabling driver signature enforcement.

---

### 4. net.firewall.disable

**Status:** **DENIED**

**Reason:** Disabling Windows Firewall is not a repair. It is a security risk and does not diagnose network issues.

**Proposed action:** None (rejected)

**Alternative:** Use `Test-NetConnection` to diagnose gateway/DNS, then propose firewall rule addition (not disable) if specific port is blocked.

---

### 5. net.firewall.add-rule

**Diagnostic evidence required:**
- Application name (e.g., "Zoom.exe")
- Port number (e.g., 443, 3389)
- Protocol (TCP/UDP)
- Network diagnostic showing blocked connection

**Proposed action:**
```powershell
New-NetFirewallRule `
  -DisplayName "Allow <app-name>" `
  -Direction Inbound `
  -Program "C:\Path\To\App.exe" `
  -Action Allow `
  -Enabled True
```

**Impact:**
- Firewall will allow inbound connections to the specified app/port
- Other apps/ports remain blocked (no blanket allow)
- Rule persists across reboots

**Risk classification:** LOW (specific rule, does not disable firewall)

**Preconditions:**
- Network diagnostic shows connection failure
- Gateway is reachable (not a network-wide issue)
- Application path is verified (not a malicious executable)
- Customer approval recorded

**Rollback plan:**
1. Remove rule: `Remove-NetFirewallRule -DisplayName "Allow <app-name>"`
2. If rule causes issues, disable it: `Set-NetFirewallRule -DisplayName "Allow <app-name>" -Enabled False`
3. Firewall remains enabled with default rules

**Expiry:** 1 hour from proposal

**Approval required:** Yes

**Execution:** NOT IMPLEMENTED (device jobs remain read-only allowlist)

---

### 6. print.spooler.restart

**Diagnostic evidence required:**
- Print spooler status (stopped, running, etc.)
- Pending print jobs count
- Recent event log errors (Event ID 7031, 7034)

**Proposed action:**
```powershell
# Clear stuck print jobs
Stop-Service -Name Spooler -Force
Remove-Item -Path "C:\Windows\System32\spool\PRINTERS\*" -Force
Start-Service -Name Spooler
```

**Impact:**
- All pending print jobs will be cleared
- Printer may need to be re-added in some cases
- ~10 seconds downtime for printing

**Risk classification:** LOW (reversible, standard troubleshooting)

**Preconditions:**
- Print spooler is stuck (not accepting new jobs)
- Customer approval for clearing print queue recorded
- Printer is not in use for critical job (e.g., patient labels in hospital)

**Rollback plan:**
1. If spooler does not start, check event log for errors
2. Manual rollback: Reboot PC to restore spooler
3. Worst case: Reinstall printer drivers

**Expiry:** 1 hour from proposal

**Approval required:** Yes

**Execution:** NOT IMPLEMENTED (device jobs remain read-only allowlist)

---

### 7. win.storage.cleanup

**Diagnostic evidence required:**
- Disk free space (must be <10% or <10 GB)
- Large files/folders consuming space (if available)
- Temp folder size

**Proposed action:**
```powershell
# Cleanup temp files and Windows Update cache
cleanmgr /verylowdisk /sagerun:1

# OR manual cleanup:
Remove-Item -Path "$env:TEMP\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Windows\Temp\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Windows\SoftwareDistribution\Download\*" -Recurse -Force -ErrorAction SilentlyContinue
```

**Impact:**
- Temp files and Windows Update cache will be deleted
- May free 1-10 GB depending on system
- No user files deleted (only system temp files)
- ~5-15 minutes to complete

**Risk classification:** LOW (standard cleanup, no data loss)

**Preconditions:**
- Disk free space <10% or <10 GB
- Customer approval recorded
- No pending Windows Update (check `Get-WindowsUpdateLog`)

**Rollback plan:**
- No rollback needed (temp files can be regenerated)
- If cleanup fails, disk space remains low (no harm)

**Expiry:** 24 hours from proposal

**Approval required:** Yes

**Execution:** NOT IMPLEMENTED (device jobs remain read-only allowlist)

---

### 8. win.troubleshooter.run

**Diagnostic evidence required:**
- Problem category (network, printer, Windows Update, etc.)
- Troubleshooter name (e.g., "Network Adapter", "Printer")

**Proposed action:**
```powershell
# Run built-in Windows troubleshooter
msdt.exe /id <troubleshooter-id>

# Example troubleshooters:
# Network: msdt.exe /id NetworkDiagnosticsDA
# Printer: msdt.exe /id PrinterDiagnostic
# Windows Update: msdt.exe /id WindowsUpdateDiagnostic
```

**Impact:**
- Troubleshooter will scan for issues and propose fixes
- User may need to interact with UI (not silent)
- Fixes may require reboot (troubleshooter will prompt)

**Risk classification:** LOW (read-only scan + interactive fixes)

**Preconditions:**
- Customer approval for troubleshooter run recorded
- Operator has remote desktop access (not SSH only)
- Troubleshooter exists on this Windows version

**Rollback plan:**
- Troubleshooter does not modify system without user consent
- If troubleshooter applies unwanted fix, use System Restore

**Expiry:** 1 hour from proposal

**Approval required:** Yes

**Execution:** NOT IMPLEMENTED (requires interactive UI)

---

## Approval Workflow

### Step 1: Propose Repair

**Operator** (via Console or API):
1. Review diagnostic evidence from device report
2. Select repair action from catalog (e.g., "win.service.restart")
3. Fill in parameters (e.g., service_name="Spooler")
4. Confirm preconditions are met
5. Record customer approval (verbal consent, ticket number, etc.)
6. Submit proposal to `windows_repair/device_store.py`

**Stored fields:**
- `proposal_id`: UUID
- `device_id`: Target device
- `operator_id`: Who proposed it
- `procedure_id`: Repair action (e.g., "win.service.restart")
- `parameters`: Action-specific params (e.g., service_name)
- `diagnostic_evidence`: Link to device report or check result
- `customer_approval`: "Verbal consent 2026-10-23", "Ticket #12345", etc.
- `risk_classification`: LOW/MEDIUM/HIGH
- `rollback_plan`: Text description of rollback steps
- `proposed_at`: Timestamp
- `expires_at`: Timestamp (proposal_at + TTL)
- `state`: "proposed"

### Step 2: Review Proposal

**Approver** (admin or senior operator):
1. Review proposal in Console UI or API
2. Verify diagnostic evidence supports the proposed action
3. Verify customer approval is recorded
4. Verify rollback plan is present and clear
5. Approve or reject with reason

**If approved:**
- `state`: "proposed" → "approved"
- `approved_by`: Approver operator_id
- `approved_at`: Timestamp
- `approval_id`: UUID (used to link execution to approval)

**If rejected:**
- `state`: "proposed" → "rejected"
- `rejected_by`: Approver operator_id
- `rejected_at`: Timestamp
- `rejection_reason`: Text explanation

### Step 3: Execute (NOT IMPLEMENTED)

**CURRENT STATE:** Execution on enrolled devices is NOT implemented. `repair_authority=false` for all devices.

**FUTURE STATE (after Director approval + second-PC gate closed):**

1. Operator initiates execution via Console
2. Console creates a signed device job with `approval_id`
3. Device worker pulls job, verifies approval signature, and executes action
4. Device worker reports result (success/failure/rollback)
5. Console updates proposal state: "approved" → "executed" or "failed"
6. Audit log records execution timestamp, result, and operator

**Execution NOT enabled until:**
- Second physical Windows PC gate is closed (live evidence)
- Founder approves remote repair execution
- Director scorecard shows production readiness
- Rollback procedures are tested on non-prod systems

## Audit Log Fields

Every proposal, approval, rejection, and execution is recorded in `windows_repair/device_store.py` audit log:

```python
{
    "action": "propose" | "approve" | "reject" | "execute" | "rollback",
    "proposal_id": "<uuid>",
    "device_id": "<device-id>",
    "tenant_id": "<tenant-id>",
    "operator_id": "<operator-id>",
    "operator": "<username>",
    "procedure_id": "<repair-action>",
    "state": "proposed" | "approved" | "rejected" | "executed" | "failed" | "rolled_back",
    "at": <unix-timestamp>,
    "approval_id": "<uuid>" | None,
    "rollback_plan": "<text>",
    "execution_result": {"status": "success" | "failure", "detail": "..."},
}
```

## Testing Repair Proposals (Mock Only)

**Unit tests** should verify:
- Proposal creation with all required fields
- Approval workflow (propose → approve → audit)
- Rejection workflow (propose → reject → audit)
- Expired proposals are not executable
- Missing rollback plan is rejected
- Invalid procedure_id is rejected

**Integration tests** (mock device):
- Propose repair for mock device
- Approve proposal
- Verify audit log contains proposal + approval
- Verify device job is NOT created (execution disabled)
- Verify `repair_authority=false` in device report

**NO real repairs** are executed in tests. All tests use mocks or read-only diagnostics.

## References

- Device store: `windows_repair/device_store.py`
- Repair engine: `windows_repair/engine.py`
- Catalogue: `windows_repair/catalogue.py`
- Endpoint worker: `integrations/endpoint_worker.py`
- Approval workflow: This document

## Next Steps

1. **Code stubs:** Add `propose_repair()` function to `windows_repair/device_store.py` (proposal + audit only, no execute)
2. **Unit tests:** Test proposal workflow with mocks
3. **Console UI:** Add repair proposal form (after second-PC gate closed)
4. **Founder approval:** Review catalog and approve execution path (not yet)
5. **Director scorecard:** Track readiness metrics (second-PC gate, rollback tests, audit coverage)
