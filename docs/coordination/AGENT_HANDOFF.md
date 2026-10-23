# Agent handoff

Read this file before starting. Append to the log when you finish. Do not delete log entries. Only the Director moves the old CURRENT block into the log and writes a new CURRENT block.

## CURRENT

Updated: 2026-10-23T16:15Z

The owner started a new RunPod pod because the previous A100, gom4ualdk47qrj, could not get its GPU. The new pod is 1jyrnyxpb0n93s, name continuous_green_cephalopod, A100-SXM4-80GB, about $1.80/hr. The existing Global Volume is mounted at /workspace. Weights are at /workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654. SSH for this pod: root@195.26.233.96 port 48443. The console on the owner's PC is http://127.0.0.1:18080/ through an SSH tunnel to the pod's 127.0.0.1:8080. That page is blank until the console process is listening.

Preflight passed at 2026-10-23T14:55:25Z: A100 81920 MiB, driver major 595, ports 8002, 8010, and 8080 free, runtime archive present. START.sh was then started and was restoring the runtime into /tmp/vllm-qwen-env. Source checked out by that start was f38cbef. GitHub main at the last save before this file was cf92c292b31698661658abdd5f90341c444f17ba. Confirm both SHAs before trusting them.

Acceptance was 4/9 overall and 4/8 mandatory. Production is NO-GO. Microsoft content match is not proven. The second Windows PC is not enrolled. Fresh recovery on this same PC does not close that gate. Model weights were not copied.

Next safe work: finish bringing up this pod's console, then continue product work that does not need a new GPU or a weight copy.

## LOG

- 2026-10-23T16:15Z Liaison file created. No product code in this commit. Cursor was starting the new pod. The local page was down because no tunnel was listening; a tunnel to port 18080 was opened from the owner's PC.
- 2026-10-23T15:52Z (Agent) Endpoint hardening commit dfaeecb on cursor/endpoint-hardening-59b5. DPAPI secret storage (Windows), redaction before upload, schema_version/agent_version in reports, expanded docs (troubleshooting, upgrades, revocation, recovery, uninstall, supported Windows versions, code-signing options, repair proposal workflow). Tests: 22 new in test_endpoint_hardening.py (all pass), 18 existing in test_endpoint.py (all pass). Mock-tested only; no real second Windows PC enrolled. Second endpoint gate remains open. Remote repair is NOT production-ready. Contract freeze honored: two separate stacks (diagnostics/repair), allowlist updated for schema_version/agent_version, public fields unchanged, repair_authority=false, no Console UI changes, no privileged commands. Known limitations: DPAPI requires re-enrol if user profile lost, redaction is pattern-based (may miss some PII), repair execution not implemented on endpoint. Rollback: revert commit, secrets stay private-file only. Next: PR review, second Windows PC enrolment, real-device evidence. Security decisions: DPAPI user-scope, no admin required, redaction always on, TLS verification required, no command injection, revocation immediate, no automatic repair.
- 2026-10-23T18:23Z (Agent) Console UI improvements commit 3eb833c on cursor/console-device-ui-improvements-b0c8. Device list now shows diagnostic_coverage, evidence_age/stale, optional schema_version/agent_version (backward-compatible with main branch). Secrets (device_secret, mac_key) cleared from DOM 60s after one-time display. Enrolment button disabled during code generation. Readable errors for 401/403/503 on device routes. Repair view clarifies approval required, remote execute unavailable, repair_authority OFF. Tests: 3 new in test_server.py (all pass), 37 total ConsoleTests pass. No secrets in UI after display. No fake metrics. No execute endpoints. Contract freeze honored: no route renames, no public field changes. Limitations: Second PC not enrolled, no live device evidence, UI field rendering tested with mocks only. Rollback: revert commit. Next: PR review, test with PR #8 fields when merged, second PC enrolment. UI changes: web/static/app.js (device/repair displays), web/test_server.py (coverage/timing/empty-state tests).
