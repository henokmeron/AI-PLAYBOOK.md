# Microsoft 365 read-only sign-in

Checked again on 2026-10-21 from this workstation. No browser Microsoft
session was available to the agent, `MICROSOFT_CLIENT_ID` was unset, and no
Graph call was made. The connectors stay **NOT CONFIGURED**.

This is the first real Microsoft connection. It is not connected. No Entra
application was created, no application id is stored in this repository, no
account has consented, and no request has reached Microsoft Graph.

On 2026-10-15 the paid Pod was `1g41ejmd99iyun` (“brand new pod”), not the
older checkout. SSH `root@216.81.248.126 -p 19091` answered. Qwen `:8002`,
the gateway `:8010`, and the console `:8080` did not. `/tmp/AI-PLAYBOOK` was
absent. The same Global Volume was mounted and the Qwen weights were present.
Publishing this file does not deploy it, and `MICROSOFT_CLIENT_ID` was unset.

## What the code does

1. The Agent page offers three Microsoft sign-in choices. Each one is a real link:
   - `?account=any` uses the `common` directory (work, school, or personal)
   - `?account=work` uses `organizations`
   - `?account=personal` uses `consumers`
   The browser cannot choose an arbitrary directory. If `MICROSOFT_TENANT` is one organisation, that directory is the only choice. Without `MICROSOFT_CLIENT_ID`, sign-in returns HTTP 409 and does not redirect.
2. The console redirects the browser to `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize` with `prompt=select_account`.
3. The request is an authorization-code flow with PKCE (`S256`). There is no client secret and no client assertion. The code verifier stays on the server for ten minutes and is single-use.
4. The redirect URI must be exactly `http://127.0.0.1:18080/api/microsoft/callback` (or `http://localhost` with a port and that same path). A public redirect is rejected.
5. The callback checks `state` and exchanges the code only when both the code and the state are present. A missing or reused state, a cancelled consent (`access_denied`), or any other Microsoft error returns an HTML page. That page does not repeat Microsoft's error text. The browser is sent to the Agent page. An empty redirect is not used, because Chrome shows an empty `/api/` response as a blank JSON viewer. The authorization code is not written to the access log. After a valid code, the console calls `GET https://graph.microsoft.com/v1.0/me` and only then records the account.
6. The access token and refresh token stay on the server. The default file is `/tmp/microsoft-365-token.json`, created with mode `0600`. On Linux a group- or world-readable file is not loaded. The path cannot be inside this repository or under `/workspace`, so a volume snapshot does not keep the mailbox token. The browser receives the account address and connection status only.
7. The connection record grants `mail:read` when the token includes `Mail.Read`, and `mail:write` when it includes `Mail.ReadWrite`. Search and read go through `Catalog.execute` as `m365_search_mail` and `m365_read_mail`. An approved `m365_create_mail_draft` creates an unsent draft only. An empty search says that nothing matched. A Graph rejection is reported without the response body.
8. Message ids are URL-encoded, including `/`, which real Graph ids contain. `Mail.Send`, Teams send, and calendar changes stay disabled even when `authorised=True`. Teams, OneDrive, SharePoint, and Azure inventory reads are registered and mock-tested. Live Graph and ARM calls still need `MICROSOFT_CLIENT_ID` and consent.

The redirect host is the laptop tunnel, not a public address. The mapped SSH
port changes when the Pod is recreated. The port seen on 2026-10-15 was
`19091` on `216.81.248.126`. The tunnel shape is
`ssh -N -L 18080:127.0.0.1:8080 -p <mapped-port>`. Keep the console on
`127.0.0.1`. Microsoft ignores the port when matching a `localhost` redirect,
but `127.0.0.1` must match exactly. The portal's redirect text box rejects
`http://127.0.0.1`, so that URI is added in the application manifest.

## Exact registration

On 2026-10-15 the Entra app-registration blade was signed in with a personal
Microsoft account. The portal returned AADSTS16000: that live.com account is
not a member of the Microsoft Services tenant, so the application list did not
load. No application named `Business AI local` could be confirmed, and none
was created. Sign in with a work or school account that can open App
registrations, then create **one** app only if that name is not already there:

- Name: `Business AI local`
- Supported account types: accounts in any organizational directory and personal Microsoft accounts
- Do not create a client secret

In the application manifest, set:

- `allowPublicClient` to `true`
- `replyUrlsWithType` to one entry whose `url` is `http://127.0.0.1:18080/api/microsoft/callback` and whose `type` is `InstalledClient`

Add delegated Microsoft Graph permissions:

- `User.Read`
- `Mail.Read`
- `Chat.Read`
- `Files.Read`
- `Sites.Read.All` (may require admin consent)

For read-only Azure inventory, also add the Azure Service Management delegated
permission `user_impersonation`. Do not add `Mail.Send`, `Mail.ReadWrite`,
`Files.ReadWrite`, or Azure write roles. Do not paste the Application (client)
ID into chat or into a file in this repository.

Until `MICROSOFT_CLIENT_ID` is set and an account consents, the connectors stay
**NOT CONFIGURED**. Offline contract tests use an in-memory transport and are
not a live Microsoft connection.

Copy the Application (client) ID and set it as `MICROSOFT_CLIENT_ID` in the
console process environment when the restart below is approved. Leave
`MICROSOFT_TENANT` as `common` unless the organisation requires one directory.
Leave `MICROSOFT_TOKEN_FILE` at `/tmp/microsoft-365-token.json`.

## Agent documents

The Agent page shows the runner's execution state (received, investigating, awaiting information, awaiting approval, executing, verifying, completed, failed, escalated, or cancelled), the tool it used, and the exact approval target (tool name, call id, and arguments). It does not invent steps. The catalog labels each operation `implemented`, `mock-tested`, `live-tested`, `unavailable`, or `disconnected`. Mail search and read are mock-tested. They are not live-tested. Send and the other writes are unavailable. The local document search and calculator rows are also mock-tested; an older live calculator check on commit `98511df` was not repeated.

A paused task can be cancelled or given more information from the Agent page. Cancelling does not call Microsoft. An interrupted tool call is not run a second time when the task is restored.

The Agent page can search the same on-disk library as Document Q&A
(`/workspace/rag-demo-docs`, or a named collection under
`/workspace/rag-managed-docs`). The tool returns passages, file names, and
`abstained` when the library does not cover the question. Passages that look
like instructions are labelled as document data. The standalone Document Q&A
API is unchanged. File attachments on the Agent page are not supported and are
not indexed.

This retrieval runs in the console process. It is not on the running console
until that process is replaced.

## Console replacement

A console-only replacement was requested earlier on 2026-10-15 and was not done then. It was not done in this session either.

`ops/release/deploy-console-only.sh` is the guard. Without `CONSOLE_RESTART_APPROVED=yes` it only prints a dry run. With that variable it still refuses unless Qwen `:8002` and the gateway `:8010` already return HTTP 200, and it does not signal those processes. On Pod `1g41ejmd99iyun` both ports were down, so the script would refuse. It was not executed.

`bash /workspace/ai-platform-release/START.sh` would cold-start Qwen. The last cold load was about 1080 seconds. The Pod is already billing at $1.79/hour with the GPU idle, and the balance was about $4.89. That start was not run.

What may stop: **only the console process** on `127.0.0.1:8080`. Do not stop
Qwen on `127.0.0.1:8002`. Do not stop the gateway on `127.0.0.1:8010`. Do not
delete `/workspace/models`, the runtime archive, snapshots, or
`/workspace/rag-managed-docs`.

Recovery if the new console fails to bind: Qwen and the gateway are still up.
Start the console again from the updated checkout with the same environment
the launcher uses (`WEB_HOST=127.0.0.1`, `WEB_PORT=8080`,
`PLATFORM_GATEWAY_URL=http://127.0.0.1:8010`, the existing key file, and
`PLATFORM_MODEL_ID=qwen3.5-27b`). If the whole stack is ever down, the
recovery command remains `bash /workspace/ai-platform-release/START.sh`.
`MICROSOFT_CLIENT_ID` must be supplied by the owner in that environment. Do
not write a placeholder id into the Pod.

After that console is up, open `http://127.0.0.1:18080/#agent` through the
tunnel and consent. Only then is a mailbox search a real Graph request.

## Next connectors, not built

These are separate permissions and products. None of them run here.

- **Teams.** Delegated `Chat.Read` can read the signed-in user's chats. Channel messages use `ChannelMessage.Read.All`, which needs an administrator to consent. Sending is a different permission and stays disabled.
- **OneDrive.** Delegated `Files.Read` can list and download files the user can already open. Not requested.
- **SharePoint.** Searching site collections is `Sites.Read.All`, a broader read than one user's drive. Not requested.
- **Calendar.** Delegated `Calendars.Read` and `GET /me/calendarView`. Not requested.
- **Excel.** Microsoft Graph's worksheet `usedRange` lists `Files.ReadWrite` as the least privileged permission even for a GET. Do not call that API for a read-only agent. A downloaded `.xlsx` can be read with `Files.Read` and the local parser already used by Document Q&A. That path is not wired.
- **Gmail and Google Workspace.** Gmail read is the restricted scope `https://www.googleapis.com/auth/gmail.readonly` and needs Google's own verification. Drive is a separate scope. Not started.
- **Xero.** An app created after 2 March 2026 uses granular scopes such as `accounting.invoices.read`, not the older broad accounting scope. Not started.
- **QuickBooks Online.** `com.intuit.quickbooks.accounting` is not a read-only scope. A connector would have to refuse writes in this platform even after consent. Not started.
- **Sage.** Sage Business Cloud Accounting, Sage 50, and Sage Intacct do not share one API. Not started.

The Cursor Teams plugin is not part of this platform.
