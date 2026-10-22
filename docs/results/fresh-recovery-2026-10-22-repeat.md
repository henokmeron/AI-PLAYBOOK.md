# Fresh recovery — 2026-10-22 repeat

Local drill on this Windows PC. The suite finished at `2026-10-22T22:29:41Z`. Cleanup of this run's container and destination finished just after that.

## Verdict

The fresh-recovery gate remains unmet because this PC is not a fresh machine or a new pod.

The offline suite exited **0**. Pass count **41**, fail count **0**. That result does not satisfy the board rule in `ops/acceptance_board.py`:

> Recovery on a fresh machine or a new pod (a temp extract does not count)

Required live result: `fresh_recovery_ok`, freshness 168 hours. This run is the same development PC. It is not a fresh machine and it is not a new pod. The extract directory was under `%TEMP%`. `docs/results/acceptance-evidence.json` was not given a `fresh_recovery_ok` record. The gate criteria were not edited.

The archive does not include the model. Nothing here touched the A100 pod, SSH, `/workspace`, model weights, or the Global Volume. Nothing was restarted. No paid machine was created. The container had no GPU devices, no mounts, and its network was disconnected before the suite.

## Exit codes

| Step | Exit |
| --- | --- |
| Checksum | 0 |
| Recover | 0 |
| Container create | 0 |
| Dependency install | 0 |
| Suite | 0 |
| Cleanup (stop, remove container, delete destination) | 0 |

Network disconnect before the suite also exited 0.

## Checksum before extract

Sidecar and archive both `d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82`. Archive bytes 710946. `match=true`.

Archive: `%LOCALAPPDATA%\AI-PLAYBOOK\releases\758177dfad9c6ddac588debce55ab0729704c8fd\AI-PLAYBOOK-758177dfad9c6ddac588debce55ab0729704c8fd.tar.gz`. Commit `758177dfad9c6ddac588debce55ab0729704c8fd`.

Python: `C:\Users\henok\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe`.

## Extract

Destination did not exist beforehand. It is not the earlier `%TEMP%\ai-playbook-fresh-recovery-20261022-758177df` tree.

```powershell
python -m ops.release.recover --archive $archive --sha256 d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82 --destination $env:TEMP\ai-playbook-fresh-recovery-20261022f-758177df
```

Exit **0**.

```text
extracted=C:\Users\henok\AppData\Local\Temp\ai-playbook-fresh-recovery-20261022f-758177df
automatic: checksum verified and source extracted
automatic: published origin recorded in .git; no fetch and no commit
```

Host `git remote -v` in that directory printed fetch and push URLs `https://github.com/henokmeron/AI-PLAYBOOK.md.git`. No commit was created and nothing was fetched.

## Container and install

Docker was already running (`client=29.8.2`, `server=29.8.2`). Image `python:3.11-slim` was already local. No image was pulled in this run.

```powershell
docker run -d --name ai-playbook-fresh-recovery-20261022f python:3.11-slim sleep infinity
```

Exit **0**. Container `de84d3e484fb0e1b097a71e38a9d2c71c626c4ee07ed9d514ea2a7f54e507353`. Python inside was `3.11.17`. `git` was not on the image before the install. Weight-file count inside the copied tree was 0.

The recovered tree was copied to `/opt/ai-playbook`. The archive predates `ops/release/install-clean-env.sh`, so that script was copied from this checkout to `/tmp/install-clean-env.sh` and run as `sh /tmp/install-clean-env.sh /opt/ai-playbook`. It was not written into the suite tree.

Exit **0**. `git version 2.47.3`. `pypdf=6.20.0`. `openpyxl=3.1.5`. `git remote -v` inside the container showed the same published origin. The install used the default bridge. After it finished, `docker network disconnect bridge` exited **0**. Inspect then showed `network={}`, `mounts=0`, `devices=null`.

## Offline tests

```powershell
docker exec -e PYTHONUNBUFFERED=1 -w /opt/ai-playbook ai-playbook-fresh-recovery-20261022f python -m ops.run_tests
```

Exit **0**.

```text
SUMMARY modules=41 ok=41 failed=0 elapsed_s=55.2
```

`ops.test_git_parity`, `ops.test_release_package`, and `rag.tests.test_document_loaders` were among the modules that passed. The filtered log also printed one `Traceback` line under `api.test_gateway_reliability`; that module was still counted in the 41 that passed.

## Cleanup

`docker stop` exit **0**. `docker rm` exit **0**. The destination directory was deleted (exit **0**) and was absent afterward. Docker Desktop was left running. The earlier recovery containers from the same day were not removed.

## What this does not decide

- The package does not contain Qwen weights and this run did not download them.
- A passing extract plus a local container does not satisfy `fresh_recovery`.
- Production stays on the existing board. This file does not change it.
