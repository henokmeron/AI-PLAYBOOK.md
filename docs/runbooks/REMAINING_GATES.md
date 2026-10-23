# Remaining live gates

These gates are open. Nothing here starts a pod, copies model weights, or creates a paid resource. Production stays NO-GO until each mandatory one has its own live evidence.

## Microsoft content match

A count-only list of message ids was HTTP 200 with count 9 on 2026-10-22T23:28Z. A phrase search for `the`, and `contains(subject,'the')`, were HTTP 200 with count 0. No subject or body was stored. `Mail.Send` is not granted. That is not `mailbox_content_match_ok`.

Do not open a subject to invent the query. The owner can supply one harmless distinctive phrase that is already in the mailbox. Record only the HTTP status, the count, and whether that phrase was present.

## Second Windows computer

This development PC does not count, and the Linux pod does not count. A loopback enrolment on this PC was run with the fixture name and `--fixture-label not-the-second-endpoint`. The device record sets `counts_as_second_endpoint` to false. That rehearsal is not evidence for this gate.

The live device list stays `/tmp/endpoint-devices.json` so the file can be mode 0600. `/tmp` is not chmodded. When `/workspace` is the Global Volume, a checksummed mirror is kept at `/workspace/platform-state/endpoint-backups/<stamp>/` and the next console start restores it onto local disk if the live file is gone. The mirror holds enrolment-code hashes, device-secret hashes, and diagnostic summaries. It is not a private POSIX store. The Microsoft token and the gateway key are not in it. Restoring that file does not pass this gate.

These steps still require a different physical Windows PC:

1. Install Python 3.11 or newer and a copy of this repo.
2. Open an SSH tunnel so the console is at `http://127.0.0.1:8080` on that computer. The worker refuses plain HTTP to any other host.
3. In the signed-in console, IT Helpdesk, choose **Create an enrolment code**.
4. On the second computer:

```powershell
python -m integrations.endpoint_worker enrol --console http://127.0.0.1:8080 --code=<one-time-code> --name="Office PC 2" --token-file="$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
python -m integrations.endpoint_worker report --console http://127.0.0.1:8080 --token-file="$env:LOCALAPPDATA\AI-PLAYBOOK\device-secret"
```

Keep the `=` after `--code`. A value that starts with `-` is dropped by the command parser when it is a separate argument, so the console never receives the code. Do not run `enrol` on BANYA-FAMILY-PL. That PC refuses it unless the fixture label is set, and the fixture does not count.

The device secret is written to that file and is not printed. Do not paste the secret or the one-time code into chat, docs, or git.

## Fresh recovery

A temp extract on this PC does not count, including a new container on this same PC. The gate stays unmet until the same checksum-verified recover runs on a fresh machine or a new pod.

The archive used below is commit `758177dfad9c6ddac588debce55ab0729704c8fd`, SHA-256 `d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82`. It does not contain `.git` or the model weights. A stock `python:3.11-slim` image also has no `git`, `pypdf`, or `openpyxl`. The first container, with `--network none`, could not install them and the suite exited 1 (38 of 41 modules). A later container on this same PC installed them and the suite exited 1 with 40 of 41 modules: `ops.test_git_parity` failed because the extract was not a git checkout.

On the machine that holds the archive, recover into an empty directory:

```powershell
python -m ops.release.recover --archive "$env:LOCALAPPDATA\AI-PLAYBOOK\releases\758177dfad9c6ddac588debce55ab0729704c8fd\AI-PLAYBOOK-758177dfad9c6ddac588debce55ab0729704c8fd.tar.gz" --sha256 d641667fdabf46b38d1091ea147497b548183a38bc65ce3dfed74d450ae3ae82 --destination <empty-directory>
```

`recover` checks the checksum and extracts. It then records `origin` as `https://github.com/henokmeron/AI-PLAYBOOK.md.git` in a new `.git` directory. It does not fetch, commit, start Qwen, the gateway, or the console. That origin is the metadata `test_this_checkout_origin_matches_without_network` reads. The test is not skipped.

Inside the new container, after that extract is copied in, run the clean-image script from a checkout that contains it (the `758177df` archive does not):

```bash
sh ops/release/install-clean-env.sh /opt/ai-playbook
python -m ops.run_tests
```

The script runs `apt-get install -y git` when `git` is missing, then `python -m pip install pypdf==6.20.0 openpyxl==3.1.5 et-xmlfile==2.0.0 defusedxml==0.7.1`. If `.git` is still absent it records the same origin. The install needs a network. It does not copy model weights and it does not fetch the repository.

On 2026-10-22 a new container on this same PC followed that path. The checksum matched, recover exited 0, and `python -m ops.run_tests` exited 0 (41 of 41). The record is `docs/results/fresh-recovery-2026-10-22-repeat.md`. That run does not pass this gate.

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
