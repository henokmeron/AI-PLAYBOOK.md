# Integration inventory and storage — 2026-10-14

No extra plugins or runtimes were downloaded for this inventory. Sizes below were measured on this Windows PC, except the RunPod volume, which was not measured again. The 2026-10-14 read-only audit remains the volume figure: **126.03 GB**, one Gemma checkpoint, one Qwen checkpoint, two runtime archives, and about 177 MB of other files. Those files stay where they are.

## Storage on this PC

| Location | Measured |
| --- | --- |
| Windows `C:` | 328.6 GB used, **181.1 GB free** |
| Windows `G:` | 11.3 GB used, **4.8 GB free** |
| Cursor plugin cache `github` (older copy) | 6,128 bytes |
| Cursor plugin cache `gmail` (older copy) | 4,737 bytes |
| Cursor plugin cache `lovable` | 19,528 bytes |
| Cursor plugin cache `teams` after the repair | 5,796 bytes |

The first platform phase adds a few kilobytes of Python and documentation in Git. It does not copy model weights, install Node services, or add a database. Estimated extra disk for the phase: **under 1 MB**.

## How the three layers stay separate

Cursor plugins help development. They are not part of the deployed console. The platform has its own agent, tool list, and connector catalog. External products are reached only by a connector that passes scope and approval checks. The Teams plugin fails that test because its URL is Cursor's service.

## First set to build

1. **Connector catalog and Agent page.** Done in this change. Microsoft 365 is listed and disconnected. The agent can run the existing calculator. Consequential tools pause for approval. Local tests passed. Not deployed to the Pod.
2. **Microsoft Graph, read-only mail and files, after you consent.** One Entra app, delegated `Mail.Read` and `Files.Read` first. Drafts use `Mail.ReadWrite` and do not send. Sending uses `Mail.Send` and needs approval. Teams channel reads often need an administrator to consent to `ChannelMessage.Read.All`. Do not request every Graph permission on the first sign-in.
3. **Leave the rest as a catalogue.** Do not install Xero, QuickBooks, Slack, Jira, or the others until one Microsoft read path works.

## Catalogue

Official APIs only. "Plugin" means a Cursor marketplace package, which stays in Cursor. Storage for each of these code connectors is expected to be well under 50 MB until a vendor SDK is chosen. None of those SDKs were installed.

| Priority | Service | API | Auth | First operations | Main limit |
| --- | --- | --- | --- | --- | --- |
| 1 | Microsoft 365 mail, files, calendar, Teams | Microsoft Graph | Delegated OAuth | Read, then draft, then approved send | Admin consent for some Teams channel reads |
| 2 | Google Gmail and Drive | Gmail API, Drive API | Google OAuth | Read mail and files | Cursor's Gmail plugin is also Cursor-only |
| 3 | GitHub | GitHub REST or official MCP | Fine-grained token or OAuth | Read issues and pull requests | Already used for this repo; not a customer connector yet |
| 4 | Xero, QuickBooks Online | Official accounting APIs | OAuth | Read an invoice | Separate apps and sandbox companies |
| 5 | Slack | Slack Web API | OAuth | Read a channel | Posting needs approval |
| 6 | Jira, Linear | Official REST | OAuth | Read an issue | Do not treat them as the same product |
| 7 | Salesforce, HubSpot | Official CRM APIs | OAuth | Read a contact | Easy to over-request scopes |
| Later | Sage, Asana, Trello, Monday, LinkedIn, Meta, WordPress, Shopify, Zoom, n8n, Zapier | Each product's own API | Varies | Not chosen | Sage products do not share one API. Social posting has extra review rules. |

Browser automation is a last resort and is not part of this phase.

## How to add a connector

1. Add a `ConnectorSpec` with a stable id, version, and one scope per operation.
2. Mark reads and drafts as not requiring approval. Mark anything that sends, deletes, publishes, or changes a record as consequential, which forces approval.
3. Register it in `platform_catalog()`. The performer must raise before any network call when the account is missing.
4. Give the agent only operations whose scope is on the connection record. Do not register the others.
5. Add a unit test that a missing approval and a missing account both leave the network counter at zero.

