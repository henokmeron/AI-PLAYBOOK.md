# Windows diagnostic breadth, 2026-10-23

## What changed

The eight stored checks did not identify the computer. Disk space, services, update events, PnP problem codes, printers, network, recent system errors, and startup were already collected. Startup can carry boot time, free memory, and CPU load. It does not store manufacturer, model, BIOS, or CPU name.

`hw.identity.inspect` is now a ninth read-only check. A fixed script reads Win32_ComputerSystem, Win32_BIOS, Win32_Processor, and Win32_OperatingSystem. It does not accept a command, a path, or a credential. Serial numbers and the signed-in user name are not selected.

The stored report can include a bounded `hardware` object: status, manufacturer, model, BIOS, CPU, and available versus total memory. The check-in body, with nine maximum summaries and that object, stays inside the 4096-byte console limit.

Missing or partial identity is `unavailable`, `unsupported`, or `permission-denied`. Those readings are not `ok`. A fixture labelled `synthetic` is not `live_windows` and is not `ok`. `acceptance_role()` is unchanged: an empty fixture label is still `not-recorded-as-second-endpoint`.

## What was not run on the Office PC

This work did not run on Office PC device `bead5785f3674aaeb92c189f8c1b5b8c`. That laptop already reported eight ok checks. This PC cannot write that laptop, and no new live report was invented.

Blocker: the Office PC download does not contain the startup-summary fix (commit `e8f966534a7f7d5b8409793bbdbede19596a0e78` and later). The owner must run `docs/coordination/office-pc-clone.md`, then run the worker from the folder that contains `integrations`. Until that clone, the Office PC will not send this hardware check. That is a blocker for the next Office PC report, not a failure of this code.

A read-only collector on this development PC returned `status=collected`, `ok=true`, and `evidence_source=live_windows`. Identity strings from that PC are not copied here. That run is not the second endpoint and does not pass the acceptance gate.

Production stays NO-GO. No `second_endpoint_worker_ok` or `deployed_sha_read` record was added. Qwen was not restarted. No pod was created, no weights were copied, no mail was sent, and no device was enrolled.

## Tests

Commands used `C:\Users\henok\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe` from `C:\Users\henok\src\AI-PLAYBOOK.md`.

- `python -m unittest integrations.tests.test_endpoint` — exit 0. Ran 23 tests in 2.690s. OK (skipped=1, the self-signed HTTPS case, because openssl is not available).
- `python -m unittest windows_repair.tests.test_hardware_inventory windows_repair.tests.test_capabilities windows_repair.tests.test_windows_repair` — exit 0. Ran 24 tests in 2.485s. OK.

The hardware tests use synthetic fixtures labelled `synthetic` for a complete reading, a missing reading, and a permission-denied reading. The live test on this PC only checks the status contract.

## Commit

Branch: `feature/windows-diagnostic-breadth`. Confirmed `origin/main` at the start of this work was `ab6788bab23fbed2127ab7d7dc7b93b98a25a049`. Before this commit, `origin/main` was `2e956c45330cd70d7bb56d2c447c582f6aeae417` (coordination notes only). This branch is based on that parent.

Feature commit: `1908c9a93591ffbc1433525772cbb066ae61a4d5`

## Next action

The owner runs the clone steps in `docs/coordination/office-pc-clone.md` on the Office PC, then runs `python -m integrations.endpoint_worker report` from the folder that contains `integrations`. Do not mark `second_endpoint_worker_ok` from this branch. Do not merge this branch to main from here.
