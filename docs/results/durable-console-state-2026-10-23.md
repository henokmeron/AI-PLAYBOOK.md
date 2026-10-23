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

The pod checkout and the console reload are recorded after this file is on `main`. This sentence is not evidence that the running console has loaded this commit.
