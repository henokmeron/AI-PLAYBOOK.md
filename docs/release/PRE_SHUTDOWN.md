# Pre-shutdown checkpoint

Run this before a planned Pod stop. It does not stop the Pod.

```powershell
python -m ops.release.pre_shutdown
```

The script checks that local `main` matches `origin/main`, the work tree has no source changes, and it builds the release package. It then prints one status:

| Status | Meaning |
| --- | --- |
| `READY_TO_SHUTDOWN` | The package checksum was verified and a persistent-volume copy was also verified. |
| `BLOCKED` | A local package may exist, but the volume copy was not verified or another required check failed. |
| `NOT_VERIFIED` | The package was not built. |

`python -m ops.release.pre_shutdown` does not itself read the Global Volume. Pass `--volume-verified` only after a checksum you have already checked. An older note that the SSH key was missing is out of date: the key is present, and it was used for the 2026-10-22 save below. Do not print the key.

## 2026-10-22 save

The pod was left running. This save did not run `snapshot-published-tip.sh`, because that script also installs `START.sh` and appends `VERSION.txt`. The published archive was copied to new paths and checked on the pod:

| Item | Path | SHA-256 |
| --- | --- | --- |
| Source snapshot of `6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8` | `/workspace/ai-platform-backups/source-snapshots/AI-PLAYBOOK.md-runpod-first-6f07b58.tar.gz` | `3cf154feb99536781232408ea06cc93373e14fe69e1d866daffa64ecdb015de7` |
| Checksum file (`sha256sum -c` OK) | `/workspace/ai-platform-backups/manifests/AI-PLAYBOOK.md-runpod-first-6f07b58.sha256` | same digest as the archive |
| Operator backup | `/workspace/platform-state/operator-backups/20261022T015922Z/operators.json` | `41811efc68d6723d5dc77dc1af06c882397b793ec9d5d0eae03ea9bef91ac6bf` |

Weights, the runtime archive (`666bb7c3fde67503c1d728d7d9501d597069e527eabb617228beebe5e626c9fb`, `sha256sum -c` OK), RAG docs, the wheelhouse, and `START.sh` were already on the volume. Weight shard bytes were **NOT RECOMPUTED**. They were not copied off the volume. There is no independent weight backup. The gateway key, sessions, and `/tmp/console-operator.secret` were not copied. `/tmp` disappears when the pod stops.

The pod that is running now is A100 `mlar88u3ku8utm` (`screeching_crimson_vole`) at **$1.80/hr**, with this same volume mounted at `/workspace`. Preflight already passed. The next cold start, only after the GPU load is approved, is:

```bash
bash /workspace/ai-platform-release/START.sh
```

H100 `xx9cjogra5vcwl` is **Stopped**. Do not start it. The full command above was not run. Production stays **NO-GO**.

## 2026-10-22 stopped-pod access check

The console was reloaded. Pod `xx9cjogra5vcwl` (`reliable_moccasin_hummingbird`) is **Stopped**, cost **$0.00/hr**, Compute **Not running**. It was not started. The Storage page, after reload, still shows Global Volume “New model container” `cmv2p5m0d000007jk9o3931ea`, type **Global**, location **Any**, **126.0GB**, **1,804 objects**, **$11.34/mo**. A stale tab had shown 1,794 objects. The stopped-pod Volumes tab shows **0 Bytes / 0 objects**. That line is not a file listing and does not match the Storage page.

Direct S3 access is **not** supported for this Global Volume. [The S3-compatible API](https://docs.runpod.io/storage/s3-api) is for network volumes in one data center. [Global volumes](https://docs.runpod.io/storage/globalvolume/overview) mount when a GPU pod starts, and they cannot attach to a CPU pod. The volume menu is Deploy, Edit, and Delete. There is no file browser. No S3 key was created. No object names were listed. No file was written.

The volume is already mounted on running A100 `mlar88u3ku8utm`. Read `/workspace` from that pod. H100 `xx9cjogra5vcwl` stays Stopped. Do not create a key, a volume, or a pod for that read. The snapshot and operator backup in the table above were checked before the H100 stop. They were not re-hashed for this note.

Before you stop the Pod yourself, confirm:

1. GitHub `main` is the commit you intend to keep.
2. The printed archive checksum matches a file you can still open.
3. Model weights are still on the volume. This checkpoint does not re-check them unless the Pod is reachable.
4. An operator account exists in `OPERATOR_AUTH_DIR` if the console will be restarted later.

The previous package is left in place. This script does not delete older releases.
