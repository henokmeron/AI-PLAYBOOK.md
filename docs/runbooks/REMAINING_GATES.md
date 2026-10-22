# Remaining live gates

These four gates are open. Nothing here starts a pod, copies model weights, or creates a paid resource. Production stays NO-GO until each one has its own live evidence.

## Second Windows computer

This development PC does not count. No second computer is enrolled. The pod keeps the device list in `/tmp/endpoint-devices.json` unless `ENDPOINT_STATE_FILE` is a persistent path, and that `/tmp` file is lost when the pod stops.

On the second Windows computer:

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

A temp extract on this PC does not count. Docker Desktop is installed and its engine is stopped (`docker version` cannot reach the pipe). Starting that engine and recovering into a new container uses no paid resource. It is CPU-only and does not load the model.

The newest local archive with a matching checksum is commit `758177dfad9c6ddac588debce55ab0729704c8fd`, SHA-256 `d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82`. Newer archives `00894206…` and `d6d3ac2f…` have no checksum file.

```powershell
python -m ops.release.recover --archive "$env:LOCALAPPDATA\AI-PLAYBOOK\releases\758177dfad9c6ddac588debce55ab0729704c8fd\AI-PLAYBOOK-758177dfad9c6ddac588debce55ab0729704c8fd.tar.gz" --sha256 d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82 --destination <empty-directory>
```

`recover` checks the checksum and extracts. It does not start Qwen, the gateway, or the console.

## Blackwell

Blocked until a Blackwell pod is approved. The current A100 cannot run this stack. Requirements from `ops/blackwell-runtime.lock`: compute capability 12 or higher, NVIDIA driver 575 or newer, CUDA 12.9, vLLM `0.32.0+cu129`, torch `2.13.0+cu129`. The A100 torch build `2.13.0+cu126` is rejected. Install needs about 20 GiB free. The start script waits up to 45 minutes for the model to load.

On an approved pod with the Global Volume attached, and only after that approval:

```bash
bash /tmp/AI-PLAYBOOK/ops/install-qwen-blackwell-env.sh --install
bash /tmp/AI-PLAYBOOK/ops/start-qwen-blackwell.sh --check
bash /tmp/AI-PLAYBOOK/ops/start-qwen-blackwell.sh --infer
```

## Independent weight backup

The Qwen weights (about 52 GB) and the runtime archive exist on Global Volume `cmv2p5m0d000007jk9o3931ea` only. Code is on GitHub and in local release archives. Copying the weights needs an approved destination, the transfer cost, and the transfer time. Do not copy them until that destination is approved.
