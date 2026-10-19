# Release and recovery

A release is a `git archive` of one verified `main` commit, plus a JSON manifest. The archive does not contain model weights, the Pod virtual environment, operator passwords, or device secrets.

## Create a package

From a clean `main` that matches GitHub:

```powershell
python -m ops.release.make_release
```

The package is written to `%LOCALAPPDATA%\AI-PLAYBOOK\releases\<commit>\`. The command prints the release id and the SHA-256 of the archive. It does not contact the Pod.

## Extract a package

```powershell
python -m ops.release.recover --archive <archive.tar.gz> --sha256 <checksum> --destination <empty-directory>
```

Automatic steps: checksum check, reject unsafe archive paths, extract into an empty directory.

Human steps after that:

1. Keep Qwen weights on the RunPod volume at `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654`. This package does not download them.
2. Restore the Pod Python runtime from `/workspace/runtime-setup/qwen-vllm/`. There is no pip lock file in Git for that runtime.
3. Create a console administrator with `scripts/provision_console_operator.py` before starting the new console. There is no default password.
4. Start or replace services only with `ops/release/START.sh` or `ops/release/deploy-console-only.sh` on an already healthy Pod. Those scripts are not run by `recover`.

## Persistent copy

`ops/release/snapshot-published-tip.sh` can write a checksummed archive to the Global Volume, and only when `/workspace` is that volume. It is not run from this PC when the SSH key is missing.

## Pre-shutdown

See `docs/release/PRE_SHUTDOWN.md`. The checkpoint script does not stop the Pod.
