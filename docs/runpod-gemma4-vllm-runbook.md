# RunPod Gemma 4 + vLLM Runbook

## Status (2026-10-11)

- GPU Pod: NVIDIA H100 NVL, 94 GB VRAM; Pod is billed while running.
- Model: `google/gemma-4-31B-it`, BF16, approximately 62.6 GB in Azure; the RunPod copy is on the persistent Global Volume mounted at `/workspace`.
- Confirmed model config: `/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it/config.json`.
- Serving software: vLLM 0.31.0; PyTorch 2.13.0+cu129; CUDA runtime reported by PyTorch: 12.6; GPU detected.
- Working Python environment: `/tmp/vllm-clean-env`. **This is Pod-local temporary storage, not persistent.** It may disappear if the Pod is recreated or its local disk is reset. Do not treat it as the durable installation.
- Latest screenshot/log showed `Application startup complete`, server listening on port 8000, and routes including `/v1/models` and `/v1/chat/completions`. This indicates the server started. An actual request still needs to be tested.
- To avoid prior Ninja failure, launch with `PATH=/tmp/vllm-clean-env/bin:$PATH` so the `ninja` executable is visible.
- Earlier failures included a missing CUDA runtime library from a mismatched package set, Torch/TorchAudio CUDA version mismatch, Ninja not on PATH, and a wrong model directory. Do not patch libraries individually or redownload the model to solve those errors.

## Current successful launch command

Run from a shell in the existing Pod (model path and environment are specific to this Pod):

```bash
export PATH="/tmp/vllm-clean-env/bin:$PATH"
export TMPDIR=/tmp
export VLLM_RPC_BASE_PATH=/tmp

/tmp/vllm-clean-env/bin/vllm serve \
  /workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.90
```

The terminal remains occupied while the server runs. Do not paste the shell prompt itself as part of a command.

## Minimal smoke test

With the server running, open the same RunPod HTTP proxy host in a browser and append `/v1/models`. Expect JSON listing the served model. For a generation test, use the proxy's `/v1/chat/completions` endpoint with a small request, or run this in a second shell inside the Pod:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it","messages":[{"role":"user","content":"Reply with exactly: model works"}],"max_tokens":12}'
```

## Storage and recovery boundaries

- **Persistent:** the model in RunPod Global Volume mounted at `/workspace`; Azure Blob Storage is the master backup.
- **Pod-local / not guaranteed durable:** `/tmp/vllm-clean-env`, local caches, logs such as `/tmp/gemma-vllm.log`, and shell environment variables. These are not the application source of truth.
- **Not yet built:** the actual AI product/platform layer (API wrapper, RAG, tools, agent workflows, UI, authentication, monitoring, deployment automation). At this stage we are validating model serving, not claiming the full product exists.
- GitHub stores the runbook and future source/configuration—not model weights.

## Before stopping the Pod

1. Confirm `/v1/models` responds and complete one generation request.
2. Save this runbook and any final version/config details in GitHub.
3. If GPU balance is nearly exhausted, stop the Pod promptly after testing. Do not delete the Global Volume or Azure model copy.
4. A future recreation should use a tested, pinned image/container or a tested setup script stored in GitHub. This current `/tmp` environment alone cannot guarantee a two-minute rebuild; that requires packaging and validating the full environment separately.

## Repeatability plan (next engineering task)

Create and test a pinned deployment recipe (ideally a container image or reproducible image template) with the Python, vLLM, PyTorch/CUDA backend and launch configuration locked. Keep model weights on persistent storage. Test the recipe on a fresh Pod before claiming it is reproducible. Keep the smoke test as a deployment gate. Never upgrade individual CUDA/Torch packages without validating the entire compatible set first.

## Resume checklist for the next session

**Do not immediately reinstall. First inspect what survived.** After starting the existing Pod, run these checks in the terminal:

```bash
nvidia-smi
ls -ld /workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it
test -x /tmp/vllm-clean-env/bin/vllm && /tmp/vllm-clean-env/bin/vllm --version || echo "Previous temporary vLLM environment is missing"
```

- If `/tmp/vllm-clean-env/bin/vllm` exists, inspect and try that existing environment before installing anything.
- If it is missing, do **not** assume the model is lost: check the Global Volume model path separately. The model and Python environment have different persistence boundaries.
- Do not promise a five-minute rebuild: the previous install took time and required troubleshooting. First test what remains; then make the setup reproducible.
- If the environment is missing, record that fact and follow the persistent-runtime plan. Do not perform a large GPU install until the user agrees and the persistence approach is clear.
- Once vLLM starts, test `/v1/models` and send the chat-completion smoke test above. A server startup message alone is not proof that generation works.
- Keep the server terminal open while testing; use a second terminal or the RunPod proxy to make requests. Stop the Pod after testing if it is not needed.

## Operator limitation

The assistant cannot directly start or type into the user's RunPod Pod from this chat. The user must start the Pod and provide the terminal access/output (or screenshots); then instructions can be given one command at a time based on the actual result. The assistant should not claim a command ran unless its output was provided and checked.

## Rebuild session findings — 2026-10-11 evening

The new Pod was deployed with the Global Volume `New model container` mounted at `/workspace`. It uses an NVIDIA H100 NVL (94 GB VRAM), the RunPod PyTorch 2.8.0 template, Python 3.12.3, and `uv 0.9.0`. `nvidia-smi` reports driver 580.126.09 and CUDA 13.0. This CUDA label is the driver capability and must not be confused with the CUDA runtime bundled with PyTorch.

The following were observed in the Global Volume:
- Model config exists at `/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it/config.json`.
- Model directory occupies about 59 GB.
- `/workspace/vllm-env` is an incomplete/broken environment: its `pyvenv.cfg` points to `/usr/local/bin`, and Python launcher files are zero-byte or symlinks targeting `/usr/local/bin/python`. Do not try to use it or treat it as a working vLLM install.
- `/workspace/.uv-cache` is about 90 MB and `/workspace/uv-cache-fresh` about 168 KB. The cache includes some Torch/TorchAudio/TorchVision/Triton-related cache entries but is not known to contain the complete dependency set.
- No requirements file, lock file, Dockerfile or install script was found in the diagnostic search under `/workspace`.
- The mount is FUSE-backed (`fuse.geeseefs`). Earlier attempts to create a normal executable virtual environment directly on this filesystem produced unusable zero-byte launchers. Do not create the main venv on Global Volume without a successful filesystem capability test.

### Rebuild policy for this Pod

1. Do not delete or redownload the model.
2. Preserve the original baseline and create a separate clean runtime profile.
3. Keep install scripts, exact version pins, configuration and reusable package artifacts on the Global Volume. The 90 MB existing cache is insufficient evidence that the full environment is cached.
4. Do not rely on a venv directly on Global Volume unless a real Python/vLLM execution test proves it works.
5. Prefer a tested approach that stores a complete wheelhouse or equivalent install artifacts persistently, and recreates the executable venv on Pod-local storage from those artifacts; alternatively use a versioned persistent container image if supported. This avoids redownloading packages where the persistent artifacts suffice, while acknowledging the executable environment may need recreation.
6. Before a large install, ensure enough free Pod-local disk for vLLM, PyTorch and build/cache overhead. Check storage capacity and package compatibility first.
7. Launch vLLM, query `/v1/models`, then send a real `/v1/chat/completions` request. Server startup alone is not success.
8. Capture exact package versions, command lines and test result. Only call the setup reusable after confirming artifacts remain on Global Volume and can recreate the working environment.



## Error register and prevention log — 2026-10-11

Use this as a preflight checklist; do not repeat a failed install command without correcting the specific cause.

### Confirmed errors and resolutions

1. **Wrong/incomplete virtual environment on Global Volume.** A prior `/workspace/vllm-env` contained unusable zero-byte launchers/symlinks and was not a real working vLLM environment. Resolution: abandon it; create a fresh venv on local `/tmp`. Never reuse it.
2. **Global Volume does not support normal POSIX permission behavior.** `chmod` on `/workspace/runtime-setup/install-vllm.sh` failed with `Operation not permitted`. Resolution: call the readable script with `bash /workspace/runtime-setup/install-vllm.sh`; do not rely on executable permission or chmod on the mount.
3. **uv cache silently defaulted to the Global Volume.** Even though the venv was under `/tmp`, an install failed while extracting `llguidance` at `/workspace/.cache/uv/tmp.../llguidance/_lib.abi3.so`, specifically because file permissions could not be set. Resolution: explicitly export `UV_CACHE_DIR=/tmp/uv-cache` and `TMPDIR=/tmp` before both venv creation and package install. Verify with `uv cache dir` before retrying.
4. **A shell chain masked the fact that the setup did not run.** The earlier command used `&& chmod ... && bash ...`; because chmod failed, the final bash step was skipped. Resolution: avoid chmod and execute `bash script` explicitly; inspect the output before assuming a script ran.
5. **Multiline terminal paste was unreliable.** A multiline script pasted line-by-line left the shell at continuation prompts and was not saved as intended. Resolution: provide one complete command to copy/paste, or carefully save a file by a method validated in that terminal. Do not assume a displayed command executed.
6. **Ninja was not on PATH at runtime.** Resolution recorded from the prior launch: set `PATH="/tmp/vllm-clean-env/bin:$PATH"` before launching vLLM so environment-installed executables are found.
7. **Temporary IPC/runtime files conflicted with mounted-storage limitations.** Prior launch used defaults that did not work reliably with the mount. Resolution recorded in the working launch command: `TMPDIR=/tmp` and `VLLM_RPC_BASE_PATH=/tmp`.
8. **A previous dependency set had a missing CUDA runtime library / incompatible CUDA-linked package set.** Resolution principle: use a coherent, pinned vLLM/PyTorch/CUDA environment; do not patch individual shared libraries or mix packages blindly. Recheck imports and the CUDA build after install.
9. **Torch and TorchAudio CUDA/version mismatch.** This was recorded among previous failures. Resolution principle: inspect exact installed versions and compatibility as one set before changing anything; do not upgrade individual Torch family packages ad hoc. Today's package listing alone is not proof of compatibility.
10. **Wrong model directory was used during a prior launch attempt.** The verified model path for this Pod has three repeated directory levels: `/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it`. Verify its `config.json` before serving; do not redownload the 59 GB model to solve a path issue.
11. **GPU/server startup was at risk of being mistaken for end-to-end success.** Prior records show server startup completed, but no confirmed generation result at that time. Resolution: check `/v1/models` and run an actual `/v1/chat/completions` request before declaring success.
12. **The new Pod had only 30 GB of local overlay disk.** The Global Volume's virtual FUSE capacity display is not a reliable measure of local temporary disk. Resolution: check `df -h / /tmp` before installing; today's installer stops if less than 25 GiB is available.
13. **Persistence boundaries were confused.** The model is persistent on Global Volume (and backed up in Azure); `/tmp/vllm-clean-env` and `/tmp/uv-cache` are local and may disappear on Pod recreation/reset. Resolution: distinguish the persistent model/setup files from the executable environment. Do not promise a persistent install until a rebuild-from-persistent-artifacts test passes.
14. **The setup recipe was not initially checked into a durable source before being run.** Resolution: keep setup script and this error register in GitHub and a readable copy on Global Volume. The executable bit is not needed when invoking with `bash`.
15. **Cost and destructive actions needed clearer guardrails.** The H100 NVL Pod is billed while running; model files must not be deleted to address software setup failures. Resolution: do not delete the Global Volume, model, or stopped Pods as an installation workaround; stop paid GPU compute when the user is finished testing, without deleting persistent data.

### Current install attempt — status

The 2026-10-11 screenshot shows a package list including `vllm==0.31.0` and `torch==2.13.0`, then a returned shell prompt without an installation error. This suggests that the install completed, but the environment is **not yet validated**. Next validation must be read-only and grouped: local disk, `uv cache dir`, vLLM version, PyTorch import, PyTorch CUDA build, `torch.cuda.is_available()`, GPU name, and `nvidia-smi`. Do not reinstall unless those checks identify a problem.

### Required preflight before any future install

- Confirm exact target venv and model path.
- Check `df -h / /tmp`; the Pod-local overlay was 30 GB.
- Set `TMPDIR=/tmp`, `UV_CACHE_DIR=/tmp/uv-cache`, and `VLLM_RPC_BASE_PATH=/tmp` explicitly.
- Confirm `uv cache dir` resolves to `/tmp/uv-cache`.
- Use a pinned, compatible package set and change one variable at a time.
- If installation fails, read the first actual error and correct that cause—never repeat the same command unchanged.
- After install, validate imports and GPU first, then start the server, check `/v1/models`, and make one generation request.
- Preserve a tested wheelhouse or versioned runtime image plus setup and configuration files, and verify fresh-environment recovery before calling the runtime reproducible.


## Local install validation — 2026-10-11 19:54 (user screenshot)

Read-only validation completed after installing with the uv cache explicitly placed under `/tmp`:
- Local overlay: 30 GB total, 7.9 GB used, 23 GB available (27% used).
- `uv cache dir`: `/tmp/uv-cache` — confirms cache is no longer resolving to `/workspace`.
- `vllm --version`: 0.31.0.
- Installed package versions: vLLM 0.31.0, PyTorch 2.13.0, TorchVision 0.28.0, TorchAudio 2.11.0, Triton 3.7.1.
- PyTorch CUDA build: 12.9; `torch.cuda.is_available()`: True; GPU detected: NVIDIA H100 NVL.
- `nvidia-smi`: driver 580.126.09, driver CUDA capability 13.0; GPU idle with 0 MiB used at check.
- Conclusion: the vLLM package install completed and PyTorch sees the GPU. This does not yet prove model loading or generation works. Next step is to launch with the recorded exact model path, then check `/v1/models` and one completion request. Do not reinstall unless serving or tests reveal a specific fault.


## Server startup confirmed — 2026-10-11 20:10 (user screenshot)

- Launched vLLM 0.31.0 from `/tmp/vllm-clean-env` with local `TMPDIR=/tmp`, `UV_CACHE_DIR=/tmp/uv-cache`, and `VLLM_RPC_BASE_PATH=/tmp`.
- Screenshot confirms server listening at `http://0.0.0.0:8000` and reports `Application startup complete.`
- Routes include `/v1/models` and `/v1/chat/completions`.
- This confirms server startup, but not yet that Gemma can complete a generation. Keep the serving terminal open and test from a second terminal:
  ```bash
  curl -sS http://127.0.0.1:8000/v1/models
  curl -sS http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it","messages":[{"role":"user","content":"Reply with exactly: model works"}],"max_tokens":12}'
  ```
- Only after the second request returns generated text should model serving be marked end-to-end verified.


## End-to-end generation confirmed — 2026-10-11 20:11 (user screenshot)

A real request to `http://127.0.0.1:8000/v1/chat/completions` succeeded. The request asked the model to reply exactly `model works`; JSON returned `choices[0].message.content = "model works"`, with `finish_reason = "stop"`. This proves the current vLLM server, model loading, and local chat-completions API work together on this Pod.

### Current verified baseline

- Model path: `/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it` on RunPod Global Volume.
- vLLM: 0.31.0.
- PyTorch: 2.13.0; CUDA build 12.9.
- GPU: NVIDIA H100 NVL, detected by PyTorch; driver 580.126.09.
- Python environment: `/tmp/vllm-clean-env` (Pod-local and temporary).
- uv cache: `/tmp/uv-cache` (Pod-local and temporary).
- Server: port 8000, max model length 4096, GPU memory utilization 0.90.
- Environment cache/temp path fix confirmed; do not reinstall this working environment unnecessarily.

### Next work — persistence and product

Do not change the working runtime while it is serving. Keep the serving terminal open when testing. The next engineering priority is to make a repeatable, pinned install/runtime and persist the reusable package artifacts/configuration separately from the temporary environment. The present successful test does not make `/tmp/vllm-clean-env` persistent: stopping/recreating the Pod may remove it. The Global Volume model and Azure backup must be preserved. Once durable recovery is validated, build an API wrapper and platform features in separate versioned steps.


## Persistence preparation preflight — 2026-10-11 20:14 (user screenshot)

- Local overlay: 30 GB total, 8.2 GB used, 22 GB available.
- Working environment at `/tmp/vllm-clean-env`: about 8.0 GB.
- Local uv cache at `/tmp/uv-cache`: about 100 MB.
- `uv pip check`: checked 199 packages; all installed packages are compatible according to pip's metadata consistency check.
- Persistent setup files already saved under `/workspace/runtime-setup`: `install-vllm.sh`, `requirements-frozen.txt`, and `runtime-manifest.txt`.
- Archive tools `zstd` and `pigz` are present on the Pod.
- Next operation: create a compressed snapshot of the exact working environment at `/workspace/runtime-setup/vllm-clean-env.tar.zst` on the Global Volume, then verify its compressed stream and tar directory listing. Do this without stopping the server.
- Important limitation: this archive is a snapshot, not a guarantee of portability across arbitrary base images. Recovery must use the same container/Python/CUDA-compatible base and extract to the same local path `/tmp/vllm-clean-env`; then verify vLLM version, torch CUDA availability, GPU detection, and a generation request. Keep the pinned requirements and setup script as independent rebuild options.


## Working environment archive created and verified — 2026-10-11 20:16 (user screenshot)

- Archive stored on Global Volume: `/workspace/runtime-setup/vllm-clean-env.tar.zst`.
- Compressed archive size from `ls -lh`: about 3.4 GB.
- `zstd -t` passed and reported uncompressed content size about 8.42 GB.
- Tar listing succeeded and contained 70,954 entries.
- Related persistent files: `install-vllm.sh`, `requirements-frozen.txt`, `runtime-manifest.txt`.
- This verifies the archive's compressed-stream integrity and readable tar index; it does **not** yet prove a restored environment can run. Next create a SHA-256 checksum file and preserve it with the archive. Recovery must be tested later on a compatible Pod/container without overwriting the currently working environment.
- Keep the server and Pod running until the restore/recovery strategy is documented. Do not delete the Global Volume or Azure model backup.


## Archive checksum recorded — 2026-10-11 20:36 (user screenshot)

The command `sha256sum vllm-clean-env.tar.zst requirements-frozen.txt runtime-manifest.txt install-vllm.sh > SHA256SUMS` completed and `cat SHA256SUMS` printed SHA-256 entries for all four files. The checksum file exists at `/workspace/runtime-setup/SHA256SUMS` (348 bytes per `ls -lh` screenshot).

Next, verify with `cd /workspace/runtime-setup && sha256sum -c SHA256SUMS && zstd -t vllm-clean-env.tar.zst`. A checksum and compressed-stream test confirm file integrity only; do not describe the environment as restore-tested yet. Python virtual environments commonly contain absolute paths, so a real restore test must use a compatible container and account for the original path `/tmp/vllm-clean-env`; do not extract over the currently serving environment.
