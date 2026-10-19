# Implementation status

Checked 2026-10-19 after `git fetch`. Local `main` and GitHub `main` were both `95c6b8a6acb6545fef5775271f6dea19aaa9e88e` before this status note. A row is not “working in production” unless the Deployed column has evidence.

| Capability | In code | Tested locally | Real Windows | Real external service | GitHub `main` | Deployed |
| --- | --- | --- | --- | --- | --- | --- |
| Loopback console, gateway, helpdesk, RAG, Operations Centre | Yes | Earlier suites passed | Not a Windows product test | No | Yes, through `46e184c` and later repair commits | **NOT VERIFIED**. Pod was not contacted for this increment. |
| Director report | Yes. Includes `operator_auth`: missing file is NOT CONFIGURED, no active admin is DEGRADED, and password hashes are omitted. | `ops_centre.tests.test_director` passed (6) | No | No | `95c6b8a6acb6545fef5775271f6dea19aaa9e88e` | **NOT VERIFIED** |
| Windows repair catalogue and live read-only diagnostics | Yes | Yes, including `test_live_diagnostics` | Yes, 2026-10-19: disk, printers, network, and devices on this PC. `problem_resolved` false. | No | `46e184c` is on GitHub `main` | **NOT VERIFIED** |
| Enrolled endpoint read-only checks | Yes. The worker can submit the eight registered read-only checks. Enrolment does not grant repair authority. Fixture evidence is rejected. | `integrations.tests.test_endpoint` passed, including director coverage. | Not run as a separate enrolled endpoint. A report from this PC would be this PC, not a customer. | No | `bee8d224360bb0910053d1b71301cb71261f1db7` | **NOT DEPLOYED** |
| Source release package | `python -m ops.release.make_release` writes a git archive and SHA-256 manifest outside the repo. It does not include model weights. | `ops.test_release_package` | No | Volume copy not verified | This commit, after push | **NOT DEPLOYED** |
| Printer spooler approval practice path | Yes | `test_printer_restart_needs_a_different_approver_and_does_not_run` passed | The practice path uses a fixture. Live spooler was Running earlier. No restart was run. | No | `f1599ec` is on GitHub `main` | **NOT CONFIGURED** for an elevated test machine |
| Remote desktop | MeshCentral 1.2.6 boundary only | Session request stays `not_established` | No | No MeshCentral server | Yes | **NOT CONFIGURED** |
| Named operator login | Yes: scrypt passwords, roles admin/operator/viewer, HttpOnly session cookie, CSRF, Host/Origin checks, fail-closed when no operators exist | `web.test_auth` passed (20) after login hardening. `web.test_server` passed (45) before the two extra auth tests. Repair, director, and endpoint regressions passed (36). | No | No | `a9d8a1cebafb6db23eda1515eb0bcdfd03b9d36c` | **NOT DEPLOYED** |
| Microsoft 365 mail | Code present | Mocked console tests | No | `MICROSOFT_CLIENT_ID` unset | Yes | **NOT CONFIGURED** |
| RunPod Qwen | Scripts exist | Not run this increment | No | Pod was not started or stopped | Source is on GitHub | **UNKNOWN**. No health check was made. |

## Deployment blocker

Console-only deploy is `CONSOLE_RESTART_APPROVED=yes bash /tmp/AI-PLAYBOOK/ops/release/deploy-console-only.sh` on the Pod, and only when Qwen and the gateway are already healthy. It also requires `operators.json` in `OPERATOR_AUTH_DIR` before it replaces the console.

Exact blocker: `%USERPROFILE%\.ssh\id_ed25519` is not on this PC. The Pod was not contacted and was not started. No health check was made. Deployed commit: **not verified**.

`START.sh`, `deploy-console-only.sh`, and `snapshot-published-tip.sh` now default `PLATFORM_BRANCH` to `main`. GitHub `feature/qwen3.5-27b-integration` is `ec61ac5a548165914dcbf57a32928d595a86399c`, which is not this `main`. That branch was not updated.
