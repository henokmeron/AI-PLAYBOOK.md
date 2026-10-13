#!/usr/bin/env bash
# Explicit one-GPU model switch. Never loads Gemma and Qwen together.
# Does NOT change models/registry.yaml production default.
set -Eeuo pipefail

TARGET="${1:-}"
DIAG=/workspace/platform-diagnostics/tonight
mkdir -p "$DIAG"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

usage() {
  cat <<'EOF'
Usage: ops/switch-gpu-model.sh <gemma|qwen>

  gemma  Stop Qwen (:8002) if running, then start Gemma stack via existing scripts.
  qwen   Stop Gemma (:8000) if running, then start isolated Qwen (:8002).

Safety:
  - Requires explicit target; refuses unknown values.
  - Does not touch production registry default.
  - Main :8010/:8080 start is separate and requires operator approval.
EOF
}

port_up() {
  local port="$1"
  curl -fsS --max-time 2 "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1
}

stop_port_process() {
  local port="$1"
  local label="$2"
  if port_up "$port"; then
    log "Stopping $label on :$port"
    pkill -f "vllm serve.*--port ${port}" 2>/dev/null || true
    sleep 3
  fi
  if port_up "$port"; then
    log "ERROR: $label still responding on :$port after stop attempt"
    return 1
  fi
  log "$label is down on :$port"
}

if [[ -z "$TARGET" || "$TARGET" == "-h" || "$TARGET" == "--help" ]]; then
  usage
  exit 2
fi

case "$TARGET" in
  gemma)
    stop_port_process 8002 qwen || exit 1
    if [[ ! -x /tmp/vllm-clean-env/bin/vllm ]]; then
      log "ERROR: Gemma env /tmp/vllm-clean-env missing. Restore from /workspace/runtime-setup/vllm-clean-env.tar.zst first."
      exit 3
    fi
    log "Start Gemma with your documented main serve recipe on :8000 (not auto-started here to avoid unapproved main-stack restart)."
    log "After Gemma :8000 is healthy, start main gateway/console only with approval."
    echo "NEXT=start-gemma-manually-on-8000" | tee "$DIAG/last-switch.txt"
    ;;
  qwen)
    stop_port_process 8000 gemma || true
    if [[ ! -x /tmp/vllm-qwen-env/bin/vllm ]]; then
      log "ERROR: Qwen env /tmp/vllm-qwen-env missing. Reinstall isolated env per docs/qwen3.5-27b-integration.md"
      exit 3
    fi
    if port_up 8002; then
      log "Qwen already healthy on :8002"
    else
      log "Starting isolated Qwen via ops/start-qwen-isolated.sh --start"
      bash "$(dirname "$0")/start-qwen-isolated.sh" --start
    fi
    echo "NEXT=qwen-8002" | tee "$DIAG/last-switch.txt"
    ;;
  *)
    usage
    exit 2
    ;;
esac
