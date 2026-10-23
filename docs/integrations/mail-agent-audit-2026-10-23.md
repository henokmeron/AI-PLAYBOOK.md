## Mail Agent Security and Permission Audit

**Date:** 2026-10-23  
**Scope:** Microsoft 365 / Microsoft Graph integration  
**Repository:** https://github.com/henokmeron/AI-PLAYBOOK.md  
**Current HEAD:** 30164f9f61f0ec2bfa86d425e1edf51b6689e431

---

## Executive Summary

This audit reviews the Mail agent (Microsoft 365/Graph integration) against strict permission boundaries. The integration is designed for **read-only mailbox access** with approved draft operations only. Sending mail and broader permissions are explicitly disabled.

**Status:** NOT CONFIGURED (no live credentials present)  
**Permissions:** User.Read and Mail.Read ONLY (as designed)  
**Live Mailbox Testing:** BLOCKED (no MICROSOFT_CLIENT_ID configured)

---

## 1. Authentication and Authorization Audit

### 1.1 OAuth 2.0 Flow

**Implementation:** Authorization Code flow with PKCE (`integrations/microsoft_oauth.py`)

✅ **Compliant:**
- Uses PKCE (S256) with no client secret
- Code verifier stays server-side, single-use, 10-minute expiry
- State parameter validated to prevent CSRF
- Redirect URI restricted to localhost loopback only
- No public web redirects accepted

✅ **Token Storage:**
- Access and refresh tokens stored in `/tmp/microsoft-365-token.json` (mode 0600)
- Path configurable via `MICROSOFT_TOKEN_FILE`
- Explicitly blocked from repository and `/workspace` volume
- Permissions enforced on POSIX systems (group/world-readable files rejected)
- Tokens never appear in logs, responses, or error messages

### 1.2 Consent and Permissions

**Default Sign-In Scopes (Read-Only):**
```
openid
profile
email
offline_access
User.Read
Mail.Read
```

**Additional Scopes (Behind Approval Gate):**
- `Mail.ReadWrite` - Only for unsent draft operations, requires approval
- `Files.ReadWrite` - Only for named file operations, requires approval

**Explicitly Disabled:**
- ❌ `Mail.Send` - Never requested, always refused
- ❌ Admin consent flows
- ❌ Application permissions (delegated only)
- ❌ Broader Graph permissions (Teams, Calendar, SharePoint not in default flow)

### 1.3 Tenant and Account Boundaries

**Configuration:**
- Default tenant: `d595636e-9ef4-4890-b8a7-bde8dd5cab03` (single-tenant)
- `common` tenant rejected by code, never sent to Microsoft
- Sign-in offers organization or personal accounts (not both simultaneously)
- No cross-tenant token sharing

**Code References:**
- `microsoft_oauth.py:62-64` - Default tenant constant
- `microsoft_oauth.py:136-145` - Tenant validation and `common` rejection
- `microsoft_oauth.py:149-154` - Resolution to default tenant

### 1.4 Token Lifecycle

**Access Token:**
- Obtained via authorization code exchange
- Expires after ~1 hour (Microsoft default minus 60s buffer)
- Automatically refreshed when expired (before Graph call)

**Refresh Token:**
- Stored securely, rotated on refresh
- If revoked: sign-in required, old token deleted
- Network failures: token retained, retry allowed

**Disconnection:**
- Manual via `disconnect()` method
- Automatic on refresh failure with `invalid_grant`
- Token file deleted on disconnect

**Code References:**
- `microsoft_oauth.py:527-547` - Token refresh logic
- `microsoft_oauth.py:802-806` - Disconnect and cleanup
- `microsoft_oauth.py:839-850` - Revoked token handling

---

## 2. API Error Handling

### 2.1 HTTP Status Code Handling

| Status | Error Type | Retry? | Action |
|--------|-----------|--------|--------|
| 200/201 | Success | N/A | Return data |
| 204 | Success (empty) | N/A | Return success indicator |
| 400 | InvalidRequest | No | Fail immediately with safe message |
| 401 | AuthenticationError | No | Prompt reconnection, never retry |
| 403 | PermissionDenied | No | Report missing scope, no request sent |
| 404 | NotFound | No | Return not_found status |
| 409 | Conflict | No | Report conflict (e.g., file exists) |
| 429 | RateLimited | Yes | Respect Retry-After header |
| 500+ | TransientError | Yes | Exponential backoff retry |

**Privacy Protection:**
- Error messages never include tokens
- Microsoft error details sanitized before logging
- User data never appears in exception text

**Code References:**
- `microsoft_oauth.py:569-591` - Graph GET error handling
- `microsoft_oauth.py:620-639` - Graph write error handling
- `resilience.py:40-77` - Retry policy implementation

### 2.2 Retry Strategy

**Resilient Client** (`microsoft_resilience.py`):
- Maximum 4 attempts for idempotent operations
- Exponential backoff: 1s, 2s, 4s, 8s (with jitter)
- Respects Retry-After headers from 429 responses
- Non-idempotent operations: no automatic retry
- Permanent errors (400, 403, 404): no retry

**Timeout Handling:**
- Default 30-second timeout per request
- Configurable via `GraphResilience` constructor
- Long operations may hit timeout and fail gracefully

**Code References:**
- `microsoft_resilience.py:34-76` - Retry wrapper
- `resilience.py:53-77` - Core retry logic

---

## 3. Data Privacy and Logging

### 3.1 What is NEVER Logged or Stored

❌ **Personal Data:**
- Subject lines
- Message bodies
- Sender addresses
- Recipient addresses
- Body previews (except in approved UI responses)

❌ **Credentials:**
- Access tokens
- Refresh tokens
- Authorization codes
- Client secrets (none used)

### 3.2 What IS Logged (Privacy-Safe)

✅ **Operational Data:**
- HTTP status codes
- Result counts (e.g., "3 messages found")
- Error types (class names, no details)
- Retry attempts
- Boolean indicators (e.g., "match found: true")

✅ **Configuration Status:**
- Whether client ID is present ("present" or "absent", never the actual value)
- Connection status ("connected", "disconnected", "NOT CONFIGURED")
- Granted scopes (e.g., "mail:read")

**Code References:**
- `mail_verification.py:39-61` - Privacy-safe result structure
- `microsoft365.py:298-313` - Configuration reporting without secrets

### 3.3 Mailbox Verification Harness

**Purpose:** Verify mailbox access WITHOUT exposing personal data

**Privacy-Safe Testing** (`mail_verification.py`):
- Records only: HTTP status, result count, boolean match indicator
- Never stores: subjects, bodies, senders
- Graph requests use `$select=id` (no content fields)
- Supports synthetic fixtures for automated tests

**Test Types:**
1. **Positive Match:** Owner-supplied distinctive phrase should find results
2. **Negative Match:** Unmatched phrase should return zero results  
3. **Synthetic Fixture:** Mock responses for CI without credentials

**Owner Requirements:**
- Must supply distinctive phrase (not generic words like "the")
- Phrase provided via environment variable, never hardcoded

---

## 4. Resilience Features

### 4.1 Rate Limiting and Throttling

**Local Rate Limiting:**
- Token bucket per tenant+connector
- Prevents excessive client-side requests
- Configurable burst and rate limits

**Microsoft Graph Throttling:**
- Automatic retry on 429 responses
- Retry-After header respected (max 32s)
- Exponential backoff with jitter

**Code References:**
- `resilience.py:16-36` - Token bucket implementation
- `microsoft_resilience.py:42-76` - Retry with Graph throttling

### 4.2 Pagination

**Safe Pagination** (`resilience.py:82-108`, `microsoft_resilience.py:78-134`):
- Follows `@odata.nextLink` from Graph responses
- Cycle detection prevents infinite loops
- Bounded by max pages (20) and max items (1000)
- Automatic retry on transient page fetch errors

**Example:**
```python
for message in resilience.paginate_graph_results(
    "/me/messages",
    {"$select": "id,subject"},
    max_items=100,
):
    process(message)
```

### 4.3 Timeout Handling

**Request Timeouts:**
- Default: 30 seconds per Graph API call
- Configured in `GraphResilience` constructor
- Timeout failures classified as transient errors
- Retryable if operation is idempotent

### 4.4 Transient Error Recovery

**Automatically Retried:**
- 429 (Rate Limit Exceeded)
- 503 (Service Unavailable)
- 500+ (Server Errors)
- Network timeouts
- Connection failures

**Never Retried:**
- 400 (Bad Request - client error)
- 401 (Unauthorized - need reconnection)
- 403 (Forbidden - missing permission)
- 404 (Not Found - doesn't exist)

---

## 5. Permission Boundaries (Strict Enforcement)

### 5.1 Read-Only Operations

**Allowed Without Approval:**
- `search_mail` - Search mailbox with Mail.Read
- `read_mail` - Read one specific message with Mail.Read
- `search_teams_messages` - Search Teams chats (if Chat.Read granted)
- `search_files` - Search OneDrive (if Files.Read granted)
- `search_sharepoint` - Search SharePoint (if Sites.Read.All granted)
- `list_calendar` - List calendar events (if Calendars.Read granted)

**Code References:**
- `microsoft365.py:150-252` - Operation catalog with effects
- `catalog.py` - Effect.READ operations (no approval required)

### 5.2 Approved Draft Operations

**Require Approval (Effect.DRAFT):**
- `create_mail_draft` - Create unsent draft (Mail.ReadWrite)
- `update_mail_draft` - Update unsent draft (Mail.ReadWrite)
- `upload_file` - Upload named OneDrive file (Files.ReadWrite)
- `update_file` - Replace named file (Files.ReadWrite)
- `delete_file` - Delete named file (Files.ReadWrite)

**Approval Gate:**
- User must explicitly approve each operation
- Idempotency key prevents duplicate execution
- Approval recorded with approver identity

**Code References:**
- `microsoft365.py:159-232` - Draft and file operations
- `automation.py:52-89` - Approval gate implementation
- `catalog.py` - Effect.DRAFT requires approval

### 5.3 Explicitly Disabled Operations

**Always Refused (Even if Approved):**
- `send_mail` - Sending email (Effect.CONSEQUENTIAL, disabled)
- `send_teams_message` - Sending Teams message
- `update_calendar_event` - Calendar changes

**Enforcement:**
- `microsoft365.py:430-436` - Hard refusal before any API call
- `microsoft_oauth.py:594-599` - Additional send path detection
- Returns `PermissionDenied` with "No request was sent"

**Test Coverage:**
- `test_microsoft_oauth.py:286-305` - Send refusal tests
- `test_microsoft_oauth.py:516-523` - Prompt injection resistance

### 5.4 Permission Escalation Prevention

**File Path Validation:**
- Empty paths rejected
- Drive root rejected
- Folder deletion rejected
- Path traversal blocked (`.` and `..`)
- Only named files allowed

**Message ID Validation:**
- Must match regex `[A-Za-z0-9_+=/\-]{8,512}`
- Send paths explicitly rejected (`/send`, `/sendmail`)
- URL-encoded before Graph API call

**Code References:**
- `microsoft_oauth.py:182-200` - Drive path validation
- `microsoft_oauth.py:470-480` - Message ID validation
- `microsoft_oauth.py:648-659` - Send path detection

---

## 6. Integration Interfaces

### 6.1 Catalog and Operation Specs

**Connector Specifications** (`microsoft365.py:144-252`):
- `MICROSOFT_365` - Mail, Teams, OneDrive, SharePoint
- `AZURE` - Read-only subscription and resource inventory

**Operation Specification Fields:**
- `name` - Operation identifier
- `summary` - Human-readable description
- `effect` - READ, DRAFT, REVERSIBLE, or CONSEQUENTIAL
- `scope` - Required capability (e.g., `mail:read`)
- `provider_permissions` - Graph API scopes required
- `input_schema` - JSON Schema for parameters
- `output_schema` - JSON Schema for response
- `requires_approval` - Boolean approval gate
- `idempotent` - Boolean retry safety
- `evidence` - Testing status (mock-tested, live-tested, unavailable)

### 6.2 Input Validation

**JSON Schema Validation:**
- All operation inputs validated against schema
- Length limits on all string fields
- Required fields enforced
- Additional properties rejected

**Example Schemas:**
- `_QUERY` - Search query (1-500 chars)
- `_MESSAGE` - Email draft (to, subject, body with limits)
- `_FILE_CONTENT` - File operations (path, content with 200KB limit)

**Code References:**
- `microsoft365.py:23-116` - Schema definitions
- `catalog.py` - Schema validation in execute()

### 6.3 Output Sanitization

**Response Structure** (`_MAIL_RESULT`, `_OBJECT_RESULT`):
- Fixed schema with length limits
- No raw Graph response fields
- Personal data clipped to limits (e.g., subject max 300 chars)
- Tokens and credentials never included

**Privacy Clipping** (`microsoft365.py:315-342`):
- `_clip()` - Removes newlines, limits length
- `_message()` - Extracts safe fields only
- `_item()` - Generic item formatter
- Web links validated (must start with `https://`)

---

## 7. Power Automate and Workflow Integration

### 7.1 Current Status

**NOT TESTED** - No live Power Automate flow has executed.

**Configuration:**
- `POWER_AUTOMATE_WEBHOOK_URL` environment variable (currently unset)
- When unset: approved tasks recorded as `not_tested`, no HTTP request made
- When set: webhook URL must be validated before use

**Code References:**
- `automation.py:6-14` - Power Automate configuration
- `docs/integrations/power-automate.md` - Documentation

### 7.2 Workflow Boundaries

**If Power Automate is Configured:**

✅ **Safe Triggers:**
- Approved mailbox events (new mail matching filters)
- Document library changes
- Calendar event changes (if approved)

❌ **Unsafe Triggers:**
- Unapproved mail send actions
- Automatic privileged operations
- Triggers without idempotency protection

**Required for Production:**
1. Owner-approved least-privilege webhook URL
2. Recorded successful flow execution
3. Failure handling and notification
4. Audit trail for all triggered actions
5. Idempotency keys for duplicate prevention

### 7.3 Automation Safety

**Durable Task Store** (`automation.py`):
- Idempotency key prevents duplicate execution
- Sensitive actions require approval
- Non-idempotent failures not retried
- Idempotent failures retried up to 3 times
- Approval recorded with approver identity

**Untrusted Input Protection:**
- Email content treated as untrusted
- Prompt injection resistance (tested in `test_microsoft_oauth.py:567-594`)
- Mail text cannot grant permissions or trigger sends

---

## 8. Test Coverage

### 8.1 Unit Tests

**Existing Test Files:**
- `integrations/tests/test_microsoft_oauth.py` - 830 lines, comprehensive OAuth tests
- `integrations/tests/test_automation.py` - 150 lines, automation and approval tests
- `integrations/tests/test_microsoft_resilience.py` - NEW, resilience and retry tests
- `integrations/tests/test_mail_verification.py` - NEW, privacy-safe verification tests

**Test Scenarios:**
✅ OAuth authorization and token exchange  
✅ PKCE verifier and challenge matching  
✅ Token refresh and expiration  
✅ Revoked token handling  
✅ Permission denied scenarios  
✅ Send mail refusal (always blocked)  
✅ Prompt injection resistance  
✅ Empty search results (honest reporting)  
✅ Pagination with cycle detection  
✅ Retry on transient errors  
✅ Rate limit respect  
✅ Privacy-safe verification (positive and negative matches)  
✅ Synthetic fixture testing  
✅ File path validation  
✅ Approval gate enforcement  

### 8.2 Live Testing Status

**Mock Transport:**
- All existing tests use in-memory mock transport
- No actual Microsoft Graph API calls
- OAuth marked as "mock-tested" evidence

**Live Mailbox:**
- ❌ Not tested (no `MICROSOFT_CLIENT_ID` configured)
- ❌ No real mailbox search performed
- ❌ No positive match verification with owner phrase
- ❌ No negative match verification (empty result)

**What's Needed for Live Testing:**
1. Owner sets `MICROSOFT_CLIENT_ID` in environment or private file
2. Owner completes consent flow in browser
3. Owner provides distinctive phrase for positive match test
4. Owner provides nonsense phrase for negative match test
5. Run verification harness and record results
6. Confirm HTTP 200, result counts, no personal data logged

### 8.3 CI/CD Considerations

**Automated Tests (No Credentials):**
- All current tests pass without credentials
- Synthetic fixtures used for mailbox verification
- No live Graph API dependency

**Manual Verification Required:**
- Live mailbox access (owner credentials)
- Power Automate flow execution (if configured)
- End-to-end consent and token refresh

---

## 9. Remaining Gaps and Blocks

### 9.1 Blocked by Configuration

**MICROSOFT_CLIENT_ID:**
- **Status:** NOT CONFIGURED
- **Impact:** No live sign-in possible, mailbox remains "NOT CONFIGURED"
- **Resolution:** Owner must set environment variable or client ID file
- **Security:** Client ID is configuration, not a secret, but kept out of git

**POWER_AUTOMATE_WEBHOOK_URL:**
- **Status:** NOT CONFIGURED
- **Impact:** Approved automation tasks recorded as "not_tested", no HTTP sent
- **Resolution:** Owner must validate and approve webhook URL
- **Security:** Webhook URL must not be committed to git

### 9.2 Blocked by Owner Approval

**Live Mailbox Verification:**
- Requires owner-supplied distinctive phrase (not generic)
- Requires completion of browser consent flow
- Results must confirm HTTP 200, positive and negative matches

**Power Automate Flow:**
- Requires owner-approved flow creation
- Requires documented trigger, actions, and failure handling
- Must verify end-to-end execution before labeling "live"

### 9.3 Not Implemented (By Design)

**Mail.Send:**
- ❌ Never requested, always refused
- ❌ Not added to consent scope
- ❌ Hard-coded refusal in all code paths

**Admin Consent:**
- ❌ No organization-wide permissions requested
- ❌ No application permissions (delegated only)
- ❌ No additional Entra applications

**Broader Permissions:**
- Teams.ReadWrite, Files.ReadWrite.All, Sites.FullControl, etc.
- All blocked from default consent flow
- Some available behind approval gate (Files.ReadWrite for named files)

---

## 10. Audit Conclusions

### 10.1 Compliance Summary

✅ **Compliant:**
- Uses only User.Read and Mail.Read for default sign-in
- Mail.Send explicitly disabled and refused
- Tokens never exposed in logs, responses, or errors
- Personal data (subjects, bodies) never logged
- Secrets never committed to git
- Proper OAuth flow with PKCE, no client secret
- Approval gate for draft and file operations
- Retry with exponential backoff and Retry-After respect
- Pagination with cycle detection
- Input validation and output sanitization

⚠️ **Not Verified (Blocked):**
- Live mailbox positive match (no credentials)
- Live mailbox negative match (no credentials)
- Power Automate flow execution (not configured)

❌ **Explicitly Disabled:**
- Sending email
- Broader Graph permissions without approval
- Cross-tenant access
- Application permissions

### 10.2 Recommendations

**Before Production:**
1. ✅ Complete live mailbox verification with owner phrase
2. ✅ Document Power Automate flow (if required) and verify execution
3. ✅ Confirm no credentials or tokens in git history
4. ✅ Review audit logs for any personal data leaks
5. ✅ Owner approval for any permission additions

**For Hardening:**
1. ✅ Add monitoring for retry counts and rate limit hits
2. ✅ Document disaster recovery (token revocation, re-consent)
3. ✅ Add alerts for authentication failures
4. ✅ Periodic permission audit (quarterly review)

**Not Recommended:**
- ❌ Adding Mail.Send permission
- ❌ Weakening approval gates
- ❌ Storing tokens in git or shared volumes
- ❌ Logging message content or personal data

---

## 11. Code References

**Primary Implementation Files:**
- `integrations/microsoft365.py` - Catalog and client (808 lines)
- `integrations/microsoft_oauth.py` - OAuth and Graph API (937 lines)
- `integrations/resilience.py` - Retry and pagination (108 lines)
- `integrations/microsoft_resilience.py` - NEW, Graph resilience wrapper
- `integrations/mail_verification.py` - NEW, privacy-safe verification harness
- `integrations/automation.py` - Approval and idempotency
- `integrations/catalog.py` - Operation catalog and execution

**Test Files:**
- `integrations/tests/test_microsoft_oauth.py` - 830 lines
- `integrations/tests/test_automation.py` - 150 lines
- `integrations/tests/test_microsoft_resilience.py` - NEW
- `integrations/tests/test_mail_verification.py` - NEW

**Documentation:**
- `docs/integrations/microsoft-365-signin.md` - Sign-in setup
- `docs/integrations/power-automate.md` - Workflow integration
- `docs/integrations/INTEGRATION_MATRIX.md` - Integration overview

---

**Audit Completed:** 2026-10-23  
**Next Review:** After live mailbox verification or before production use  
**Auditor Note:** This audit is based on code inspection and unit tests. Live verification is BLOCKED by missing credentials.
