# Remaining live gates

These four gates are open. Nothing here starts a pod, copies model weights, or creates a paid resource. Production stays NO-GO until each one has its own live evidence.

## Second Windows computer

This development PC does not count, and the Linux pod does not count. A loopback enrolment on this PC was run with the fixture name and `--fixture-label not-the-second-endpoint`. The device record sets `counts_as_second_endpoint` to false. That rehearsal is not evidence for this gate.

The pod keeps the device list in `/tmp/endpoint-devices.json` unless `ENDPOINT_STATE_FILE` is a persistent path, and that `/tmp` file is lost when the pod stops.

These steps still require a different physical Windows PC:

1. Install Python 3.11 or newer and a copy of this repo.
2. Open an SSH tunnel so the console is at `http://127.0.0.1:8080` on that computer. The worker refuses plain HTTP to any other host.
3. In the signed-in console, IT Helpdesk, choose **Create an enrolment code**.
4. On the second computer:

```powershell
python -m integrations.endpoint_worker enrol --console http://127.0.0.1:8080 --code "<one-time-code>" --name "Office PC 2" --token-file "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
python -m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file "$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
```

The device secret is written to that file and is not printed. Do not paste the secret or the one-time code into chat, docs, or git.

## Fresh recovery

A temp extract on this PC does not count, including a new container on this same PC. The gate stays unmet until the same checksum-verified recover runs on a fresh machine or a new pod.

The archive used below is commit `758177dfad9c6ddac588debce55ab0729704c8fd`, SHA-256 `d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82`. It does not contain `.git` or the model weights. A stock `python:3.11-slim` image also has no `git`, `pypdf`, or `openpyxl`. Install those in the new environment before `python -m ops.run_tests`. The first container, with `--network none`, could not install them and the suite exited 1 (38 of 41 modules). A later container on this same PC installed them and the suite exited 1 with 40 of 41 modules: the remaining failure is `ops.test_git_parity` because the extract is not a git checkout.

On the machine that holds the archive, recover into an empty directory:

```powershell
python -m ops.release.recover --archive "$env:LOCALAPPDATA\AI-PLAYBOOK\releases\758177dfad9c6ddac588debce55ab0729704c8fd\AI-PLAYBOOK-758177dfad9c6ddac588debce55ab0729704c8fd.tar.gz" --sha256 d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82 --destination <empty-directory>
```

`recover` checks the checksum and extracts. It does not start Qwen, the gateway, or the console.

Inside the new container, after that extract is copied in:

```bash
apt-get update && apt-get install -y git
python -m pip install pypdf==6.20.0 openpyxl==3.1.5 et-xmlfile==2.0.0 defusedxml==0.7.1
python -m ops.run_tests
```

The install needs a network. It does not copy model weights. `git` makes `git --version` succeed. It does not turn the extract into a checkout, so `test_this_checkout_origin_matches_without_network` still fails until the tree is a clone of the published repo.

## Blackwell

Blocked until the owner approves a new pod. The running A100 cannot run this stack, and this runbook does not create one. Approval has to name the GPU, accept a new hourly compute charge for that pod, and accept up to 45 minutes of model-load time (the start script's 2,700-second readiness timeout) plus the install. The install needs at least 20 GiB free. No Blackwell hourly price is recorded here.

Requirements from `ops/blackwell-runtime.lock`: compute capability 12 or higher, NVIDIA driver 575 or newer, CUDA 12.9, vLLM `0.32.0+cu129`, torch `2.13.0+cu129`. The A100 torch build `2.13.0+cu126` is rejected. The CUDA 13.0 vLLM wheel was absent (HTTP 404 on 2026-10-21).

On an approved pod with the Global Volume attached, and only after that approval:

```bash
bash /tmp/AI-PLAYBOOK/ops/install-qwen-blackwell-env.sh --install
bash /tmp/AI-PLAYBOOK/ops/start-qwen-blackwell.sh --check
bash /tmp/AI-PLAYBOOK/ops/start-qwen-blackwell.sh --infer
```

## Independent weight backup

The Qwen weights (about 52 GB, 11 shard files, not re-hashed in the 2026-10-22 inventory) and the runtime archive exist on Global Volume `cmv2p5m0d000007jk9o3931ea` only. That volume was 126.0 GB stored and $11.34/mo. Code is on GitHub and in local release archives. Those archives do not contain the weights. Copying about 52 GB needs an approved destination, the storage cost of that copy, and the transfer time. Do not copy them until that destination is approved. No copy was made.
