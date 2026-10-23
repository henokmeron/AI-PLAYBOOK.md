# Windows safe fixes, 2026-10-23

## What changed

Two repair actions now exist, and both refuse unless an explicit approval names the same device, the same action id, and the same target. A diagnostic result is not an approval. There is no blanket approval.

The actions do not call Windows. A matching approval with no injected fake still refuses. A fake can report success in a test. That success is not a live repair: `live` stays false, `changed_device` stays false, and `problem_resolved` stays false.

## Action ids

- `win.service.restart_failed` — restart one failed automatic service, named in the approval. A running service is not stopped. A list of services is not restarted. The computer is not rebooted. Manual, disabled, and non-failed services are refused. Delayed automatic is treated as automatic.
- `print.queue.clear_spool` — clear spool files for one stuck printer queue, named in the approval. Only absolute `spool\PRINTERS\*.SPL` and `*.SHD` files tagged with that queue are eligible. User documents, the spooler directory, the PRINTERS directory, and other queues are refused, and nothing is deleted when any listed path is outside that one queue.

## Refusal rules

The gate returns `refused` when:

- approval is missing (`approval_missing`)
- the value is not an `Approval`, including a diagnostic dict that copies the same field names (`not_an_approval`)
- device, action, or target is blank, `*`, `all`, `any`, or more than one name (`blanket_approval`)
- the approval is expired, including `now == expires_at` (`approval_expired`)
- the device id differs (`approval_device_mismatch`)
- the action id differs (`approval_action_mismatch`)
- the target name differs (`approval_target_mismatch`)

These stay refused even when an approval names them (`action_forbidden`): reboot, format, registry wipe, firewall changes, uninstall, driver download, driver install, file delete, Microsoft 365, sign-in, mail, and tokens. Shutdown is treated the same way. No environment variable turns live repair on.

## What was not run

No service was restarted and no spool file was deleted on this PC, the Office PC, or the pod. There was no SSH, no Qwen restart, no process restart, and no device enrolment. Production stays NO-GO. No acceptance gate was marked. `ops/acceptance_board.py` and `docs/results/acceptance-evidence.json` were not changed.

## Tests

Command used `C:\Users\henok\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe` from `C:\Users\henok\src\AI-PLAYBOOK-safe-fixes`.

- `python -m unittest windows_repair.tests.test_safe_fixes` — exit 0. Ran 22 tests in 0.002s. OK.

The tests use fakes. They cover refusal without a matching approval, and a fake success path when the approval matches. They also cover a running service, a list of services, another queue, a user document, and the spool directory.

## Commit

Branch: `feature/windows-safe-fixes`. Base is `origin/main` at `bba59f08d4787e48a01766ff18ca165fc8089175` after `git fetch origin`. The other checkout's local `main` was `9d979b6b21a7690011a68a3924e30e1a2f6fefdc`; this branch was not cut from that checkout.

This branch was not merged. `main` was not pushed.
