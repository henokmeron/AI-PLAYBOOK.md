# Integration framework and provider assessment

Status: **framework is a local prototype tested only against an in-memory fake connector.
No real provider integration exists or has been tested. No accounts were connected.**
Provider facts below come from the vendors' public documentation as generally known in 2026.
Re-verify scopes, limits and pricing against current vendor docs before building, because they change.

## 1. Framework (`integrations/`)

| Concern | Implementation | Guarantee in code |
| --- | --- | --- |
| Auth | `Connector.authenticate(ctx)` with credentials from a `SecretProvider` | A missing or short credential fails closed before any provider call (`AuthenticationError`). |
| Least-privilege scopes | `tenancy.Scope("<resource>:<read\|write>")`, `TenantContext.scopes` | Every operation declares one scope. Write never implies read. |
| Read vs write separation | `Connector.read()` / `Connector.write()` | Calling a write operation through `read` (or the reverse) raises `InvalidRequest`. `Operation` refuses to define a write that does not require approval. |
| Approval for writes | `approvals.ApprovalService` | An approval is bound to tenant, connector, operation and a SHA-256 of the exact params. It expires (15 min by default), is single-use, and needs a distinct approver in the same tenant. It is consumed before execution, so a failed write needs a fresh approval. |
| Tenant boundary | `TenantContext.require_tenant()` and per-tenant rate-limit keys | Resources carry their owning tenant; cross-tenant reads raise `TenantBoundaryViolation` and are audited as `denied`. |
| Rate limiting | `resilience.TokenBucket` keyed `tenant:connector` | Local limit raises `RateLimited(retry_after=…)` before the provider is hit. |
| Retries with backoff | `resilience.call_with_retry` | Retries only `retryable` errors (`RateLimited`, `TransientError`) and only when the operation is idempotent. Writes are retried only with an idempotency key. Exponential backoff with jitter; honours `retry_after`. |
| Pagination | `resilience.iterate_pages` | Hard `max_pages` / `max_items` limits; a repeated cursor raises an error instead of looping. |
| Webhooks | `webhooks.WebhookVerifier` | HMAC-SHA256 over `timestamp.body`, constant-time compare, ±300 s tolerance, replay cache by delivery id, 1 MiB body cap. |
| Error taxonomy | `errors.py`, `classify_http_status()` | authentication, permission_denied, tenant_boundary, approval_required, not_found, conflict, invalid_request, rate_limited*, transient*, webhook_verification, provider_error (* = retryable). |
| Secrets | `secrets.Secret`, `EnvSecretProvider` (allowlist), `FileSecretProvider` | `repr`/`str`/`format` print `[REDACTED]`; secrets cannot be pickled. File secrets must be regular files with mode 600 on POSIX, ≤16 KiB. |
| Audit trail | `audit.AuditLog` | Append-only, SHA-256 hash-chained (`verify_chain()`), params redacted with `agents/redaction.py`, optional JSONL sink. Records every read, write, denial and approval request. |

Tests: `python -m unittest discover -s integrations/tests -t .`

**Not built yet (needed before any real connector):** OAuth authorisation-code/PKCE flows and
token refresh, encrypted durable token storage, persistent approval and audit stores (both are
currently in-memory), per-tenant credential isolation in storage, provider-specific webhook
schemes, and an admin UI for approvals.

## 2. Provider evaluation

Scoring is 1 (poor) to 5 (good) for *this* platform's needs: grounded document Q&A for UK small and
mid-sized businesses, run on our own GPU, with least privilege and human approval.

| Provider | Value to current product | Least-privilege options | Auth & ops complexity | Data-protection risk | Score |
| --- | --- | --- | --- | --- | --- |
| **SharePoint / OneDrive (Microsoft Graph)** | 5: documents are where policies, fee schedules and contracts already live, and that feeds RAG directly | 5: `Sites.Selected` (application) grants access to only the sites an admin assigns; `Files.Read.All` / `Sites.Read.All` are available but broad | 3: Entra ID app registration, admin consent, per-site grants, delta queries for sync; throttling uses `Retry-After` | Medium: read-only, but documents may hold personal data | **4.5** |
| Microsoft 365 Outlook (Graph mail/calendar) | 3: email triage/drafting is valuable but a different product | 3: `Mail.Read` is mailbox-wide; application access policies / RBAC for Applications can restrict mailboxes but add admin work | 3–4: same Entra setup plus change-notification subscriptions that must be renewed | **High**: mailboxes are dense with personal and special-category data; sending mail is a consequential write | 3.0 |
| Google Workspace (Drive, Gmail) | 4 for Drive-based customers | 3: `drive.file` is narrow but only covers files the app created or opened; `drive.readonly` is broad; restricted Gmail scopes need a security assessment for public apps | 3–4: OAuth verification and possibly a CASA assessment for restricted scopes; domain-wide delegation is powerful and risky | Medium–High | 3.5 |
| Xero (accounting) | 2 now (finance ops is a later product line per the business strategy) | 4: granular scopes (e.g. `accounting.transactions.read`, `accounting.reports.read`) | 3: OAuth 2.0 with short-lived access tokens and rotating refresh tokens; daily and per-minute rate limits per tenant; HMAC-signed webhooks | Medium: financial data; writes (invoices, payments) are high-consequence | 3.0 |
| QuickBooks Online (Intuit) | 2 now; weaker UK share than Xero | 2: `com.intuit.quickbooks.accounting` is a single broad scope | 3: OAuth 2.0 with refresh-token rotation, per-realm limits, app review for production | Medium; broad scope makes least privilege hard | 2.5 |

## 3. Recommendation: build **SharePoint/OneDrive document library sync, read-only, via Microsoft Graph with `Sites.Selected`** first

Reasons:

1. **It strengthens the product that already works.** Document Q&A is the verified first-release
   capability. A connector that keeps a chosen SharePoint library in sync with a RAG collection
   removes manual uploads and gives immediate customer value. Mail, Xero and QuickBooks would each
   need a new product surface.
2. **It has the best least-privilege story.** With `Sites.Selected`, the customer's admin grants
   the app access to one named site or library, not the whole tenant. That maps cleanly onto our
   `TenantContext` + `documents:read` scope, and it is easy to explain in a security review.
3. **It is read-only.** No write scope is needed for v1, so the approval gate is not on the
   critical path, and the worst-case failure is stale or missing documents rather than a wrong
   email or invoice.
4. **It fits the business strategy.** Line C ("Managed IT, Microsoft 365 and AI implementation") and
   most UK SMB targets already run Microsoft 365, so the same Entra app pattern unlocks Outlook,
   Teams and Graph-based posture reviews later.
5. **The operational pieces are well understood.** Delta queries give incremental sync with
   cursors (our `iterate_pages`), Graph throttling returns `Retry-After` (our `RateLimited`), and
   change notifications need validation and `clientState` checks (our webhook hook point).

Minimum viable scope for that first connector (not started; needs approval):

- One Entra app per environment, application permission `Sites.Selected` only, granted per site
  by the customer admin. No `*.ReadWrite*`, no `Files.Read.All`.
- Operations: `list_drive_items` (delta, paginated), `download_item` (size cap matching
  `rag/document_library.MAX_UPLOAD_BYTES`, extension allowlist matching RAG), with a sync job that
  writes to that tenant's own managed collection only.
- Store the client secret (or, better, a certificate) via `FileSecretProvider` on a tmpfs or secret
  store, never in the repo or env dumps; audit every sync.
- Deletions in SharePoint mark documents for removal from the collection and are verified with the
  existing `verify_document_removed`.
- Prerequisites from the security review: per-tenant gateway credentials and collection ACLs
  (finding H-3), and the console exposure fix (finding C-1).

**Defer:** Outlook (high personal-data risk, and sending is a consequential write), Google
Workspace (start only if a pilot customer is Google-first; restricted-scope verification costs time),
and Xero, which is the better of the two accounting options for UK customers when finance ops is
validated. QuickBooks has the weakest least-privilege options.

## 4. What is explicitly not claimed

- No Microsoft, Google, Xero or Intuit API has been called. No app registrations exist.
- The fake connector proves the framework's control flow, not provider behaviour (throttling
  semantics, delta-token expiry, permission edge cases).
- This is not a compliance or vendor-security assessment.
