# Capability matrix

Statuses mean:

- **IMPLEMENTED AND TESTED** — code and automated tests exist in this tree. Not a live Pod claim.
- **IMPLEMENTED BUT NOT LIVE-VERIFIED** — code exists; this session did not prove it on a running Pod.
- **PARTIAL** — some of the behaviour exists.
- **MISSING** — not built.
- **BLOCKED** — needs credentials, a running Pod, or a decision this session must not make.

Checked against GitHub `main` downloaded 2026-10-18, plus the Director files added in this working copy. Operator-auth PR 4 was **not** merged into this tree.

| Capability | Status | Evidence |
| --- | --- | --- |
| Loopback console (chat, documents, status) | IMPLEMENTED BUT NOT LIVE-VERIFIED | `web/server.py`, `web/test_server.py` |
| Model gateway | IMPLEMENTED BUT NOT LIVE-VERIFIED | `api/local_gateway.py` |
| Qwen on RunPod | BLOCKED | Pod was left running earlier; this session did not SSH or restart it |
| IT Helpdesk agent and approvals | IMPLEMENTED BUT NOT LIVE-VERIFIED | `agents/`; prior live note is in `docs/results/`, not re-run here |
| RAG answers with citations / abstention | IMPLEMENTED BUT NOT LIVE-VERIFIED | `rag/`, `api` conversation tests; not re-run here (no Python on this PC) |
| Operations Centre probes, alerts, incidents | IMPLEMENTED AND TESTED in source | `ops_centre/`, `ops_centre/tests/test_ops_centre.py` |
| Director on-demand report | IMPLEMENTED AND TESTED in source | `ops_centre/director.py`, `ops_centre/tests/test_director.py` — tests not executed on this PC |
| Scheduled Director reports | MISSING | No job runner. Documented in `docs/ops_centre/DIRECTOR.md` |
| Named operator login, CSRF, roles | PARTIAL | Implemented on PR 4, not in this `main` snapshot, not deployed |
| Microsoft mail search/read | PARTIAL | Code in `integrations/microsoft365.py` needs `Mail.Read` and `MICROSOFT_CLIENT_ID`. Not connected |
| Teams, SharePoint, OneDrive, Azure writes | MISSING | See `docs/integrations/m365-azure-roadmap.md` |
| Remote PC control | PARTIAL | MeshCentral boundary only. `MESHCENTRAL_URL` unset means NOT CONFIGURED. No session was opened. |
| Windows repair catalogue and signed jobs | IMPLEMENTED AND TESTED in source | `windows_repair/`, `windows_repair/tests/test_windows_repair.py`. Fixtures are mocked. Elevated repairs are not applied to this PC. |
