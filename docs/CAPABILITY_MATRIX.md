# Capability matrix

Statuses mean:

- **IMPLEMENTED AND TESTED** — code and automated tests exist in this tree. Not a live Pod claim.
- **IMPLEMENTED BUT NOT LIVE-VERIFIED** — code exists; this session did not prove it on a running Pod.
- **PARTIAL** — some of the behaviour exists.
- **MISSING** — not built.
- **BLOCKED** — needs credentials, a running Pod, or a decision this session must not make.

Checked 2026-10-22 against the local `main` working tree and a read-only portal pass. Named operator login is in this tree. It is not a live Pod claim. The saved Entra redirect was re-read on Authentication (Preview).

The machine-readable registry is `windows_repair/capabilities.py`. Its statuses are PASS, PARTIAL, FAIL, NOT IMPLEMENTED, BLOCKED, and NOT VERIFIED. Windows read-only diagnostics are not Mac, Android, iPhone, or web-device support. There is no macOS, Android, or iOS agent in this repository. Web control is the loopback console only.

| Capability | Status | Evidence |
| --- | --- | --- |
| Loopback console (chat, documents, status) | IMPLEMENTED BUT NOT LIVE-VERIFIED | `web/server.py`, `web/test_server.py` |
| Model gateway | IMPLEMENTED BUT NOT LIVE-VERIFIED | `api/local_gateway.py` |
| Qwen on RunPod | BLOCKED | Pod was left running earlier; this session did not SSH or restart it |
| IT Helpdesk agent and approvals | IMPLEMENTED BUT NOT LIVE-VERIFIED | `agents/`; prior live note is in `docs/results/`, not re-run here |
| RAG answers with citations / abstention | IMPLEMENTED BUT NOT LIVE-VERIFIED | `rag/`, `api` conversation tests; not re-run here (no Python on this PC) |
| Operations Centre probes, alerts, incidents | IMPLEMENTED AND TESTED in source | `ops_centre/`, `ops_centre/tests/test_ops_centre.py` |
| Director on-demand report | IMPLEMENTED AND TESTED in source | `ops_centre/director.py`, `ops_centre/tests/test_director.py` — tests not executed on this PC |
| Scheduled Director reports | PARTIAL | `ops_centre/director_schedule.py` can run on a file interval. No cron daemon ships with the Pod. |
| Named operator login, CSRF, roles | IMPLEMENTED AND TESTED in source | `web/auth/`, `scripts/provision_console_operator.py`, `web/test_auth.py`. First admin is created with the provision script. No default password. Not deployed. |
| Microsoft mail search/read | PARTIAL | Code in `integrations/microsoft_oauth.py` requests delegated `User.Read` and `Mail.Read`. Mock-tested. Authentication (Preview) has saved Mobile and desktop redirect `http://127.0.0.1:18080/api/microsoft/callback` for single-tenant directory `d595636e-9ef4-4890-b8a7-bde8dd5cab03`. No mailbox was read. **NOT CONFIGURED**. |
| Teams, SharePoint, OneDrive, Azure inventory reads | PARTIAL | Registered and mock-tested. Live Graph/ARM still need Entra consent. Writes stay disabled. |
| Microsoft / Azure writes | MISSING | Send mail and resource changes stay unavailable. Unsent drafts need `Mail.ReadWrite` via `access=draft`. |
| Windows repair catalogue and signed jobs | IMPLEMENTED AND TESTED in source | `windows_repair/`. On 2026-10-22 the development PC ran the registered read-only collectors, including activation, USB, Wi-Fi, proxy, TLS, browser, permissions, and crash evidence. That PC is not a customer endpoint. `problem_resolved` stayed false. Elevated spooler restart is not run here. |
| Remote PC control | PARTIAL | MeshCentral 1.2.6, Apache-2.0, is the selected boundary. No server is installed and no remote desktop session has been opened. |
