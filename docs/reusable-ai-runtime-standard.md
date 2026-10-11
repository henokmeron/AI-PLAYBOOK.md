# Reusable AI Runtime and Model-Switching Standard

## Purpose

Build the AI platform once and reuse it. Do not manually reinstall Python, vLLM, PyTorch, and dependencies for every model or every Pod unless a compatibility change genuinely requires it.

## Preserve both baseline and working state

Maintain two distinct records:

1. **Baseline recipe:** pinned versions, installation commands, hardware/driver assumptions, and clean configuration templates. Never overwrite this with experimental changes.
2. **Verified working profile:** the exact versions and configuration that have passed a real model-generation test. Record changes as a separate profile or revision, with a reason and test result.

Do not call a setup "working" merely because the vLLM server starts. A successful test must send a chat-completion request and receive a valid generated response.

## Persistence requirements

- Keep model weights on RunPod Global Volume and retain the independent Azure model copy.
- Preserve reusable software artifacts in persistent storage wherever the storage supports them correctly: dependency wheels/cache, pinned requirements or lock files, setup scripts, launch scripts, configuration templates, and relevant logs.
- Keep source code, setup recipes, compatibility notes, and change history in GitHub.
- Where practical, keep an independent copy of important software artifacts in Azure.
- Never rely on a Pod's temporary filesystem (for example `/tmp`) as the only copy of a required environment or artifact.
- Verify actual persistence by recreating/restarting a Pod and restoring or reusing the setup. Do not assume persistence because a file appeared to save.

## Important Global Volume constraint

The current RunPod Global Volume is mounted at `/workspace` using a FUSE-based filesystem. Earlier attempts encountered permission limitations when installing software there. Therefore, do not assume a conventional Python virtual environment stored directly on the volume will be executable or reliable. Test required filesystem behaviour (permissions, executable files, symlinks and package operations) before adopting that layout.

If a virtual environment cannot be used reliably on Global Volume, preserve a reproducible package cache/wheelhouse and setup recipe there, or use another persistent, versioned software artifact/container-image approach supported by the RunPod deployment. The recovery process must be documented and tested. The user’s requirement is to avoid repeating manual installation; a temporary environment alone does not satisfy it.

## Model portability

- Treat the model as a replaceable component, not as part of the platform installation.
- Keep model weights separate from the Python/vLLM runtime.
- Use a model-specific configuration for model path/name, context length, GPU memory utilization, dtype/quantization where applicable, and other required options.
- Check each candidate model's architecture support, vLLM version requirements, tokenizer/processor needs, license, memory footprint, and hardware compatibility before deployment.
- Reuse the same pinned vLLM/Python environment when compatible. If a model requires another version, create a separate named runtime profile rather than breaking the verified baseline.
- Do not assume one runtime version supports every present or future model.

## Current Gemma 4 31B baseline

Previously recorded environment:
- RunPod H100 NVL, approximately 94 GB VRAM.
- Python 3.12.3.
- vLLM 0.31.0.
- PyTorch 2.13.0+cu129.
- Model files on Global Volume at `/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it`.
- The vLLM server reached "Application startup complete" and a real `/v1/chat/completions` request returned `model works`; end-to-end generation is confirmed on the current Pod.
- The environment was installed at `/tmp/vllm-clean-env`, so it must be treated as temporary and not as a persistent solution.

These are historical observations, not a guarantee that the environment still exists or that this version combination is the best choice for future models. Re-check the current Pod, versions, CUDA/driver compatibility, and model support before spending on GPU time.

## Acceptance checklist before declaring the setup reusable

- [ ] Confirm the existing model files are present; do not re-download unnecessarily.
- [ ] Record OS/container image, Python, vLLM, PyTorch, CUDA runtime, GPU and driver information.
- [ ] Save pinned dependencies and reproducible install/launch scripts.
- [ ] Store persistent artifacts in a location whose filesystem behaviour has been tested.
- [ ] Start vLLM and receive a valid response from a real chat-completion request.
- [ ] Restart or recreate a Pod and recover the service without repeating manual troubleshooting.
- [ ] Confirm a second supported model can be selected by configuration, or document the exact compatibility exception.
- [ ] Update this document and the runbook with the test outcome, commands, and any limitations.

## Operating rule

Before paid GPU work, plan the smallest test that can prove persistence and model generation. Stop the GPU Pod when testing is complete. Do not delete the Azure model backup or the only known-good artifacts while validating a new setup.


## Update — 2026-10-11: verified inference, backup integrity, and evaluation start

- Current Pod environment: Python 3.12.3, vLLM 0.31.0, PyTorch 2.13.0, PyTorch CUDA build 12.9, TorchVision 0.28.0, TorchAudio 2.11.0, Triton 3.7.1.
- `uv cache dir` is `/tmp/uv-cache`; all runtime temp paths are explicitly redirected to `/tmp`.
- PyTorch reported CUDA available and detected an NVIDIA H100 NVL. Driver shown by `nvidia-smi`: 580.126.09.
- Server startup and a real generation request have been confirmed.
- A compressed environment snapshot, pinned package listing and manifest exist on Global Volume. Checksums and `zstd -t` passed; restore remains unverified because a second GPU Pod could not be provisioned due to RunPod capacity.
- A new dependency-free baseline evaluation script has been added at `evaluation/run_chat_eval.py`. Run it before declaring the evaluation baseline recorded. Avoid model/runtime changes during this step.
