# Asset inventory — 2026-10-22

## Shutdown save the same day

The pod was left running. No service was restarted. No Azure resource was created. No secret is recorded here. New files were written only at the paths below. Older volume files were not overwritten.

| Item | Evidence | Label |
| --- | --- | --- |
| Source snapshot `6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8` | `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-runpod-first-6f07b58.tar.gz` | **VERIFIED**. 696,562 bytes, 380 members, SHA-256 `3cf154feb99536781232408ea06cc93373e14fe69e1d866daffa64ecdb015de7`. `sha256sum -c` OK against `/workspace/ai-platform-backups/manifests/AI-PLAYBOOK.md-runpod-first-6f07b58.sha256`. |
| Release manifest and sidecar | `/workspace/ai-platform-backups/manifests/AI-PLAYBOOK-6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8.manifest.json` and `...tar.gz.sha256` | **VERIFIED** copied. File SHA-256 `6e1a628b9adcec49c6e8b4db4ded7c58540875c0b60079255e97ee17cc684426` and `1e401f38395f08eb8e055c4c4ed7e46fb70ac9241c3b63cbfb1179a9f104dc8a`. |
| Save note | `/workspace/ai-platform-backups/manifests/shutdown-asset-manifest-6f07b58-20261022T015922Z.txt` | Written. No secrets. |
| Operator backup | `/workspace/platform-state/operator-backups/20261022T015922Z/` | **VERIFIED** read-back. `operators.json` 378 bytes, SHA-256 `41811efc68d6723d5dc77dc1af06c882397b793ec9d5d0eae03ea9bef91ac6bf`, one enabled admin, scrypt. `SHA256SUMS` present. |
| Runtime archive | `sha256sum -c /workspace/runtime-setup/qwen-vllm/SHA256SUMS` | **VERIFIED** OK. `vllm-qwen-env.tar.zst` line remains `666bb7c3fde67503c1d728d7d9501d597069e527eabb617228beebe5e626c9fb`. Not re-downloaded. |
| Weights | 11 shard files listed under the known directory, about 52G | Shard bytes **NOT RECOMPUTED**. Small manifest file still SHA-256 `8f4e2624e9d53ece3c7590b02b6cdde16d7072b2aa98687225a77abe7ea60185`. |
| Launcher | `/workspace/ai-platform-release/START.sh` | **VERIFIED** unchanged. SHA-256 `41af7e93f34f2d28d9b97d53b18a4c58565dcb50e35bcdd6e71e40cfdaf92ca6`. Same as git `ops/release/START.sh`. |
| Older snapshot `01e7692` | re-hashed | **VERIFIED** still `a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370`. |
| Health after the copy | `2026-10-22T02:00:24Z` | `:8002/health` 200, `:8010/health` 200, `:8080/api/status` 200. |
| Not copied | `/tmp/platform-gateway.key`, `/tmp/console-operators/sessions.json`, `/tmp/console-operator.secret`, `/tmp/vllm-qwen-env` | Left on pod-local disk. The token file was absent. The gateway key is recreated on start. |

The full `snapshot-published-tip.sh` path was not used, because that path also installs `START.sh` and appends `VERSION.txt`. The archive bytes are the local package of `6f07b58`. A documentation commit after this inventory is not required on the volume.

## Later the same day (read-only recheck)

No Pod was started, stopped, resized, reloaded, or redeployed. No volume file was written. No Azure resource was created. No secret was opened or copied into this file.

| Item | Evidence | Label |
| --- | --- | --- |
| Archive of `d8c32ffebad6295b5d891de09681e46bbe2f022c` | `%LOCALAPPDATA%\AI-PLAYBOOK\releases\d8c32ffebad6295b5d891de09681e46bbe2f022c\AI-PLAYBOOK-d8c32ffebad6295b5d891de09681e46bbe2f022c.tar.gz` | **VERIFIED** read-back. 685,460 bytes, 377 members, SHA-256 `de30f6a2877fee34036731ab58073da8e0433cd6a10742e4ecfb4b6f3437f0c6`. Manifest matched. Not on the volume. |
| Archive of `9893cec4f3eb8b03370a4cab5f9a2dee9ab860b8` | `%LOCALAPPDATA%\AI-PLAYBOOK\releases\9893cec4f3eb8b03370a4cab5f9a2dee9ab860b8\AI-PLAYBOOK-9893cec4f3eb8b03370a4cab5f9a2dee9ab860b8.tar.gz` | **VERIFIED** read-back. 696,043 bytes, 380 members, SHA-256 `65cbcb5f16a90a5c4008f1a9e7e78b61916564df723da3c4da3ae34deaf2e2d5`. Sidecar matched. Not on the volume. The commit that records this row is not inside the archive. |
| Isolated extract | `%TEMP%\ai-playbook-recover-d8c32ff` | **VERIFIED** as a temp extract only. Not a fresh machine. |
| Pod health `2026-10-22T01:18:42Z` | `:8002/health` 200, `:8010/health` 200, `:8080/api/status` 200. HEAD `a0e9422145aae4e38025709d1ca88288e42f375b`. H100 NVL 85415/95830 MiB, driver 595.91.07, util 0%. | **VERIFIED**. Not parity with GitHub. |
| Billing header | First loaded header $15.46. After reload, **$14.93**, spend **$3.197/hr**, estimated time left **5 hours**. | **VERIFIED** re-read. Not $0.00. Inbox $4.77 is an older notification. |
| Weight backup | Not copied | **NO** independent weight backup. Shards stay only on the volume. |
| Microsoft | Saved redirect and single tenant as in `docs/integrations/microsoft-365-signin.md` | **NOT CONFIGURED** until a mailbox read. |

## First inventory the same day

Read-only inspection from `C:\Users\henok\src\AI-PLAYBOOK.md`. No Pod was started, stopped, resized, or reloaded. No volume file was written. No Azure resource was created. No secret is recorded here.

## GitHub source

| Item | Evidence | Label |
| --- | --- | --- |
| Remote | `https://github.com/henokmeron/AI-PLAYBOOK.md.git` | **VERIFIED** (`git remote -v` after init in this folder) |
| `origin/main` before this inventory commit | `2a56578a74cac4fc0c3f2a0b439c525daba17a6a` | **VERIFIED** by `git fetch` |
| Feature branches `feature/qwen-a100-start-hardening` and `feature/qwen3.5-27b-integration` | Fast-forwarded from `ec61ac5a548165914dcbf57a32928d595a86399c` to `0aa1caf21fea9570da8af21379f56e635aa2b3d7` with the collector commit. This note is a later commit on `main`. | **VERIFIED** push, not a force-push |
| Local tree before the collector edit | 330 files, same set as the shallow clone, zero differences after ignoring CR | **VERIFIED** |
| This PC release of `0aa1caf21fea9570da8af21379f56e635aa2b3d7` | `%LOCALAPPDATA%\AI-PLAYBOOK\releases\0aa1caf21fea9570da8af21379f56e635aa2b3d7\AI-PLAYBOOK-0aa1caf21fea9570da8af21379f56e635aa2b3d7.tar.gz` | SHA-256 `b3cd3683fdceeb943e6a464ab9ef8f1cd5833799c3503af9b79f3823fe9be42f` (also checked with `Get-FileHash`), 681,498 bytes, 375 tar members. Manifest SHA-256 `2286752db07b66d17124870586b2a38bd032120fc95009513c428be603719a9a`. Not copied to the volume. A later doc commit that records this hash is not inside the archive. |

## Running Pod (left running)

| Item | Evidence | Label |
| --- | --- | --- |
| Pod | `xx9cjogra5vcwl` / `reliable_moccasin_hummingbird`, H100 NVL, $3.20/hr. Console: one pod, GPU util 0%, memory 23% and 89%, disk 20%. Header balance text $18.13 | **VERIFIED** in the RunPod console |
| GPU | `nvidia-smi`: NVIDIA H100 NVL, 85415 MiB used, 95830 MiB total, driver 595.91.07 | **VERIFIED** over read-only SSH |
| HTTP | `:8002/health` 200, `:8010/health` 200, `:8080/` 200, `:8080/api/status` 200 | **VERIFIED** |
| Pod source | `/tmp/AI-PLAYBOOK` is `a0e9422145aae4e38025709d1ca88288e42f375b` | **VERIFIED**. This is behind GitHub `main`. Not a deployment of later commits. |

## Global Volume

Console Storage page: one Global volume, name “New model container”, id `cmv2p5m0d000007jk9o3931ea`, 126.0 GB stored, 1,794 objects, location Any, $11.34/mo. SSH mount: `fuse.geesefs` source `5aac0c77-6fcc-4be9-a112-dfe3890e1373` at `/workspace`. Both were observed on 2026-10-22. The deploy wizard had shown “0B stored” for a selected volume; the Storage page and the SSH listing contradict that wizard line. **VERIFIED** that data is present. No new volume was created.

| Asset | Path | Checksum computed this session | Label |
| --- | --- | --- | --- |
| Runtime archive | `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` | `666bb7c3fde67503c1d728d7d9501d597069e527eabb617228beebe5e626c9fb` | **VERIFIED** (`sha256sum -c SHA256SUMS` OK) |
| Frozen requirements | `requirements-frozen.txt` in that directory | `7e3500b07cdada6f66a78cd85928c2bddd40c50d490040d01241e269d94982f1` | **VERIFIED** (same check) |
| Runtime manifest | `runtime-manifest.txt` | `6eff70c723530c06260cb1047674f02d786d292d74bc8b966b82229f5690b510` | **VERIFIED** |
| vLLM version file | `vllm-version.txt` | `cc63125dd5c7bd2af06a6bcaf362f3ae0f34c727c2565132b8992943de1f3c71` | **VERIFIED** |
| Launcher | `/workspace/ai-platform-release/START.sh` | `41af7e93f34f2d28d9b97d53b18a4c58565dcb50e35bcdd6e71e40cfdaf92ca6` | **VERIFIED** |
| Snapshot `01e7692` | `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-runpod-first-01e7692.tar.gz` | `a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370` | **VERIFIED** (matches the digest already recorded in the handoff) |
| Snapshot `f7af785` | `.../AI-PLAYBOOK.md-runpod-first-f7af785.tar.gz` | `fcaa6252e5f122ad01cdb6259dfb6a7341fd90d06936dcaaf1a7cf9c25967bcb` | **VERIFIED** for this file only. It is not a current-main snapshot. |
| Weight manifest file | `/workspace/models/Qwen3.5-27B/manifests/fc05daec18b0a78c049392ed2e771dde82bdf654.sha256sums` | file SHA-256 `8f4e2624e9d53ece3c7590b02b6cdde16d7072b2aa98687225a77abe7ea60185`; contents are one line `2216b80b412eeb4f6cf450f3a2d8517edc3533c0dd6fbefaaf6e94b1b6cc8431  -` | File **VERIFIED**. The 11 shard files were listed (~52G) and were **NOT RECOMPUTED**. |
| RAG managed docs | `/workspace/rag-managed-docs` | not hashed | Directory exists, `du` reported 1.5K. Contents **NOT VERIFIED** beyond size. |
| Older snapshots | the other `.tar.gz` files listed by `ls` on 2026-10-22 | not hashed this session | **NOT RECOMPUTED** |

## Microsoft and Azure

Signed-in Azure portal, Default Directory. Credits shown: £150.95, expiring 2026-11-20. App registrations, All applications: one app, `llmfortestingclientid`, application id `07634d62-4b0e-4572-b586-c5922bb01570`, created 2026-10-21. A later read of the same app showed delegated Microsoft Graph `User.Read` and `Mail.Read`. Admin consent required is No for both. `Mail.Send` and `Mail.ReadWrite` were not added. No application secret was opened or created. The overview lists one existing secret and no certificate. Supported account types: this organization only. The loopback redirect was entered in the manifest editor and Save stayed disabled, so that redirect is **NOT VERIFIED** as stored. No Graph request was sent. The Pod environment was not changed. Mail integration remains **NOT CONFIGURED**.

## Local package of 281eb62

`%LOCALAPPDATA%\AI-PLAYBOOK\releases\281eb628b51f100433e3f4ab0aad83b516050ae5\AI-PLAYBOOK-281eb628b51f100433e3f4ab0aad83b516050ae5.tar.gz`. SHA-256 `1a998f7103cc8ca4a9f3a14047eb37e14d95470bba87c232c085e09851b7dad7`, 682,017 bytes, 375 tar members. Manifest read back in Python. Not copied to the volume. This inventory update is a later commit and is not inside that archive. The weight files were not copied off the volume. GitHub is a source backup only.

## Recovery path

1. GitHub `main` is the source of truth for code. The local package of `0aa1caf21fea9570da8af21379f56e635aa2b3d7` is SHA-256 `b3cd3683fdceeb943e6a464ab9ef8f1cd5833799c3503af9b79f3823fe9be42f`. Recover with `python -m ops.release.recover` as in `docs/release/RECOVERY.md`. That archive was not copied to the volume.
2. Weights stay at the volume path above. This package does not download them. Shard hashes were not recomputed on 2026-10-22.
3. Restore the runtime from `/workspace/runtime-setup/qwen-vllm/` into `/tmp`, not onto `/workspace`. The archive checksum above was checked.
4. `START.sh` on the volume is the 2026-10-19 file hashed above. It was not executed.
5. Create a console administrator with `scripts/provision_console_operator.py`. There is no default password. `/tmp` operators do not survive a Pod stop. Operator-backup files on the volume were **NOT LISTED** this session.
6. Do not start a second Pod. Do not copy a new archive onto the volume without a separate approval.

## Still not proven

Live Blackwell install and inference: **NOT TESTED**. A second Windows computer: **NOT TESTED**. Mail search against a real mailbox: **NOT TESTED**. Go-live: **NO-GO**.
