# Release and recovery

A release is a `git archive` of one verified `main` commit, plus a JSON manifest. The archive does not contain model weights, the Pod virtual environment, operator passwords, or device secrets.

## Create a package

From a clean `main` that matches GitHub:

```powershell
python -m ops.release.make_release
```

The package is written to `%LOCALAPPDATA%\AI-PLAYBOOK\releases\<commit>\`. The command prints the release id and the SHA-256 of the archive. It does not contact the Pod.

The `.github/workflows/verify-and-package.yml` workflow is configured to run the release-recovery tests and build a commit-versioned archive plus manifest on pushes to `main`, then upload them as a GitHub Actions artifact for 90 days. Workflow run 39690305165 was created for commit f41f6f2e456609b8977922a3cbe9b001a5c1abbf and was still queued at the latest check; artifact availability is **NOT VERIFIED**. It does not create a GitHub Release or copy files to the RunPod Global Volume.

## Extract a package

```powershell
python -m ops.release.recover --archive <archive.tar.gz> --sha256 <checksum> --destination <empty-directory>
```

Automatic steps: checksum check, reject unsafe archive paths and all symlink/hardlink/device/FIFO members, reject a symlink destination, then extract into an empty directory. Paths are checked for POSIX traversal, Windows drive/UNC paths, backslash traversal, and NTFS alternate data streams. These checks protect recovery from a crafted archive; they do not establish that a release is deployed.

Human steps after that:

1. Keep Qwen weights on the RunPod volume at `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654`. This package does not download them.
2. Restore the Pod Python runtime from `/workspace/runtime-setup/qwen-vllm/`. There is no pip lock file in Git for that runtime.
3. Create a console administrator with `scripts/provision_console_operator.py` before starting the new console. There is no default password. The live file is `/tmp/console-operators/operators.json` (mode 0700 directory, 0600 file). A Pod stop deletes `/tmp`.
4. Start or replace services only with `ops/release/START.sh` or `ops/release/deploy-console-only.sh` on an already healthy Pod. Those scripts are not run by `recover`.

## Operator recovery after a Pod stop

| Store | Path | Survives Pod stop | Permission model |
| --- | --- | --- | --- |
| Live operators | `/tmp/console-operators` | No | POSIX 0700/0600 enforced. The console reads this directory. |
| Operator backup | `/workspace/platform-state/operator-backups/<stamp>/` | Yes, when `/workspace` is `fuse.geesefs` | Checksummed `operators.json` plus `SHA256SUMS`. Scrypt hashes only. The volume may reject `chmod`, so this copy is not treated as a private POSIX file. |
| Sessions | `/tmp/console-operators/sessions.json` | No | Not backed up. People sign in again. |
| Gateway key | `/tmp/platform-gateway.key` | No | Recreated on start if missing. Not copied to the volume. |
| Microsoft token | `/tmp/microsoft-365-token.json` | No | Not copied to the volume. Sign-in is required again. |
| Ops events | `/workspace/ops-centre` | Yes | Audit log. A health window does not delete it. |
| Weights | `/workspace/models/Qwen3.5-27B/...` | Yes | Not part of the source archive. |
| Runtime archive | `/workspace/runtime-setup/qwen-vllm/` | Yes | Restored into `/tmp/vllm-qwen-env`, never onto the volume. |
| Source checkout | `/tmp/AI-PLAYBOOK` | No | `START.sh` clones `main` or restores a checksummed snapshot. |

Before a console start, `ops/platform_state.py` backs up a private live administrator file, or restores the newest backup whose checksum matches when the live file is absent. It refuses a symlink, a plaintext password, a file that is not private, and a backup whose checksum does not match. It does not replace an existing live file. Five checksummed backups are kept.

```bash
PYTHONPATH=/tmp/AI-PLAYBOOK /usr/bin/python3 -m ops.platform_state --check \
  --live-dir /tmp/console-operators \
  --backup-dir /workspace/platform-state/operator-backups
```

`--check` does not write. Omit `--check` to back up or restore. The command prints one JSON object and does not print passwords, hashes, or tokens.

Qwen and the gateway are left running if operator recovery fails. Provision an administrator, then start the console again. `deploy-console-only.sh` runs the same recovery before it stops the console, and only when `CONSOLE_RESTART_APPROVED=yes`. A dry run does not write the backup.

## Persistent copy

`ops/release/snapshot-published-tip.sh` can write a checksummed archive to the Global Volume, and only when `/workspace` is that volume. It is not run from this PC when the SSH key is missing.

## Pre-shutdown

See `docs/release/PRE_SHUTDOWN.md`. The checkpoint script does not stop the Pod.
