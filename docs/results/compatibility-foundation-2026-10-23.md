# Hardware and driver compatibility foundation

Date: 2026-10-23. Recommendation only. Production stays **NO-GO**. No driver, firmware, or executable was downloaded. Nothing was installed. No machine was rebooted. Qwen was not restarted. No pod was created. No SSH session was opened. `ops/acceptance_board.py` and the acceptance evidence were not edited.

## What landed

`integrations/compatibility/` is a local catalogue plus a decision function. It does not scrape and it does not open source URLs. A source URL is a citation stored on the record.

Each component record can hold, when the source actually has them: manufacturer, model, hardware id, vendor id, device id, subsystem id, driver provider, driver version, driver signer, OS build, OS architecture, source URL, source type, retrieved time, record version, and confidence. A blank field stays blank.

`decide` returns one of:

- `compatible_verified`
- `compatible_documented`
- `likely_compatible`
- `incompatible`
- `unknown`
- `unsupported`

`unknown` is the result when the catalogue has no row, the query is missing identity fields, the source is older than 90 days, the source confidence is below the gate, or two rows disagree. Those cases are not turned into a compatible result. Every result says why, and names the source record id when a row was used.

`install`, `download`, `reboot`, and `firmware_update` stay disabled. The result has no procedure.

## Synthetic catalogue

Three rows, all marked synthetic. Host is `catalogue.invalid`. They are not a scan of a computer.

| Record | What the row states | Source type |
| --- | --- | --- |
| `syn-gpu-1000-lab-2026-10-01` | `compatible_verified` for Northwind Synthetic Devices SYN-GPU-1000, driver 1.2.3.4 | lab verification |
| `syn-nic-200-doc-2026-10-01` | `compatible_documented` for Contoso Synthetic Networks SYN-NIC-200, driver 10.0.0.1 | vendor documentation |
| `syn-audio-9-evidence-2026-10-01` | `incompatible` for Fabrikam Synthetic Audio SYN-AUDIO-9, driver 0.9.0.0 | lab verification, with an evidence note |

`compatible_verified` in the tests is an exact match against the synthetic SYN-GPU-1000 lab row. It is not a statement about any real machine.

## Office PC

This note does not claim anything about the office PC. That PC was not inventoried. No manufacturer, model, hardware id, driver provider, driver version, driver signer, Windows build, or architecture was read from it. The office PC is not recorded here as compatible, likely compatible, incompatible, supported, unknown from a scan, or verified. The fictional Northwind, Contoso, and Fabrikam rows are not that PC.

## Test

`python -m unittest integrations.tests.test_compatibility`

Python 3.11. 14 tests, 0 failed, exit 0. The tests use in-memory rows only. They do not call the network.
