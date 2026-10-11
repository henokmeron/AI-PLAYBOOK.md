# RunPod Global Volume — installation failure prevention

Date: 2026-10-11

## Confirmed failure

The install script created the executable environment at `/tmp/vllm-clean-env`, but `uv pip install vllm==0.31.0` failed while extracting `llguidance`. The error path was:

`/workspace/.cache/uv/tmp.../llguidance/_lib.abi3.so: failed to set permissions: Operation not permitted`

This proves that the uv cache/temp extraction path landed on the RunPod Global Volume (mounted at `/workspace`), despite the virtual environment being under `/tmp`. Global Volume is object-backed/FUSE and does not support all POSIX permission operations required by environments/caches. Do not retry the same command unchanged.

## Corrective rule

For installs that execute software, keep all of these on Pod-local storage:
- Python virtual environment (example: `/tmp/vllm-clean-env`)
- uv cache (set `UV_CACHE_DIR=/tmp/uv-cache` explicitly)
- temporary build/extraction files (set `TMPDIR=/tmp`)
- RPC/runtime temp files (set `VLLM_RPC_BASE_PATH=/tmp`)

Always explicitly set these variables in the installer script; do not assume defaults. Check `uv cache dir` and `env | grep -E '^(UV_CACHE_DIR|XDG_CACHE_HOME|TMPDIR|HOME)='` before retrying if cache location is uncertain.

A script can be stored on Global Volume and run with `bash /workspace/runtime-setup/install-vllm.sh`; do not rely on `chmod` there, because it may be rejected by FUSE.

## Persistence requirement

The Global Volume should hold model weights, plain-text setup scripts, requirements/lock files, configuration, and—after validation—portable package archives such as a wheelhouse. Do not store a live executable virtual environment or assume uv's cache layout can be reused from the Global Volume. The current 90 MB uv cache is not a complete installer cache. Do not claim the software is durably packaged until a package archive set has been saved and tested by rebuilding a fresh local environment from it.

## Preflight before retrying

1. Inspect environment variables and `uv cache dir`.
2. Check local disk space (`df -h / /tmp`); the local overlay is 30 GB and may limit package downloads/builds.
3. Confirm the model path exists; do not redownload it.
4. Force uv cache and temporary files to local storage.
5. Install only after preflight; then test `vllm --version`, GPU detection, server startup, `/v1/models`, and one real `/v1/chat/completions` request.
6. Only after the runtime works, save exact resolved versions and package archives persistently, and verify that a fresh local environment can be reconstructed.
7. Keep the Pod-local environment classified as temporary until this recovery test succeeds.

## Known errors to prevent

- Do not run `chmod` on Global Volume files.
- Do not create a venv under `/workspace`.
- Do not allow uv/pip caches or extraction temp directories to default under `/workspace`.
- Do not assume a large-looking FUSE capacity number means local working-disk space.
- Do not assume a shell script ran when an earlier `&& chmod` failed; check the final command/output.
- Do not blindly repeat an installation command after a permission error.
- Do not upgrade Python, vLLM, PyTorch, or CUDA components independently from a known-compatible set.
- Do not delete the Global Volume or model to solve a software-install error.
- Do not claim startup is successful until an actual generation request works.
- Do not claim reproducible persistence until package archives and a fresh rebuild have been tested.
