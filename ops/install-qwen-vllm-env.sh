#!/usr/bin/env bash
# Create an isolated vLLM environment for Qwen3.5. Never overwrites /tmp/vllm-clean-env.
set -Eeuo pipefail
umask 077

ENV_DIR="${QWEN_VLLM_ENV:-/tmp/vllm-qwen-env}"
GEMMA_ENV=/tmp/vllm-clean-env
MODE="${1:---install}"

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

[[ "$ENV_DIR" != "$GEMMA_ENV" ]] || fail "refusing to install into the Gemma environment"
[[ "$ENV_DIR" != /tmp/vllm-clean-env ]] || fail "refusing to install into /tmp/vllm-clean-env"

if [[ "$MODE" == "--check" ]]; then
  [[ -x "$ENV_DIR/bin/python" ]] || fail "missing $ENV_DIR/bin/python"
  "$ENV_DIR/bin/python" - <<'PY'
import vllm, torch
print("vllm", vllm.__version__)
print("torch", torch.__version__)
print("cuda_available", torch.cuda.is_available())
PY
  exit 0
fi

if [[ -e "$ENV_DIR" && ! -x "$ENV_DIR/bin/python" ]]; then
  fail "$ENV_DIR exists but looks incomplete; remove it manually after inspection"
fi

if [[ -x "$ENV_DIR/bin/vllm" ]]; then
  log "Reusing existing $ENV_DIR"
  exec bash "$0" --check
fi

command -v uv >/dev/null 2>&1 || fail "uv is required to create the isolated Qwen vLLM env"
log "Creating isolated venv at $ENV_DIR"
uv venv "$ENV_DIR"
# Official Qwen3.5 card: nightly/main vLLM in a fresh environment.
log "Installing vLLM nightly into isolated env (this does not modify $GEMMA_ENV)"
uv pip install -p "$ENV_DIR/bin/python" -U vllm --torch-backend=auto --extra-index-url https://wheels.vllm.ai/nightly
bash "$0" --check
log "DONE. Persist a verified archive under /workspace/runtime-setup/qwen-vllm after first success."
