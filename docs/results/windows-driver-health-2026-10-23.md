# Windows driver health, 2026-10-23

## What this is

`windows_repair/driver_health.py` is a standalone Windows-only helper. It does not import the endpoint worker, the repair runner, or the approval catalogue. Other jobs own those files.

The read-only report lists the device name, class, problem code, driver version, driver provider, and driver date when those values are present. A missing field is `unavailable`, `unsupported`, or `permission-denied`. Those words are not replaced with ok, and a report with a missing field has `ok` false. `problem_resolved` stays false. Serial numbers, PnP instance ids, and hardware ids are not collected.

A payload labelled `synthetic` is not a live success. Its `ok` flag is false, its `evidence_source` is `unavailable`, and the synthetic device rows are not stored. A complete payload handed to the classifier is `evidence_source` `supplied`. This work did not query this PC, Office PC `bead5785f3674aaeb92c189f8c1b5b8c`, or the pod, so nothing here is a live success.

## Driver install refusal

The default decision is refused. Nothing is downloaded.

`propose_driver_install` always refuses. It may name `windows-update` or `pnputil` as the only allowed sources. Any other source is refused. An arbitrary URL is refused even when an approval object is present, and the URL is not copied into the result.

`install_driver` returns refused unless the approval names the device id, the action id, and the exact device target, and the source is `windows-update` or `pnputil`. A different device target does not match. When those conditions are met, the function returns a plan record of what would run. That record has `executed` false, `downloaded` false, and `invoked` false. The function does not shell out. It does not call pnputil, Windows Update, or an installer.

No code path in this module opens a network connection. The tests use fakes only.

## What was not done

Production stays NO-GO. No acceptance gate was marked. No device was enrolled. Microsoft 365, mail, and tokens were not touched. No remote shell was opened. Qwen was not restarted. No service was restarted and no printer queue was cleared. No general diagnostic check was added to the existing catalogue.

## Tests

Command, from `C:\Users\henok\src\AI-PLAYBOOK-driver-health`, using `C:\Users\henok\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe`:

`python -m unittest windows_repair.tests.test_driver_health`

Result: Ran 13 tests. OK. Exit code 0. The tests are fakes. They do not download a driver and they do not open a network connection.

## Base

Branch `feature/windows-driver-health` is based on `origin/main` at `bba59f08d4787e48a01766ff18ca165fc8089175`. The other checkout's `main` was `9d979b6b21a7690011a68a3924e30e1a2f6fefdc`. This branch was not merged.
