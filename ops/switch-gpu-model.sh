#!/usr/bin/env bash
# Explicit one-GPU model switch. Never loads Gemma and Qwen together.
# Does NOT change models/registry.yaml production default.
# Does NOT start main :8010/:8080 without separate approval.
#
# Safety gates:
#   --dry-run     print the plan only (default if SWITCH_CONFIRM is unset)
#   SWITCH_CONFIRM=yes   required for any stop/start action
set -Eeuo pipefail

TARGET="${1:-}"
MODE="${2:-}"
DIAG=/workspace/platform-diagnostics/tonight
mkdir -p "$DIAG"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

usage() {
  cat <<'EOF'
Usage:
  ops/switch-gpu-model.sh <gemma|qwen> --dry-run
  SWITCH_CONFIRM=yes ops/switch-gpu-model.sh <gemma|qwen>

  gemma  Stop Qwen (:8002) if running, then require Gemma env + manual/approved :8000 start.
  qwen   Stop Gemma (:8000) if running, then start isolated Qwen (:8002) if down.

Safety:
  - Refuses unknown targets.
  - Does not touch production registry default.
  - Does not auto-start main gateway/console (:8010/:8080).
  - Without SWITCH_CONFIRM=yes, runs as dry-run only.
  - Gemma path requires /tmp/vllm-clean-env (restore from archive first).
EOF
}

port_up() {
  local port="$1"
  curl -fsS --max-time 2 "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1
}

status_line() {
  printf ' :8000 Gemma  %s\n' "$(port_up 8000 && echo UP || echo down)"
  printf ' :8002 Qwen   %s\n' "$(port_up 8002 && echo UP || echo down)"
  printf ' gemma env    %s\n' "$([[ -x /tmp/vllm-clean-env/bin/vllm ]] && echo PRESENT || echo MISSING)"
  printf ' qwen env     %s\n' "$([[ -x /tmp/vllm-qwen-env/bin/vllm ]] && echo PRESENT || echo MISSING)"
  printf ' qwen archive %s\n' "$([[ -f /workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst ]] && echo PRESENT || echo MISSING)"
  printf ' gemma archive %s\n' "$([[ -f /workspace/runtime-setup/vllm-clean-env.tar.zst ]] && echo PRESENT || echo MISSING)"
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

DRY_RUN=1
if [[ "${SWITCH_CONFIRM:-}" == "yes" && "$MODE" != "--dry-run" ]]; then
  DRY_RUN=0
fi
if [[ "$MODE" == "--dry-run" ]]; then
  DRY_RUN=1
fi

log "Current state:"
status_line | tee "$DIAG/switch-state-before.txt"

case "$TARGET" in
  gemma)
    if [[ "$DRY_RUN" == 1 ]]; then
      log "DRY-RUN plan for gemma:"
      log "  1) Stop Qwen vLLM on :8002 (frees GPU)."
      log "  2) Ensure /tmp/vllm-clean-env via scripts/restore-vllm-environment.sh if missing."
      log "  3) Start Gemma on :8000 using documented serve command (NOT done by this script)."
      log "  4) Start main :8010/:8080 only with explicit operator approval."
      log "Set SWITCH_CONFIRM=yes to execute the Qwen stop only after approval."
      exit 0
    fi
    stop_port_process 8002 qwen || exit 1
    if [[ ! -x /tmp/vllm-clean-env/bin/vllm ]]; then
      log "ERROR: Gemma env /tmp/vllm-clean-env missing."
      log "Restore with: bash scripts/restore-vllm-environment.sh"
      log "Then start Gemma on :8000 using the recovery runbook; do not run install-vllm.sh."
      exit 3
    fi
    log "Qwen stopped. Gemma env present. NOT auto-starting :8000/:8010/:8080."
    log "Next approved step: start Gemma serve on :8000, then optionally main gateway/console."
    echo "NEXT=start-gemma-manually-on-8000" | tee "$DIAG/last-switch.txt"
    ;;
  qwen)
    if [[ "$DRY_RUN" == 1 ]]; then
      log "DRY-RUN plan for qwen:"
      log "  1) Stop Gemma vLLM on :8000 if up (frees GPU)."
      log "  2) Ensure /tmp/vllm-qwen-env (live or restore from /workspace/runtime-setup/qwen-vllm/)."
      log "  3) Start isolated Qwen on :8002 via ops/start-qwen-isolated.sh --start if down."
      log "  4) Leave main :8010/:8080 untouched."
      exit 0
    fi
    stop_port_process 8000 gemma || true
    if [[ ! -x /tmp/vllm-qwen-env/bin/vllm ]]; then
      if [[ -f /workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst ]]; then
        log "ERROR: Qwen env missing in /tmp. Restore from archive is prepared but not auto-run here."
        log "Manual restore outline: verify SHA256SUMS, extract to /tmp/vllm-qwen-env only if absent, then start-qwen-isolated.sh --start"
        exit 3
      fi
      log "ERROR: Qwen env missing and no volume archive found."
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

log "State after action:"
status_line | tee "$DIAG/switch-state-after.txt"
