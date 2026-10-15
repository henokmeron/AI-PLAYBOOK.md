# Endpoint support research — not a connector

Checked 2026-10-15 from public vendor pages. Nothing here is installed, configured, or able to reach a device. Do not treat this note as a working integration.

## What was not done

No TeamViewer, Intune Remote Help, or RustDesk package was installed. No device was enrolled. No API token was created. The catalog has no device connector, and the agent cannot start a remote session.

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

## First safe diagnostic design

This is a design only. There is no worker process.

- The device runs a small program the operator installed on purpose. It opens only outbound connections to this platform. It does not listen for inbound control, and it does not install a remote-desktop client.
- The device generates its own identity key. The server stores the public key and a display name. The private key stays on the device. Losing the server does not give anyone a way to drive the device.
- The server can revoke that identity. After revocation the worker's next connection is refused and it stops sending. Revocation is an operator action, recorded like any other approval.
- The first payload is a diagnostic the person at the device can read locally before it is sent: operating system, disk free space, and last boot time. No screen capture, no keystroke log, no file contents, no stored passwords.
- A later remote-help session, if the business buys TeamViewer, Intune Remote Help, or a properly licensed RustDesk deployment, starts only after a person at the device accepts it in that product. This agent would record the request and the approval. It would not send the input itself.

Until that worker exists, the catalog must keep any device row at `unavailable`.
