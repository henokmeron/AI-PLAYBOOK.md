# Microsoft 365 read-only sign-in

This is the first real Microsoft connection. It is not connected until an Entra
application exists, the console is started with that application id, the owner
consents, and a Graph request succeeds. No application id is stored in this
repository.

## What the code does

1. The Agent page links to `/api/microsoft/start` only after `MICROSOFT_CLIENT_ID` is set.
2. The console redirects the browser to `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize`.
3. The request is an authorization-code flow with PKCE. There is no client secret.
4. Microsoft returns the browser to `http://127.0.0.1:18080/api/microsoft/callback`.
5. The console exchanges the code at the token endpoint, then calls `GET https://graph.microsoft.com/v1.0/me`.
6. The access token and refresh token stay on the server. The default file is `/tmp/microsoft-365-token.json` with mode `0600`. The browser receives the account address and connection status only.
7. Search and read use delegated `Mail.Read`. The connection record grants only `mail:read`.
8. Send, Teams, files, and calendar operations do not call Graph. A missing scope or a missing approval stops them before any request.

The redirect host is the laptop tunnel, not the Pod's port 8080. The SSH tunnel
must be `ssh -N -L 18080:127.0.0.1:8080 -p 11165`. The running console on the
Pod does not have this code until a later approved restart.

## Exact registration

In the Microsoft Entra admin center, create an app registration:

- Name: `Business AI local`
- Supported account types: accounts in any organizational directory and personal Microsoft accounts
- Redirect URI platform: **Public client / native (mobile & desktop)**
- Redirect URI: `http://127.0.0.1:18080/api/microsoft/callback`

Add delegated Microsoft Graph permissions and nothing else:

- `User.Read`
- `Mail.Read`

Do not add `Mail.Send`, `Mail.ReadWrite`, or admin consent for the whole tenant.

Copy the Application (client) ID. Set it on the Pod as `MICROSOFT_CLIENT_ID`
for a future approved console start. Do not put it in source code or chat.
Leave `MICROSOFT_TENANT` as `common` unless the organisation requires one
directory. The token file must stay on `/tmp`, not on `/workspace`.

## After that restart

Open the tunneled console, choose Connect Microsoft 365, and approve the
consent screen. The Agent page should then show the mailbox address. Only then
is a live mailbox search a real Graph request.
