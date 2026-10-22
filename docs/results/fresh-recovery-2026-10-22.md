# Fresh recovery — 2026-10-22

Local drill on this Windows PC. Clock after the suite and the container stop: `2026-10-22T21:10:26Z`.

## Verdict

Completed on this PC. The offline suite exited **1**. This run does **not** pass the `fresh_recovery` acceptance gate.

The board rule was left as written in `ops/acceptance_board.py`:

> Recovery on a fresh machine or a new pod (a temp extract does not count)

Required live result: `fresh_recovery_ok`, freshness 168 hours. This run is the same development PC. It is not a fresh machine and it is not a new pod. The extract directory is under `%TEMP%`. `docs/results/acceptance-evidence.json` was not edited, and `fresh_recovery_ok` was not recorded.

The archive does not include the model. Manifest `model.included_in_package` is `false`. The extracted tree is 339 files, 2,679,552 bytes, and contains zero weight files (no `.safetensors`, `.gguf`, `.pt`, `.pth`, or `.onnx`). The largest file is `PLAYBOOK.md` at 139,769 bytes. Names that contain `qwen` are docs and scripts.

Nothing here touched the A100 pod, SSH, `/workspace`, model weights, or the Global Volume. Nothing was committed or pushed. No paid machine was created. Docker Desktop’s engine was started; it is local and CPU-only. The container had no GPU devices and `--network none`.

## Checksum before extract

Sidecar file text:

```text
d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82  AI-PLAYBOOK-758177dfad9c6ddac588debce55ab0729704c8fd.tar.gz
```

Command (Python `C:\Users\henok\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe`):

```powershell
$py = "C:\Users\henok\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe"
$archive = Join-Path $env:LOCALAPPDATA "AI-PLAYBOOK\releases\758177dfad9c6ddac588debce55ab0729704c8fd\AI-PLAYBOOK-758177dfad9c6ddac588debce55ab0729704c8fd.tar.gz"
$sidecar = "$archive.sha256"
$expected = "d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82"
& $py -c @"
import hashlib, sys
from pathlib import Path
sys.path.insert(0, r'C:\Users\henok\src\AI-PLAYBOOK.md')
from ops.release.package import read_checksum_sidecar
sidecar = Path(r'$sidecar')
archive = Path(r'$archive')
expected = '$expected'
digest = read_checksum_sidecar(sidecar)
print('sidecar=' + digest)
h = hashlib.sha256()
with archive.open('rb') as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b''):
        h.update(chunk)
actual = h.hexdigest()
print('archive_sha256=' + actual)
print('archive_bytes=' + str(archive.stat().st_size))
match = digest == expected and actual == expected and digest == actual
print('match=' + str(match).lower())
sys.exit(0 if match else 1)
"@
```

Exit **0**.

```text
sidecar=d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82
archive_sha256=d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82
archive_bytes=710946
match=true
```

Archive: `%LOCALAPPDATA%\AI-PLAYBOOK\releases\758177dfad9c6ddac588debce55ab0729704c8fd\AI-PLAYBOOK-758177dfad9c6ddac588debce55ab0729704c8fd.tar.gz`. Commit `758177dfad9c6ddac588debce55ab0729704c8fd`. Manifest `secrets_included` is `false`. `tests_recorded` is `ops.test_release_package`.

## Docker

Before the engine start, `docker version` exited **1**:

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

`com.docker.service` was Stopped (Manual). `wsl -l -v` exited **0** and listed only `docker-desktop`, version 2, Stopped.

```powershell
Start-Process -FilePath "C:\Program Files\Docker\Docker\Docker Desktop.exe" -PassThru
```

Exit **0**. PID `11480`. A poll of `docker version --format "{{.Server.Version}}"` then exited **0** with `29.8.2` (the start-and-poll command took about 54 seconds).

Later confirmation:

```powershell
docker version --format "client={{.Client.Version}} server={{.Server.Version}}"
```

Exit **0**. `client=29.8.2 server=29.8.2`.

No local images were present (`docker images` exit **0**, empty list). No container named `ai-playbook-fresh-recovery-20261022` existed.

```powershell
docker pull python:3.11-slim
```

Exit **0**. This is the CPU-only CPython image, not model weights.

```text
Digest: sha256:cce12316475d7d56d605f76e1d811d0dc4e7227f2d4afd29951521264f504ff8
Status: Downloaded newer image for python:3.11-slim
```

## Extract and new container

The destination did not exist. Recover ran from `C:\Users\henok\src\AI-PLAYBOOK.md` only after the sidecar match.

```powershell
$dest = Join-Path $env:TEMP "ai-playbook-fresh-recovery-20261022-758177df"
Set-Location "C:\Users\henok\src\AI-PLAYBOOK.md"
& $py -m ops.release.recover --archive $archive --sha256 d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82 --destination $dest
```

Exit **0**.

```text
extracted=C:\Users\henok\AppData\Local\Temp\ai-playbook-fresh-recovery-20261022-758177df
automatic: checksum verified and source extracted
human: provision an operator before restarting the console
human: on the Pod, keep model weights on /workspace and use ops/release/START.sh or deploy-console-only.sh
human: do not treat this extraction as a running deployment
```

The extract has no `.git` directory.

```powershell
docker run -d --name ai-playbook-fresh-recovery-20261022 --network none python:3.11-slim sleep infinity
```

Exit **0**. Container `a47b41ec6a6e7ba89512f6cc751ca44c886400e30786e7048f135f3a997fa03e`. Before the copy, Python was `3.11.17` and `/opt/ai-playbook` was absent. The image root was only the stock filesystem.

```powershell
docker exec ai-playbook-fresh-recovery-20261022 mkdir -p /opt/ai-playbook
docker cp "$dest\." ai-playbook-fresh-recovery-20261022:/opt/ai-playbook
```

Both exited **0**. Inside the container: `files=339`, `bytes=2679552`, `run_tests=True`, `weight_files=0`.

```text
image=python:3.11-slim network=none mounts=0 devices=null
```

The host checkout was not mounted. The container’s writable layer received only the recovered tree.

## Offline tests

From the recovered tree inside that container:

```powershell
docker exec -e PYTHONUNBUFFERED=1 -w /opt/ai-playbook ai-playbook-fresh-recovery-20261022 python -m ops.run_tests
```

Exit **1**.

```text
SUMMARY modules=41 ok=38 failed=3 elapsed_s=49.6
```

Failed modules:

| Module | Result | Cause |
| --- | --- | --- |
| `ops.test_git_parity` | 4 tests, 1 error | `test_this_checkout_origin_matches_without_network`: `ReleaseError: a working git executable was not found`. The stock image has no `git`. The extract also has no `.git`, so this test is aimed at a tree that is not a checkout. |
| `ops.test_release_package` | 9 tests, 1 error | `test_git_executable_prints_a_version` failed with the same missing `git`. The other eight tests in that module passed (`...E.....`). |
| `rag.tests.test_document_loaders` | 1 failure, 8 errors | `ModuleNotFoundError: No module named 'pypdf'` and `No module named 'openpyxl'`. Those parsers were not installed. The container network was `none`, so nothing was downloaded during the suite. |

`ops.test_qwen_blackwell_runtime` was among the 38 modules that passed. That is the offline pin check in this archive. It is not a Blackwell GPU result and it does not satisfy the `blackwell` gate.

The container was then stopped so `sleep infinity` would not keep running:

```powershell
docker stop ai-playbook-fresh-recovery-20261022
```

Exit **0**. Inspect after stop: `status=exited`, `exit=137` (the stop signal to `sleep`), `oom=false`. That 137 is the stop of the sleep process, not the test exit code. The test exit code remains **1**. Docker Desktop was left running. The container and the temp extract were left in place.

## Repeat after installing git, pypdf, and openpyxl

Same PC, new empty destination, new container. This still does not pass `fresh_recovery`.

Checksum command was the same Python check as above, against the same archive and sidecar. Exit **0**. `match=true`. Archive bytes 710946.

```powershell
python -m ops.release.recover --archive $archive --sha256 d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82 --destination $env:TEMP\ai-playbook-fresh-recovery-20261022c-758177df
```

Exit **0**. Destination did not exist before the command.

```powershell
docker run -d --name ai-playbook-fresh-recovery-20261022c python:3.11-slim sleep infinity
```

Exit **0**. Container `c9db3c274f653d58cc112ee2fa91d2d8975a766ea9a53a963a8d8f956eba3622`. Network was the default bridge so the install could download. The earlier container stayed `--network none` and was not reused.

```powershell
docker exec ai-playbook-fresh-recovery-20261022c mkdir -p /opt/ai-playbook
docker cp <extract>\. ai-playbook-fresh-recovery-20261022c:/opt/ai-playbook
```

Both exit **0**.

```powershell
docker exec ai-playbook-fresh-recovery-20261022c sh -c "apt-get update -qq && apt-get install -y -qq git && git --version"
```

Exit **0**. `git version 2.47.3`.

```powershell
docker exec ai-playbook-fresh-recovery-20261022c python -m pip install --disable-pip-version-check -q pypdf==6.20.0 openpyxl==3.1.5 et-xmlfile==2.0.0 defusedxml==0.7.1
```

Exit **0**.

```powershell
docker exec -e PYTHONUNBUFFERED=1 -w /opt/ai-playbook ai-playbook-fresh-recovery-20261022c python -m ops.run_tests
```

Exit **1**.

```text
SUMMARY modules=41 ok=40 failed=1 elapsed_s=52.4
```

The three earlier failures (`ops.test_git_parity` missing git, `ops.test_release_package` missing git, `rag.tests.test_document_loaders` missing pypdf and openpyxl) are gone except one. `ops.test_git_parity` still errors in `test_this_checkout_origin_matches_without_network`: `fatal: not a git repository`. The archive has no `.git` directory. `git --version` itself succeeded, and the other tests in that module passed.

```powershell
docker stop ai-playbook-fresh-recovery-20261022c
```

Exit **0**. The container was stopped so `sleep infinity` would not keep running.

`fresh_recovery_ok` was not recorded. The board rule still requires a fresh machine or a new pod.

## What this does not decide

- The package does not contain Qwen weights and this run did not download them.
- A passing extract plus a local container does not satisfy `fresh_recovery`.
- Production stays on the existing board. This file does not change it.
