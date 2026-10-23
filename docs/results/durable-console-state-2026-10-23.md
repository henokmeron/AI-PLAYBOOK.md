# Durable console state

Date: 2026-10-23. Production stays NO-GO. Qwen was not restarted for this change.

## What survives a pod stop

Live files stay on pod-local disk so mode 0600 can be enforced. `/tmp` itself is not chmodded. The Global Volume keeps checksummed copies because a pod stop deletes `/tmp`. The volume may reject chmod, so those copies are not a private POSIX store. A restore writes them back to local disk and restricts that copy.

| Store | Live path | Volume mirror | In the mirror |
| --- | --- | --- | --- |
| Operator accounts | `/tmp/console-operators/operators.json` | `/workspace/platform-state/operator-backups/<stamp>/` | Scrypt hashes |
| Device list and enrolment | `/tmp/endpoint-devices.json` | `/workspace/platform-state/endpoint-backups/<stamp>/` | Code hashes, device-secret hashes, diagnostic summaries |

Not mirrored: `sessions.json`, `/tmp/platform-gateway.key`, `/tmp/microsoft-365-token.json`, `/tmp/microsoft-client-id`. After a pod stop, people sign in again, the gateway key is recreated if it is missing, and Microsoft sign-in is required again.

Five stamped backups are kept for each store. A bad checksum is skipped. An existing live file is not replaced. A plaintext device secret or a plaintext operator password is refused and is not copied. A missing device list with no backup is ready: nothing has enrolled yet.

The console sets `OPERATOR_BACKUP_DIR` and `ENDPOINT_BACKUP_DIR` when `/workspace` is `fuse.geesefs` and those variables were unset. Each save of an account or the device list then writes a new checksummed stamp. A volume error does not undo the local file.

## Local tests

`python -m unittest ops.test_platform_state ops.test_qwen_launch_path integrations.tests.test_endpoint web.test_auth` exited 0. 66 tests ran, 1 skipped (`openssl` absent). The endpoint restore test checked that the enrolment code and the device secret were absent from the volume copy and that a reloaded registry still had the enrolled device.

## Acceptance

The second-endpoint gate was re-read and was not marked. See the same date in the handoff. The Office PC diagnostic remains a stored report. `second_endpoint_worker_ok` was not written into `docs/results/acceptance-evidence.json`.

## Pod

Checked on pod `1jyrnyxpb0n93s` after `main` was fast-forwarded. Qwen was not signalled.

| Check | Result |
| --- | --- |
| Checkout | `cb920b3a703196eb86cfceaf6974367af90ee462`, equal to `origin/main` at the reload |
| Volume | `/workspace` is `fuse.geesefs` |
| Qwen | pid 6739, `:8002/health` HTTP 200 |
| Gateway | pid 6497, `:8010/health` HTTP 200 |
| Console | replaced pid 32355 with pid 34991, command `/tmp/AI-PLAYBOOK/web/server.py`, `:8080/api/status` HTTP 200 |

The console environment and command line were copied. The gateway and Qwen were left running.

Operator backup: action `backed_up`, 1 administrator, sessions not restored. Newest stamp `/workspace/platform-state/operator-backups/20261023T213720989628Z`. Device-list backup: action `backed_up`, 1 device, `secrets_copied` false. Stamp `/workspace/platform-state/endpoint-backups/20261023T213725366204Z`.

A restore into temporary directories returned 1 administrator and 1 device. `sessions.json` was not restored. Those temporary directories were removed. The live `/tmp` files were not replaced.

This does not pass deployment parity. No `deployed_sha_read` record was added. The running gateway and Qwen processes were started before this checkout. Production stays NO-GO.

Local release archive of `cb920b3a703196eb86cfceaf6974367af90ee462`: SHA-256 `0cfd5ffcc7cdbb719280ae0d5fc51c03023bcc432762e6530d002a93007ab23c`. It was not copied to the volume.
