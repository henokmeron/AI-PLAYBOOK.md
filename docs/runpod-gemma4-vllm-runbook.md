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
