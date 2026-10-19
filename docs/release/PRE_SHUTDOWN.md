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

On this PC the SSH key `%USERPROFILE%\.ssh\id_ed25519` has been missing, so the script cannot read `/workspace/releases/` and must not print `READY_TO_SHUTDOWN`.

Before you stop the Pod yourself, confirm:

1. GitHub `main` is the commit you intend to keep.
2. The printed archive checksum matches a file you can still open.
3. Model weights are still on the volume. This checkpoint does not re-check them unless the Pod is reachable.
4. An operator account exists in `OPERATOR_AUTH_DIR` if the console will be restarted later.

The previous package is left in place. This script does not delete older releases.
