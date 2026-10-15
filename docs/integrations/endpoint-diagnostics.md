# Endpoint support

Checked 2026-10-15. Remote screen control is still not installed. A read-only check-in now exists in source. It is not deployed on the Pod, and the catalog still says `mock-tested`, not `live-tested`.

## What was not done

No TeamViewer, Intune Remote Help, or RustDesk package was installed. No device was enrolled on the Pod. No API token was created. The agent cannot start a remote session, and there is no command that runs a repair.

## TeamViewer

TeamViewer documents a Web API for session, meeting, user, group, and reporting calls. Using an integration requires a TeamViewer account and a paid license (their API matrix lists Business, Premium, and Corporate for different calls; a version 11 or later license is required to use an integration). Developing against the API is described as not requiring a license by itself. The EULA lets TeamViewer change or switch off APIs, and it restricts service-bureau, rental, timesharing, and resale use. The free client is not the commercial path for a support business.

A session is still remote control of someone else's computer. This platform must not start one in the background. If it is ever used, the person at the device has to accept the session in TeamViewer, and this product would only hold a reference to a session the vendor already showed them.

Sources: TeamViewer API knowledge-base article; TeamViewer EULA (teamviewer.com/en/legal/eula).

## Microsoft Intune Remote Help

Remote Help is Microsoft's signed-in helpdesk connection for Intune-managed devices. Microsoft's plan page says both the helper and the sharer need a Remote Help license, the device must be Intune-enrolled and registered in Entra, and the feature needs a subscription in addition to Intune Plan 1 or Plan 2. The Intune licensing page lists Remote Help under Plan 2. The public pricing page also shows a Remote Help add-on at $3.50 user/month, while the Remote Help product page says it is included in Microsoft 365 E3 and E5. Those pages do not all use the same words. Confirm the tenant's actual licenses before relying on any one of them. Unattended or role-based help is still an admin-visible Intune feature, not a hidden agent.

This platform does not call Intune. Adding it later would be a separate delegated permission and a separate approval, and it would not be a way to bypass the device user's sign-in.

Sources: `learn.microsoft.com/en-us/intune/remote-help/plan`, `learn.microsoft.com/en-us/intune/fundamentals/licensing`, Microsoft Intune pricing, and the Remote Help product page.

## RustDesk

The open-source RustDesk server is AGPL-3.0. Running a modified copy as a network service can require offering the corresponding source to the people who use that server. RustDesk Server Pro is a separate proprietary license from Purslane Limited: internal business use, one license per `hbbs` machine, annual fee, no copying, resale, sublicensing, or sharing the key. The relay (`hbbr`) is documented as not needing its own license. The vendor has declined to give legal advice on embedding RustDesk in another commercial product. Do not copy RustDesk into this repository, and do not assume the AGPL server can be wrapped in a closed support product without a lawyer.

Sources: `github.com/rustdesk/rustdesk-server` LICENSE, `github.com/rustdesk/rustdesk-server-pro` terms, and RustDesk's Server Pro license page.

## Read-only check-in in source

`integrations/endpoint.py` and `integrations/endpoint_worker.py` implement the first payload only.

- The operator creates a one-time enrolment code in the Agent page. The code is returned once and is not stored in the clear.
- The worker runs on the computer the operator chose. It generates its own secret, sends that secret once, and writes it to a file the operator names. The server stores only a SHA-256 hash.
- Later reports are `POST /api/devices/report` to `http://127.0.0.1` or `http://localhost` with an explicit port. Any other address is refused. The worker does not follow redirects and does not use an HTTP proxy.
- The accepted fields are operating system, disk free and total bytes, memory, and boot time. A `command` field, a path, or any other extra field is rejected. Newlines in the operating-system text are flattened so the text stays data.
- Revocation is an operator button. After revocation the same secret is rejected. Another customer cannot read or revoke the device.
- The agent tool `read_device_diagnostics` appears only after a computer is enrolled. It reads the stored report. It cannot ask the computer to do anything else.
- State defaults to memory. `ENDPOINT_STATE_FILE` may point at an absolute file outside this repository and, on Linux, outside `/workspace`.

Evidence: unit tests, including a real `collect_local_diagnostics()` call on the developer Windows PC, and a loopback console test that rejected a command field and did not echo the device secret. Nothing was posted to the Pod. Do not describe this as a live customer integration.

## First safe diagnostic design

- The device runs a small program the operator installed on purpose. It opens only outbound connections to this platform. It does not listen for inbound control, and it does not install a remote-desktop client.
- The device generates its own secret. The server stores a SHA-256 hash and a display name. The secret stays on the device. Losing the server does not reveal a way to drive the device, because this connector has no command channel.
- The server can revoke that identity. After revocation the worker's next connection is refused and it stops sending. Revocation is an operator action, recorded like any other approval.
- The first payload is a diagnostic the person at the device can read locally before it is sent: operating system, disk free space, and last boot time. No screen capture, no keystroke log, no file contents, no stored passwords.
- A later remote-help session, if the business buys TeamViewer, Intune Remote Help, or a properly licensed RustDesk deployment, starts only after a person at the device accepts it in that product. This agent would record the request and the approval. It would not send the input itself.

The catalog row is `mock-tested` until a check-in is stored on the running console. It must not be marked `live-tested` from unit tests alone. Remote control stays unavailable.
