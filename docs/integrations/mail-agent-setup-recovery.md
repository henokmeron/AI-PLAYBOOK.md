# Mail Agent Setup and Recovery Guide

**Date:** 2026-10-23  
**Version:** 1.0  
**Scope:** Microsoft 365 / Microsoft Graph integration

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Configuration](#configuration)
4. [Verification](#verification)
5. [Troubleshooting](#troubleshooting)
6. [Recovery Procedures](#recovery-procedures)
7. [Security Best Practices](#security-best-practices)

---

## Prerequisites

### Required

- Entra ID application with:
  - Platform: **Mobile and desktop applications**
  - Redirect URI: `http://127.0.0.1:18080/api/microsoft/callback`
  - Supported accounts: **Single tenant** (directory `d595636e-9ef4-4890-b8a7-bde8dd5cab03`)
  - Delegated permissions: `User.Read`, `Mail.Read`
  
- Environment:
  - Python 3.9+ with dependencies installed
  - Network access to `login.microsoftonline.com` and `graph.microsoft.com`
  - Port 18080 available for OAuth redirect

### Optional

- `Mail.ReadWrite` - For unsent draft operations (behind approval gate)
- `Files.ReadWrite` - For named file operations (behind approval gate)

### Not Required

❌ Client secret (this is a public client flow)  
❌ `Mail.Send` permission  
❌ Admin consent  
❌ Application permissions  

---

## Initial Setup

### Step 1: Obtain Application (Client) ID

1. Navigate to Azure Portal → Entra ID → App registrations
2. Locate application `llmfortestingclientid` (or create if needed)
3. Copy the **Application (client) ID** (UUID format)
4. **Do NOT commit this ID to git**

### Step 2: Configure Environment

**Option A: Environment Variable (Recommended for Development)**

```bash
export MICROSOFT_CLIENT_ID="<your-client-id>"
export MICROSOFT_TOKEN_FILE="/tmp/microsoft-365-token.json"
export MICROSOFT_TENANT="d595636e-9ef4-4890-b8a7-bde8dd5cab03"
```

**Option B: Private File (Recommended for Production)**

```bash
# Create private client ID file
mkdir -p /tmp/microsoft-config
echo "<your-client-id>" > /tmp/microsoft-config/client-id
chmod 600 /tmp/microsoft-config/client-id

# Configure environment
export MICROSOFT_CLIENT_ID_FILE="/tmp/microsoft-config/client-id"
export MICROSOFT_TOKEN_FILE="/tmp/microsoft-365-token.json"
```

**Security Notes:**
- Client ID file must be mode 0600 (owner read/write only)
- Token file created automatically with mode 0600
- Never store under `/workspace` or repository root
- Never commit to git

### Step 3: Verify Configuration

```bash
cd /workspace
python3 -c "
from integrations.microsoft365 import microsoft_configuration
import os
status = microsoft_configuration(os.environ)
print('Status:', status['status'])
print('Client ID:', status['client_id'])
print('Mailbox:', status['mailbox'])
"
```

Expected output:
```
Status: configured
Client ID: present
Mailbox: NOT CONFIGURED
```

If status is `NOT CONFIGURED`, check that `MICROSOFT_CLIENT_ID` or `MICROSOFT_CLIENT_ID_FILE` is set correctly.

---

## Configuration

### Sign-In Flow

1. **Start Console:**
   ```bash
   cd /workspace
   python3 web/console.py
   ```
   
2. **Access Console:**
   Open `http://127.0.0.1:18080/#agent` in browser

3. **Initiate Sign-In:**
   Click "Connect Microsoft 365" button
   
4. **Choose Account Type:**
   - **Work or School:** Use organization directory
   - **Personal:** Use personal Microsoft account (Outlook, Hotmail, etc.)
   
5. **Complete Consent:**
   - Review requested permissions (User.Read, Mail.Read)
   - Click "Accept"
   - Browser redirects back to console
   
6. **Verify Connection:**
   Console should show "Connected" with account email

### Offline Configuration Check

Without starting the console, verify OAuth configuration:

```bash
python3 -c "
from integrations.microsoft_oauth import MicrosoftOAuth
oauth = MicrosoftOAuth.from_env()
status = oauth.public_status()
print('Configured:', status['configured'])
print('Connected:', status['connected'])
print('Status:', status['status'])
if status['account']:
    print('Account:', status['account'])
print('Mail Read:', status['mail_read'])
"
```

### Token File Inspection

**Safe inspection (no secrets exposed):**

```bash
python3 -c "
from integrations.microsoft_oauth import MicrosoftOAuth
oauth = MicrosoftOAuth.from_env()
if oauth.bundle:
    print('Account:', oauth.bundle.account)
    print('Scope:', oauth.bundle.scope)
    print('Expires:', oauth.bundle.expires_at)
else:
    print('Not connected')
"
```

**Never:**
- Print `oauth.bundle.access_token`
- Print `oauth.bundle.refresh_token`
- Commit token file to git
- Share token file contents

---

## Verification

### Privacy-Safe Mailbox Verification

After sign-in, verify mailbox access WITHOUT exposing personal data:

```bash
python3 -c "
from pathlib import Path
from integrations.microsoft_oauth import MicrosoftOAuth
from integrations.mail_verification import MailboxVerificationHarness

oauth = MicrosoftOAuth.from_env()
harness = MailboxVerificationHarness(
    oauth=oauth,
    result_path=Path('/tmp/mailbox-verification-results.json'),
)

# Replace with owner-supplied distinctive phrase
# NOT generic words like 'the', 'a', 'an'
result = harness.verify_positive_match('project-alpha-distinctive')
print('Positive match:', result.success, 'found:', result.expected_match_found)

# Verify empty search works correctly
result = harness.verify_negative_match('nonexistent-uuid-12345-67890-abcdef')
print('Negative match:', result.success, 'empty:', result.expected_match_found)

# View summary
summary = harness.summary()
print('Live mailbox verified:', summary['live_mailbox_verified'])
"
```

**Expected Positive Match Result:**
```
success: True
http_status: 200
result_count: > 0
expected_match_found: True
```

**Expected Negative Match Result:**
```
success: True
http_status: 200
result_count: 0
expected_match_found: True  # Zero results is correct
```

**Privacy Notes:**
- Verification records ONLY: HTTP status, result count, boolean match
- Never logs: subject lines, bodies, senders
- Results saved to `/tmp/mailbox-verification-results.json`

### Run Unit Tests

```bash
cd /workspace
python3 -m pytest integrations/tests/test_microsoft_oauth.py -v
python3 -m pytest integrations/tests/test_mail_verification.py -v
python3 -m pytest integrations/tests/test_microsoft_resilience.py -v
python3 -m pytest integrations/tests/test_automation.py -v
```

All tests should pass without requiring live credentials (use mock transport).

---

## Troubleshooting

### Issue: "NOT CONFIGURED" Status

**Symptoms:**
- Console shows "NOT CONFIGURED"
- `microsoft_configuration()` returns status "NOT CONFIGURED"

**Diagnosis:**
```bash
# Check environment
echo $MICROSOFT_CLIENT_ID
echo $MICROSOFT_CLIENT_ID_FILE

# Check client ID source
python3 -c "
from integrations.microsoft_oauth import client_id_source
import os
source = client_id_source(os.environ)
print('Source:', source if source else 'NONE')
"
```

**Solutions:**
1. Verify `MICROSOFT_CLIENT_ID` or `MICROSOFT_CLIENT_ID_FILE` is set
2. If using file, verify it exists and is readable
3. If using file, verify permissions are 0600
4. Verify client ID is valid UUID format
5. Restart console process after setting environment

### Issue: "Sign-in State Missing or Expired"

**Symptoms:**
- Browser redirects to console with error
- Console shows "state is missing or expired"

**Causes:**
- Browser took > 10 minutes to complete consent
- State parameter reused (already consumed)
- PKCE verifier expired

**Solutions:**
1. Initiate new sign-in (old state is invalidated)
2. Complete consent within 10 minutes
3. Do not use browser back button during sign-in

### Issue: Token Refresh Failed

**Symptoms:**
- "Microsoft revoked the saved sign-in"
- Token file deleted automatically
- Status changes to "disconnected"

**Causes:**
- Refresh token revoked by Microsoft
- User changed password
- Admin revoked consent
- Refresh token expired (long idle period)

**Solutions:**
1. Disconnect and reconnect (consent flow required)
2. Token file automatically deleted, no manual cleanup needed
3. Check Entra ID app permissions are still granted

### Issue: Permission Denied on Graph Call

**Symptoms:**
- "Mail.Read is not granted"
- "No Microsoft Graph request was sent"

**Diagnosis:**
```bash
python3 -c "
from integrations.microsoft_oauth import MicrosoftOAuth
oauth = MicrosoftOAuth.from_env()
print('Delegated scopes:', oauth.delegated_scopes())
print('Has Mail.Read:', oauth.has_mail_read())
"
```

**Solutions:**
1. Verify `Mail.Read` was included in consent
2. Check token scope: `oauth.bundle.scope`
3. If scope missing, disconnect and reconnect with correct consent
4. For draft operations, ensure `Mail.ReadWrite` was consented

### Issue: Rate Limited (429)

**Symptoms:**
- "Microsoft Graph is throttling this read"
- HTTP 429 responses

**Automatic Handling:**
- GraphResilience client retries automatically
- Respects Retry-After header
- Exponential backoff applied

**Manual Mitigation:**
```python
from integrations.microsoft_resilience import create_resilient_client
from integrations.microsoft_oauth import MicrosoftOAuth

oauth = MicrosoftOAuth.from_env()
resilient = create_resilient_client(oauth, max_retries=5, timeout=60.0)

# This will retry automatically on 429
result = resilient.graph_get_with_retry(
    "/me/messages",
    {"$top": "10"},
    required_scope="Mail.Read",
)
```

### Issue: "Mailbox: NOT CONFIGURED" After Sign-In

**Symptoms:**
- OAuth shows "connected"
- But `mailbox` field shows "NOT CONFIGURED"

**Cause:**
- No live Graph mail API call has succeeded yet
- `oauth.live_mail` flag not set

**Solution:**
- Perform a successful mail search or read operation
- Verification harness will set this flag
- Not a blocker; indicates no mail API called yet

---

## Recovery Procedures

### Scenario: Token File Corrupted

**Symptoms:**
- OAuth shows "disconnected"
- Token file present but unreadable

**Recovery:**
```bash
# Delete corrupted token file
rm -f /tmp/microsoft-365-token.json

# Reconnect (will create new token file)
# Use console sign-in flow or:
python3 -c "
from integrations.microsoft_oauth import MicrosoftOAuth
oauth = MicrosoftOAuth.from_env()
oauth.disconnect()  # Cleanup
print('Token cleared. Reconnect via console.')
"
```

### Scenario: Token File Permissions Wrong

**Symptoms:**
- "Microsoft token file is not private"
- OAuth refuses to load token

**Recovery:**
```bash
# Fix permissions
chmod 600 /tmp/microsoft-365-token.json

# Verify
ls -l /tmp/microsoft-365-token.json
# Should show: -rw------- (owner read/write only)
```

### Scenario: Console Not Loading Application ID

**Symptoms:**
- Console running but shows "NOT CONFIGURED"
- Environment variable set in shell but not in process

**Recovery:**
```bash
# Export environment and restart console
export MICROSOFT_CLIENT_ID="<your-client-id>"

# Stop console process (Ctrl+C or kill)

# Restart console
python3 web/console.py
```

### Scenario: Consent Revoked by Admin

**Symptoms:**
- "Access Denied" on Graph calls
- HTTP 403 responses

**Recovery:**
1. Disconnect current session:
   ```python
   oauth = MicrosoftOAuth.from_env()
   oauth.disconnect()
   ```

2. Contact admin to restore consent

3. Reconnect via console (full consent flow required)

### Scenario: Lost Access to Entra Application

**Symptoms:**
- Cannot access Azure Portal
- Application settings unknown

**Recovery Without Portal Access:**
- Application ID: Must be provided by owner/admin
- Redirect URI: `http://127.0.0.1:18080/api/microsoft/callback`
- Permissions: `User.Read`, `Mail.Read`
- Tenant: `d595636e-9ef4-4890-b8a7-bde8dd5cab03`

**If Application Deleted:**
1. Create new Entra application
2. Configure as documented in Prerequisites
3. Grant same permissions
4. Update `MICROSOFT_CLIENT_ID` to new application ID
5. Reconnect via console

---

## Security Best Practices

### Token Storage

✅ **Do:**
- Store tokens in `/tmp` or secure temp directory
- Enforce mode 0600 on token files
- Use `MICROSOFT_TOKEN_FILE` to configure path
- Delete token file on disconnect

❌ **Don't:**
- Store tokens in repository
- Store tokens under `/workspace`
- Commit token files to git
- Share token files between users
- Log token contents

### Client ID Handling

✅ **Do:**
- Treat as configuration (not a secret, but not public)
- Store in environment variable or private file
- Keep out of git
- Use `MICROSOFT_CLIENT_ID_FILE` for production

❌ **Don't:**
- Commit to repository
- Hardcode in source files
- Expose in error messages
- Share publicly

### Permission Management

✅ **Do:**
- Request minimum necessary scopes
- Use approval gates for writes
- Document each permission's purpose
- Audit granted permissions regularly

❌ **Don't:**
- Request `Mail.Send` (explicitly disabled)
- Request admin consent without approval
- Add permissions without review
- Use application permissions (delegated only)

### Logging and Monitoring

✅ **Do:**
- Log HTTP status codes
- Log operation types and counts
- Log error types (class names)
- Monitor retry rates

❌ **Don't:**
- Log access tokens or refresh tokens
- Log subject lines or message bodies
- Log sender or recipient addresses
- Log personal data in error messages

### Network Security

✅ **Do:**
- Use HTTPS for all Microsoft API calls
- Validate redirect URIs
- Use localhost loopback for OAuth redirect
- Enforce TLS 1.2+ for connections

❌ **Don't:**
- Use HTTP for API calls (code enforces HTTPS)
- Accept arbitrary redirect URIs
- Expose OAuth callbacks to internet
- Disable certificate validation

---

## Additional Resources

**Documentation:**
- `docs/integrations/microsoft-365-signin.md` - Sign-in setup
- `docs/integrations/power-automate.md` - Workflow integration
- `docs/integrations/mail-agent-audit-2026-10-23.md` - Security audit

**Code:**
- `integrations/microsoft_oauth.py` - OAuth implementation
- `integrations/microsoft365.py` - Mail client and catalog
- `integrations/mail_verification.py` - Privacy-safe verification

**Tests:**
- `integrations/tests/test_microsoft_oauth.py` - OAuth tests
- `integrations/tests/test_mail_verification.py` - Verification tests

---

**Document Version:** 1.0  
**Last Updated:** 2026-10-23  
**Next Review:** After production deployment or permission changes
