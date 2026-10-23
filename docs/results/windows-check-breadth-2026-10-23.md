# Windows check breadth, 2026-10-23

## What changed

The check-in already stored nine read-only checks: disk free space, services, update events, device inventory, printers, network, recurring system events, startup, and hardware identity. Those nine stay. Hardware identity is still manufacturer, model, BIOS, CPU, and available versus total memory. Missing identity is unavailable, unsupported, or permission-denied, and is not ok. A synthetic fixture is not a live success. Serial numbers are not collected.

Six more read-only checks now run on the same Windows worker path:

| Check | What it reports |
| --- | --- |
| `win.reboot.pending` | Whether a reboot is pending. It does not reboot. |
| `win.services.failed` | Name and state of automatic services that are not running. It does not restart them. |
| `print.queue.depth` | Queue depth. It does not clear the spooler. |
| `win.storage.health` | Physical-disk health. Free space alone is not this check. A missing health source is unavailable, not ok. |
| `hw.devices.problems` | Problem-device name, class, and problem code. No serial numbers. |
| `win.events.recent` | A count of recent system error events. `win.events.recurring` still lists events and was not removed. |

`ok` means the read succeeded. A pending reboot, a stopped service, a deep queue, an unhealthy disk, a problem device, or a non-zero error count is a finding in the summary. It is not a repair. A missing source, a synthetic fixture, an unsupported tool, or a permission denial is not ok.

The console still accepts a check-in of at most 4096 bytes. Summaries are capped at 100 characters so fifteen maximum summaries plus hardware identity fit. The fixed script was parsed and was not executed against this PC.

## What was not run

No check was run against a live PC and called a success. No device was enrolled. No SSH session was opened. Qwen was not restarted. No service was restarted, no queue was cleared, no driver was downloaded, and nothing was installed or deleted. `ops/acceptance_board.py` and `docs/results/acceptance-evidence.json` were not edited.

Production stays NO-GO. No acceptance gate was marked.

## Tests

Commands used `C:\Users\henok\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe` from `C:\Users\henok\src\AI-PLAYBOOK-check-breadth`. The tests use fakes. They do not open a network connection.

- `python -m unittest integrations.tests.test_endpoint` — exit 0. Ran 24 tests in 2.658s. OK (skipped=1, the self-signed HTTPS case, because openssl is not available).
- `python -m unittest windows_repair.tests.test_health_checks` — exit 0. Ran 13 tests in 0.022s. OK.

## Base

`feature/windows-check-breadth` was created from `origin/main` at `bba59f08d4787e48a01766ff18ca165fc8089175`. The expected tip `9d979b6b21a7690011a68a3924e30e1a2f6fefdc` was the local `main` checkout. `origin/main` had already moved forward. The worktree was branched from the fetched `origin/main` tip. The main workspace was left on `main`.
