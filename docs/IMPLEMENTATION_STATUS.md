# Implementation status

Checked 2026-10-19. Local `main` and GitHub `main` were both `f1599ec8de67ffe75c0acc8bcb72d4e187c1b394` after `git fetch`. A row is not “working in production” unless the Deployed column has evidence.

| Capability | In code | Tested locally | Real Windows | Real external service | GitHub `main` | Deployed |
| --- | --- | --- | --- | --- | --- | --- |
| Loopback console, gateway, helpdesk, RAG, Operations Centre | Yes | Earlier suites passed | Not a Windows product test | No | Yes, through `46e184c` and later repair commits | **NOT VERIFIED**. Pod was not contacted for this increment. |
| Director report | Yes | `ops_centre.tests.test_director` passed | No | No | Yes | **NOT VERIFIED** |
| Windows repair catalogue and live read-only diagnostics | Yes | Yes, including `test_live_diagnostics` | Yes, 2026-10-19: disk, printers, network, and devices on this PC. `problem_resolved` false. | No | `46e184c` is on GitHub `main` | **NOT VERIFIED** |
| Printer spooler approval practice path | Yes | `test_printer_restart_needs_a_different_approver_and_does_not_run` passed | The practice path uses a fixture. Live spooler was Running earlier. No restart was run. | No | `f1599ec` is on GitHub `main` | **NOT CONFIGURED** for an elevated test machine |
| Remote desktop | MeshCentral 1.2.6 boundary only | Session request stays `not_established` | No | No MeshCentral server | Yes | **NOT CONFIGURED** |
| Named operator login | On branch `cursor/operator-auth-phase0-787e` at `ae2fcc1`, not in `main` | Not re-run on `main` | No | No | **Not on `main`** | **NOT DEPLOYED** |
| Microsoft 365 mail | Code present | Mocked console tests | No | `MICROSOFT_CLIENT_ID` unset | Yes | **NOT CONFIGURED** |
| RunPod Qwen | Scripts exist | Not run this increment | No | Pod was not started or stopped | Source is on GitHub | **UNKNOWN**. No health check was made. |

## Deployment blocker

Console-only deploy is `CONSOLE_RESTART_APPROVED=yes bash /tmp/AI-PLAYBOOK/ops/release/deploy-console-only.sh` on the Pod, and only when Qwen and the gateway are already healthy. This increment did not SSH to the Pod, did not start paid compute, and did not restart services. Deployed commit: **not verified**.
