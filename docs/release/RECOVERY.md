# Release and recovery

A release is a `git archive` of one verified `main` commit, plus a JSON manifest. The archive does not contain model weights, the Pod virtual environment, operator passwords, or device secrets.

## Create a package

From a clean `main` that matches GitHub:

```powershell
python -m ops.release.make_release
```

The package is written to `%LOCALAPPDATA%\AI-PLAYBOOK\releases\<commit>\`. The command prints the release id and the SHA-256 of the archive. It does not contact the Pod. It uses a git binary that prints `git version`. If PATH `git` is only a launcher, set `AI_PLAYBOOK_GIT` or install Git; on this PC the helper also finds GitHub Desktop's `git.exe`. The manifest is read back and rejected if its checksum field does not match the archive. The same digest is also written to `AI-PLAYBOOK-<commit>.tar.gz.sha256` beside the archive, not inside it, and that file is read back before the command succeeds.

`ops/release/update-source-only.sh` is the pod source update. It is dry-run unless `SOURCE_UPDATE_APPROVED=yes`. Preflight: the checkout must be git, origin must be `https://github.com/henokmeron/AI-PLAYBOOK.md.git`, and there must be no tracked edits. Action: `git fetch` and `git merge --ff-only`. Rollback: a refused fast-forward does not move HEAD; do not `git reset`. Acceptance: HEAD equals `origin/<branch>`. It does not call health URLs and it does not signal Qwen, the gateway, or the console. It was not run on the H100. Git parity for this PC is `PLAYBOOK.md` section G.

The `.github/workflows/verify-and-package.yml` workflow is configured to run the release-recovery tests and build a commit-versioned archive plus manifest on pushes to `main`, then upload them as a GitHub Actions artifact for 90 days. Workflow run 39690350318 completed successfully for commit b25294644ffd69415ecb4291723047ec647e8b41. It passed ops.test_release_package and uploaded artifact ID 12387414455, named AI-PLAYBOOK-b25294644ffd69415ecb4291723047ec647e8b41. The 374-member source archive SHA-256 is e92c9005052d63006a03004bfe212ace11969074a86be6c3c2b333624b33fdf1; the downloaded artifact ZIP SHA-256 is 097ec6835443b489a0e186a82781043e5cf5f09fd5c6aef2b847d998bf6da4a1. The artifact is retained for 90 days. This is a focused release-test pass, not a full-suite pass. It does not create a GitHub Release or copy files to the RunPod Global Volume.

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

`ops/release/snapshot-published-tip.sh` can write a checksummed archive to the Global Volume, and only when `/workspace` is that volume. Without `VOLUME_COPY_APPROVED=yes` it prints the plan and writes nothing.

Preflight: `/workspace` must be `fuse.geesefs`, the Qwen weights and runtime archive must already be there, and the destination archive must not already exist. Verify: `sha256sum -c` the new checksum file. Rollback: if that check fails, delete only the new archive and its checksum file. Older snapshots, weights, and the runtime archive stay. Acceptance: the printed digest matches the read-back, and Qwen, the gateway, and the console were not signalled.

On 2026-10-22 the owner approved one new snapshot. `snapshot-published-tip.sh` was not executed, because it also runs `install-to-volume.sh` and appends `VERSION.txt`. The local archive of `6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8` was copied to `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-runpod-first-6f07b58.tar.gz`. Its SHA-256 is `3cf154feb99536781232408ea06cc93373e14fe69e1d866daffa64ecdb015de7`, and `sha256sum -c` on the volume matched. The operator backup is `/workspace/platform-state/operator-backups/20261022T015922Z/`. The gateway key was not copied. `ops/release/volume_transfer.py` only returns a plan. `copied` stays false even when the plan is approved, so importing it cannot write the volume.

An isolated local recovery is:

```powershell
python -m ops.release.recover --archive <archive.tar.gz> --sha256 <checksum> --destination <empty-temp-directory>
```

On 2026-10-22 that command extracted the `d8c32ff` archive into `%TEMP%\ai-playbook-recover-d8c32ff`. Later the same day it extracted `6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8` into `%TEMP%\ai-playbook-recover-6f07b58-temp-extract` after sidecar SHA-256 `3cf154feb99536781232408ea06cc93373e14fe69e1d866daffa64ecdb015de7` matched. Both are temp extracts, not a fresh machine, not a second computer, and not a pod deployment.

The local archive of `00894206db6fec0238c6243e83ee7a5e18c7df08` is SHA-256 `bf4355541d1dbeecfe6681c9bdfbe5235bff0dceed8a1570bb1e9d522e4f48be`, 719,707 bytes, 383 members. The commit that records this hash is not inside that archive. It was not copied to the volume.

The local archive of `5cb961b29173dbceb8cfe661bb23a5f0cbeb39c5` is SHA-256 `3d77ab37436ed25caa8940a3da45a6768cd84943c768e9794c86c35647730984`, 709,868 bytes, 383 members. The commit that records this hash is not inside that archive. It was not copied to the volume.

Repeatable git parity on this PC is `python -m ops.git_parity`. Add `--ls-remote` to require one SHA on `main`, `feature/qwen-a100-start-hardening`, and `feature/qwen3.5-27b-integration`. The command does not commit, push, or start the pod. A matching SHA is not a deployment. System Status shows the same split: offline implementation percent is not live acceptance, and the production decision stays **NO-GO** until the live gates pass.

## Second endpoint and Blackwell

Both are **NOT TESTED**.

A second endpoint needs another Windows computer with the endpoint worker. This development PC is not that computer. Do not record its collectors as a second endpoint.

Blackwell needs a GPU of compute capability 12.0 and a driver of 575 or newer, then the pinned install, check, serve, and one inference in `ops/blackwell`. The running pod is an A100, not that hardware. The stopped H100 NVL is not that hardware either. Do not record an A100 or H100 result as a Blackwell result.

## Which pod to recover

Checked against the 2026-10-22T13:01Z record. The running pod is A100 `mlar88u3ku8utm` (`screeching_crimson_vole`) at **$1.80/hr**. Global Volume “New model container” (`cmv2p5m0d000007jk9o3931ea`) is already mounted at `/workspace`. `bash /workspace/ai-platform-release/START.sh --preflight` returned **PREFLIGHT_PASS** at 2026-10-22T13:02:45Z and did not load Qwen. The next cold start, only after the GPU load is approved, is:

```bash
bash /workspace/ai-platform-release/START.sh
```

H100 `xx9cjogra5vcwl` (`reliable_moccasin_hummingbird`) is **Stopped** at **$0.00/hr**. Do not start it. Do not create a volume, a pod, or an S3 API key. Weights and the runtime archive stay only on this volume. There is no independent weight backup. This command was not run from the session that wrote this paragraph. Production stays **NO-GO**.

## Reading the volume

The volume is mounted on the running A100 above. An earlier console check, while the H100 was the only pod on the account and was **Stopped**, still applies to the Storage page: type **Global**, location **Any**, 126.0GB, 1,804 objects after a reload. The S3-compatible API does not apply. The doc is [https://docs.runpod.io/storage/s3-api](https://docs.runpod.io/storage/s3-api) (“access and manage your network volumes”). This volume’s own menu has no S3 or file-browser action. A stopped pod’s Volumes tab can show 0 Bytes; that line is not a file listing. No key was created and no object was listed. Do not start the H100 to read the volume. The A100 is already running with it mounted.

## Pre-shutdown

See `docs/release/PRE_SHUTDOWN.md`. The checkpoint script does not stop the Pod. The stopped-pod access check is recorded there.
