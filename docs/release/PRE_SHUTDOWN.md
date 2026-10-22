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

Weights, the runtime archive (`666bb7c3fde67503c1d728d7d9501d597069e527eabb617228beebe5e626c9fb`, `sha256sum -c` OK), RAG docs, the wheelhouse, and `START.sh` were already on the volume. Weight shard bytes were **NOT RECOMPUTED**. The gateway key, sessions, and `/tmp/console-operator.secret` were not copied. `/tmp` disappears when the pod stops. After a new pod with this same volume is Running, and only then:

```bash
bash /workspace/ai-platform-release/START.sh --preflight
bash /workspace/ai-platform-release/START.sh
```

Production stays **NO-GO**.

Before you stop the Pod yourself, confirm:

1. GitHub `main` is the commit you intend to keep.
2. The printed archive checksum matches a file you can still open.
3. Model weights are still on the volume. This checkpoint does not re-check them unless the Pod is reachable.
4. An operator account exists in `OPERATOR_AUTH_DIR` if the console will be restarted later.

The previous package is left in place. This script does not delete older releases.
