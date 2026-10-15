# Shutdown recovery — 2026-10-15

The owner was about to stop RunPod `00n856z3eue5v9`. This note records what was saved and what was not. A new Global Volume snapshot was **not** created.

**Current Pod, 2026-10-15:** the owner is stopping `1g41ejmd99iyun` in the RunPod UI. Use Stop, not Terminate, and keep volume `5aac0c77-6fcc-4be9-a112-dfe3890e1373`. This agent did not confirm the stopped state. The last SSH mapping was `root@216.81.248.126 -p 19091`. That port dies with the Pod. The command later in this file that uses port `11165` is the older shutdown attempt. After the next start, read the new port and follow `docs/AGENT_HANDOFF.md`. Do not run `START.sh` until `/workspace` is confirmed as `fuse.geesefs`.

## Where this was run

| Check | Result |
| --- | --- |
| Hostname / user | `cursor` / `ubuntu` |
| `/workspace` mount | The root disk `/dev/vdc` `ext4`. `findmnt -T /workspace` reports target `/`. |
| `fuse.geesefs` | **Not this machine.** |
| `/workspace/models/Qwen3.5-27B` | **Absent.** `/workspace/models` here is only the git registry. |
| `/workspace/runtime-setup` | **Absent.** |
| `/workspace/ai-platform-backups` | **Absent.** |
| `/workspace/ai-platform-release` | **Absent.** |
| `/workspace/rag-managed-docs` | **Absent.** |
| Listeners on `:8002`, `:8010`, `:8080` | **None.** |
| SSH `root@154.54.102.31 -p 11165` | **One attempt.** TCP 11165 accepted the connection. Auth returned `Permission denied (publickey,password)` and exit 255. `~/.ssh` has `known_hosts` only. The attempt was not repeated. |
| RunPod API credential in this environment | **None.** No second Pod was started. |

This cloud VM is not the Pod and cannot write the Global Volume. **Do not assume a snapshot newer than `01e7692` exists on the volume.**

## GitHub (verified with `git ls-remote` before this note)

These four refs were `c99cb4cb9eeb974176476766dcd64964db53f68f` (“Return an HTML result from the Microsoft callback.”):

- `main`
- `feature/qwen-a100-start-hardening`
- `feature/qwen3.5-27b-integration`
- `cursor/microsoft-signin-options-2e6d`

This note is the next commit on those branches, fast-forward only. The live console checkout `/tmp/AI-PLAYBOOK` was last seen at `98511df`. That directory is on the Pod’s ephemeral disk and disappears when the Pod stops. It is not a backup.

## Volume paths last seen on 2026-10-15

A machine that had the owner’s SSH key checked the Pod earlier the same day. This cloud VM did not repeat that check. If the volume was not wiped, these paths should still be there:

| Path | Last observation |
| --- | --- |
| Volume id `5aac0c77-6fcc-4be9-a112-dfe3890e1373` mounted at `/workspace` (`fuse.geesefs`) | Seen 2026-10-15 |
| `/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654` | Weights present 2026-10-15. 11 shards, about 51.75 GiB, BF16, was the earlier inventory. Not re-counted from here. |
| `/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst` and `SHA256SUMS` | Checksum verified 2026-10-14. Not re-hashed from here. |
| `/workspace/runtime-setup/rag-wheelhouse/` | Present in the last volume inventory. Not listed from here. |
| `/workspace/rag-managed-docs` | Present in the last volume inventory. Not listed from here. |
| `/workspace/ai-platform-release/START.sh` | Matched git `ops/release/START.sh` on 2026-10-14 (SHA-256 prefix `6059e4c2`). Not compared from here. |
| `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-runpod-first-01e7692.tar.gz` | SHA-256 `a385f8a8e0f0c9f5db0d8cb48c8bbdde6a627bb6dd19690adb3cff1cd1228370`, checked 2026-10-14. Older snapshots `083fa58` and `0b49946` were still on the volume then. |

`VERSION.txt` on the volume was **not** updated. Nothing under `/workspace` was deleted. Qwen and the gateway were not stopped from here.

## What comes back on a new Pod

Attach the **same** Global Volume at `/workspace`. Do not download the model again.

```bash
bash /workspace/ai-platform-release/START.sh --preflight
bash /workspace/ai-platform-release/START.sh
```

`START.sh` clones `feature/qwen3.5-27b-integration` from GitHub into `/tmp/AI-PLAYBOOK`. That is the path that picks up this commit. The volume snapshot is used only when GitHub cannot be cloned. Today that fallback is still the older archive `AI-PLAYBOOK.md-runpod-first-01e7692.tar.gz`, which does not contain the work after `01e7692`.

## If the Pod is still on and SSH from the owner’s PC still works

The key that worked before is `%USERPROFILE%\.ssh\id_ed25519` on the owner’s Windows PC. After this note is on `main`, this one command writes the missing snapshot. It refuses to run unless `/workspace` is `fuse.geesefs`, and it does not stop the live ports:

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=8 -p 11165 -i "$env:USERPROFILE\.ssh\id_ed25519" root@154.54.102.31 "curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/ops/release/snapshot-published-tip.sh | bash"
```

The same script is `ops/release/snapshot-published-tip.sh` in this repository.

The script clones the published tip into `/tmp`, writes `AI-PLAYBOOK.md-runpod-first-<7-char>.tar.gz` plus a sibling `.sha256` manifest, checks the existing runtime `SHA256SUMS`, records weight shard names and sizes, and hashes only a 1 MiB prefix of two shards. It copies a different `START.sh` aside before replacing it. It appends to `VERSION.txt` only when that file already exists, after saving `VERSION.txt.bak-<timestamp>`.

Until that script prints `VERIFIED_SNAPSHOT=` and `VERIFIED_SHA256=`, there is no new volume snapshot.
