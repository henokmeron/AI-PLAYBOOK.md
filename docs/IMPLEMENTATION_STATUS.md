# Implementation status

Checked 2026-10-20. Before this note, local `main` and GitHub `main` were both `f7af785ca3058c62f627082903c962471ea9650d`. A row is not “working in production” unless the Deployed column has evidence. Unit tests are not a customer endpoint test. A push is not a deployment. Missing configuration is **NOT CONFIGURED** or **UNKNOWN**, never **HEALTHY**.

| Capability | In code | Tested locally | Real Windows | Real external service | GitHub `main` | Deployed |
| --- | --- | --- | --- | --- | --- | --- |
| Loopback console, gateway, helpdesk, RAG, Operations Centre | Yes | Earlier suites passed | Not a Windows product test | No | Yes, through `46e184c` and later repair commits | **NOT VERIFIED**. Pod was not contacted for this increment. |
| Director report | Yes. Includes `operator_auth` and `repair_jobs`. A missing operator file is NOT CONFIGURED. A missing device last-seen is UNKNOWN. A last-seen older than one day is DEGRADED. Password hashes are omitted. | `ops_centre.tests.test_director` and the repair-job cases in `windows_repair.tests.test_live_diagnostics` | No | No | This commit, parent `f7af785ca3058c62f627082903c962471ea9650d` | **NOT VERIFIED** |
| Repair job lifecycle | Yes. A device job is `issued`, then `accepted` after a read-only check, or `expired` when the signature is still valid and the time limit has passed. The state file stays outside the source tree. Enrolment does not grant repair authority. | Lifecycle tests use a mock collector. They do not repair this PC. | The existing disk and printer collectors can still run read-only on this PC. This lifecycle change was not a repair. | No | This commit, parent `f7af785ca3058c62f627082903c962471ea9650d` | **NOT DEPLOYED** |
| Windows repair catalogue and live read-only diagnostics | Yes | Yes, including `test_live_diagnostics` | Yes. 2026-10-19: disk, printers, network, and devices on this PC. 2026-10-20: disk and printer collectors ran again on this PC. `problem_resolved` false. No service was restarted. | No | Collectors were already on `main` before this commit | **NOT VERIFIED** |
| Enrolled endpoint read-only checks | Yes. The worker can submit the eight registered read-only checks. Enrolment does not grant repair authority. Fixture evidence is rejected. | `integrations.tests.test_endpoint` passed, including director coverage. | Not run as a separate enrolled endpoint. A report from this PC would be this PC, not a customer. | No | `bee8d224360bb0910053d1b71301cb71261f1db7` | **NOT DEPLOYED** |
| Source release package | Package of `5ce5f821d1c5d086c57e1905faf06abf6dc752ac`. SHA-256 `fb91c7cc250a01857afab9725042c440756dd087a76f45280447ae01481d61e5`. Saved at `%LOCALAPPDATA%\AI-PLAYBOOK\releases\5ce5f821d1c5d086c57e1905faf06abf6dc752ac\`. Extracted to a clean temp directory and `START.sh` was present. Model weights are not in the package. | `ops.test_release_package` passed (3) during packaging. | No | GitHub Release was not created because `gh` is not installed. Persistent volume copy was not verified. | Package commit `5ce5f82`; this note follows it | **NOT DEPLOYED** |
| Printer spooler approval practice path | Yes | `test_printer_restart_needs_a_different_approver_and_does_not_run` passed | The practice path uses a fixture. Live spooler was Running earlier. No restart was run. | No | `f1599ec` is on GitHub `main` | **NOT CONFIGURED** for an elevated test machine |
| Remote desktop | MeshCentral 1.2.6 boundary only | Session request stays `not_established` | No | No MeshCentral server | Yes | **NOT CONFIGURED** |
| Named operator login | Yes: scrypt passwords, roles admin/operator/viewer, HttpOnly session cookie, CSRF, Host/Origin checks, fail-closed when no operators exist | `web.test_auth` passed (20) after login hardening. `web.test_server` passed (45) before the two extra auth tests. Repair, director, and endpoint regressions passed (36). | No | No | `a9d8a1cebafb6db23eda1515eb0bcdfd03b9d36c` | **NOT DEPLOYED** |
| Microsoft 365 mail | Code present | Mocked console tests | No | `MICROSOFT_CLIENT_ID` unset | Yes | **NOT CONFIGURED** |
| RunPod Qwen | Scripts exist | Not run this increment | No | Pod was not started or stopped | Source is on GitHub | **UNKNOWN**. No health check was made. |

## Deployment blocker

Console-only deploy is `CONSOLE_RESTART_APPROVED=yes bash /tmp/AI-PLAYBOOK/ops/release/deploy-console-only.sh` on the Pod, and only when Qwen and the gateway are already healthy. It also requires `operators.json` in `OPERATOR_AUTH_DIR` before it replaces the console.

Exact blocker: `%USERPROFILE%\.ssh\id_ed25519` is not on this PC. The Pod was not contacted and was not started. No health check was made. Deployed commit: **not verified**.

`START.sh`, `deploy-console-only.sh`, and `snapshot-published-tip.sh` now default `PLATFORM_BRANCH` to `main`. GitHub `feature/qwen3.5-27b-integration` is `ec61ac5a548165914dcbf57a32928d595a86399c`, which is not this `main`. That branch was not updated.

Pre-shutdown checkpoint for package `5ce5f821d1c5d086c57e1905faf06abf6dc752ac` returned **BLOCKED**. The local archive checksum was verified. The Pod was not contacted. `READY_TO_SHUTDOWN` was not declared.
