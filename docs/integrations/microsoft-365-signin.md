# Microsoft 365 read-only sign-in

This is the first real Microsoft connection. It is not connected. No Entra
application was created, no application id is stored in this repository, no
account has consented, and no request has reached Microsoft Graph.

The running console on the Pod is still commit `98511df`. Publishing this file
to GitHub does not deploy it.

## What the code does

1. The Agent page links to `/api/microsoft/start` only after `MICROSOFT_CLIENT_ID` is set. Without it, sign-in returns HTTP 409 and does not redirect.
2. The console redirects the browser to `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize` with `prompt=select_account`.
3. The request is an authorization-code flow with PKCE (`S256`). There is no client secret and no client assertion. The code verifier stays on the server for ten minutes and is single-use.
4. The redirect URI must be exactly `http://127.0.0.1:18080/api/microsoft/callback` (or `http://localhost` with a port and that same path). A public redirect is rejected.
5. The callback checks `state`. The authorization code is not written to the access log. Microsoft returns the browser to the tunneled console. The console exchanges the code, then calls `GET https://graph.microsoft.com/v1.0/me`.
6. The access token and refresh token stay on the server. The default file is `/tmp/microsoft-365-token.json`, created with mode `0600`. On Linux a group- or world-readable file is not loaded. The path cannot be inside this repository or under `/workspace`, so a volume snapshot does not keep the mailbox token. The browser receives the account address and connection status only.
7. The connection record grants `mail:read` only when the token's scope list contains `Mail.Read`. Search and read then go through `Catalog.execute` as `m365_search_mail` and `m365_read_mail`. An empty search says that nothing matched. A Graph rejection is reported without the response body.
8. Message ids are URL-encoded, including `/`, which real Graph ids contain. Send, draft, Teams, files, and calendar operations do not call Graph, even when `authorised=True` or when someone edits the connection record.

The redirect host is the laptop tunnel, not a public address. The SSH tunnel
must be `ssh -N -L 18080:127.0.0.1:8080 -p 11165`. Keep the console on
`127.0.0.1`. Microsoft ignores the port when matching a `localhost` redirect,
but `127.0.0.1` must match exactly. The portal's redirect text box rejects
`http://127.0.0.1`, so that URI is added in the application manifest.

## Exact registration

The Cursor browser reached Entra and was shown Microsoft's sign-in page. No
application was created. Sign in yourself at the Microsoft Entra admin center
and create **one** app registration, only if an app named `Business AI local`
is not already there:

- Name: `Business AI local`
- Supported account types: accounts in any organizational directory and personal Microsoft accounts
- Do not create a client secret

In the application manifest, set:

- `allowPublicClient` to `true`
- `replyUrlsWithType` to one entry whose `url` is `http://127.0.0.1:18080/api/microsoft/callback` and whose `type` is `InstalledClient`

Add delegated Microsoft Graph permissions and nothing else:

- `User.Read`
- `Mail.Read`

Do not add `Mail.Send`, `Mail.ReadWrite`, `Files.ReadWrite`, or admin consent
for the whole tenant. Do not paste the Application (client) ID into chat or
into a file in this repository.

Copy the Application (client) ID and set it as `MICROSOFT_CLIENT_ID` in the
console process environment when the restart below is approved. Leave
`MICROSOFT_TENANT` as `common` unless the organisation requires one directory.
Leave `MICROSOFT_TOKEN_FILE` at `/tmp/microsoft-365-token.json`.

## Agent documents

The Agent page can search the same on-disk library as Document Q&A
(`/workspace/rag-demo-docs`, or a named collection under
`/workspace/rag-managed-docs`). The tool returns passages, file names, and
`abstained` when the library does not cover the question. Passages that look
like instructions are labelled as document data. The standalone Document Q&A
API is unchanged. File attachments on the Agent page are not supported and are
not indexed.

This retrieval runs in the console process. It is not on the running console
until that process is replaced.

## Approval required before a restart

Do not do this until the owner agrees. It was not done in this session.

`bash /workspace/ai-platform-release/START.sh --start` is the wrong command
while the stack is healthy. That launcher reuses a healthy Qwen, gateway, and
console, so the new code would not load, and a cold Qwen start is the
expensive path (last cold load was about 1080 seconds at $1.79/hour).

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
