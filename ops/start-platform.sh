#!/usr/bin/env bash
# Idempotent RunPod platform start/check entry point for the MAIN stack:
#   vLLM :8000, gateway :8010, console :8080
#
# This is a same-Pod SERVICE restart/recovery helper, not a Pod recreation tool.
# Healthy listeners are reused and never restarted. Secrets are never printed.
#
# Usage:
#   bash ops/start-platform.sh --check   # read-only health + asset summary
#   bash ops/start-platform.sh --start   # start only unhealthy/missing services
#   bash ops/start-platform.sh --help
#
# For isolated Document Q&A testing use ops/start-test-console-8082.sh (8012/8082).
# For artifact validation without starting anything use ops/preflight-recovery.sh.
set -Eeuo pipefail
umask 077

MODE="${1:---start}"
if [[ "$MODE" == "--help" || "$MODE" == "-h" ]]; then
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi
if [[ "$MODE" != "--start" && "$MODE" != "--check" ]]; then
  echo "Usage: bash ops/start-platform.sh [--check|--start|--help]" >&2
  exit 2
fi

VOL=/workspace
MODEL="$VOL/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it"
SETUP="$VOL/runtime-setup"
BACKUPS="$VOL/ai-platform-backups/deployed-runtime"
RUNTIME=/tmp/vllm-clean-env
GW=/tmp/platform-gateway-runtime
KEY=/tmp/platform-gateway.key
DEPS=/tmp/rag-deps
REPO=/tmp/AI-PLAYBOOK
DIAG="$VOL/platform-diagnostics"
mkdir -p "$DIAG"
LOG="$DIAG/start-platform.log"
exec 3>&1
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG" >&3; }
fail() { log "ERROR: $*"; exit 1; }
healthy() { curl -fsS --max-time 3 "$1" >/dev/null 2>&1; }

ensure_parser_deps() {
  # Prefer pinned setup scripts from a checkout; fall back to an existing /tmp/rag-deps.
  local root=""
  for candidate in /tmp/AI-PLAYBOOK-upload-test /tmp/AI-PLAYBOOK; do
    if [[ -f "$candidate/rag/setup_pdf_support.sh" && -f "$candidate/rag/setup_xlsx_support.sh" ]]; then
      root="$candidate"
      break
    fi
  done
  if [[ -n "$root" ]]; then
    bash "$root/rag/setup_pdf_support.sh" >>"$LOG" 2>&1 || fail "PDF parser setup failed; see $LOG"
    bash "$root/rag/setup_xlsx_support.sh" >>"$LOG" 2>&1 || fail "XLSX parser setup failed; see $LOG"
  elif [[ ! -d "$DEPS/pypdf" || ! -d "$DEPS/openpyxl" ]]; then
    fail "Parser deps missing under $DEPS and no checkout with rag/setup_*.sh was found."
  fi
  PYTHONPATH="$DEPS" "$RUNTIME/bin/python" -c \
    'import importlib.metadata as m; assert m.version("pypdf")=="6.20.0"; assert m.version("openpyxl")=="3.1.5"' \
    >>"$LOG" 2>&1 || fail "Pinned parser import check failed."
}

[[ -d "$VOL" && -f "$MODEL/config.json" ]] || fail "Global Volume or Gemma config missing; refusing to download model."
[[ -f "$SETUP/SHA256SUMS" && -f "$SETUP/vllm-clean-env.tar.zst" ]] || fail "Saved runtime archive/checksum manifest missing."

log "Checking saved runtime checksums."
(cd "$SETUP" && sha256sum -c SHA256SUMS) >>"$LOG" 2>&1 || fail "Runtime checksum validation failed."
if [[ "$MODE" == "--check" ]]; then
  printf '\n=== READ-ONLY PLATFORM CHECK ===\n'
  printf 'Model config: '; test -f "$MODEL/config.json" && echo OK
  printf 'Model weight shards: '; find "$MODEL" -maxdepth 1 -type f -name '*.safetensors' | wc -l
  printf 'Runtime archive: '; ls -lh "$SETUP/vllm-clean-env.tar.zst" | awk '{print $5}'
  printf 'Runtime environment: '; [[ -x "$RUNTIME/bin/vllm" ]] && echo PRESENT || echo NOT_IN_TMP
  printf 'vLLM API: '; healthy http://127.0.0.1:8000/v1/models && echo HEALTHY || echo NOT_HEALTHY
  printf 'Gateway: '; healthy http://127.0.0.1:8010/health && echo HEALTHY || echo NOT_HEALTHY
  printf 'Console: '; healthy http://127.0.0.1:8080/api/status && echo HEALTHY || echo NOT_HEALTHY
  printf 'Parser deps: '; [[ -d "$DEPS/pypdf" && -d "$DEPS/openpyxl" ]] && echo PRESENT || echo NOT_IN_TMP
  printf 'Gateway key permissions: '; stat -c '%a %n' "$KEY" 2>/dev/null || echo MISSING
  printf 'Test gateway :8012: '; healthy http://127.0.0.1:8012/health && echo HEALTHY || echo NOT_HEALTHY
  printf 'Test console :8082: '; healthy http://127.0.0.1:8082/api/status && echo HEALTHY || echo NOT_HEALTHY
  printf 'Diagnostics: %s\n' "$DIAG"
  printf '\nNote: --check is read-only. --start reuses healthy main services and never recreates the Pod.\n'
  exit 0
fi

# Restore the pinned environment only if it is absent. Never run the installer here.
if ! healthy http://127.0.0.1:8000/v1/models; then
  if [[ ! -x "$RUNTIME/bin/vllm" ]]; then
    command -v zstd >/dev/null || fail "zstd is required to restore the saved runtime archive."
    [[ ! -e "$RUNTIME" ]] || fail "$RUNTIME exists but vLLM is missing; refusing to overwrite a possibly damaged environment."
    FREE_KB=$(df -Pk /tmp | awk 'END {print $4}')
    [[ "$FREE_KB" =~ ^[0-9]+$ && "$FREE_KB" -ge 12582912 ]] || fail "Need at least 12 GiB free on /tmp to restore vLLM."
    log "Restoring the checksum-verified vLLM environment from Global Volume; this is a one-time cold-start step."
    tar -I 'zstd -d' -xf "$SETUP/vllm-clean-env.tar.zst" -C /tmp >>"$LOG" 2>&1 || fail "Runtime archive extraction failed."
  fi
  "$RUNTIME/bin/vllm" --version >>"$LOG" 2>&1 || fail "Restored vLLM executable failed its version check."
  [[ -f "$MODEL/model-00001-of-00002.safetensors" && -f "$MODEL/model-00002-of-00002.safetensors" ]] || fail "Expected Gemma weight shards missing."
  log "Starting vLLM on loopback port 8000."
  nohup "$RUNTIME/bin/python" "$RUNTIME/bin/vllm" serve "$MODEL" --host 127.0.0.1 --port 8000 --gpu-memory-utilization 0.90 --max-model-len 8192 >>"$DIAG/vllm.log" 2>&1 </dev/null &
  echo "$!" > "$DIAG/vllm.pid"
  ready=0
  for _ in $(seq 1 240); do
    if healthy http://127.0.0.1:8000/v1/models; then ready=1; break; fi
    sleep 2
  done
  [[ "$ready" == 1 ]] || fail "vLLM did not become API-ready. Inspect $DIAG/vllm.log; process left running for diagnosis."
else
  log "Reusing healthy vLLM service; no restart."
fi

if ! healthy http://127.0.0.1:8010/health; then
  # Pick one complete, timestamp-matched deployed source backup.
  stamp=""
  for candidate in $(find "$BACKUPS" -maxdepth 1 -type f -name '*-platform_gateway.py' -printf '%f\n' 2>/dev/null | sed 's/-platform_gateway\.py$//' | sort -r); do
    if [[ -f "$BACKUPS/$candidate-platform_gateway.py" && -f "$BACKUPS/$candidate-rag_engine.py" && -f "$BACKUPS/$candidate-document_loaders.py" && -f "$BACKUPS/$candidate-document_library.py" ]]; then stamp="$candidate"; break; fi
  done
  [[ -n "$stamp" ]] || fail "No complete timestamp-matched gateway source backup found under $BACKUPS."
  mkdir -p "$GW"
  for name in platform_gateway.py rag_engine.py document_loaders.py document_library.py; do
    cp "$BACKUPS/$stamp-$name" "$GW/$name"
  done
  "$RUNTIME/bin/python" -m py_compile "$GW/platform_gateway.py" "$GW/rag_engine.py" "$GW/document_loaders.py" "$GW/document_library.py" || fail "Gateway source syntax check failed."
  ensure_parser_deps
  if [[ ! -s "$KEY" ]]; then
    log "No temporary gateway key found; creating a new random key (never logged or persisted)."
    "$RUNTIME/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))' > "$KEY"
    chmod 600 "$KEY"
  fi
  [[ "$(stat -c '%a' "$KEY")" == "600" ]] || chmod 600 "$KEY"
  [[ -d "$VOL/rag-demo-docs" && -d "$VOL/rag-managed-docs" ]] || fail "One or more RAG document directories are missing."
  log "Starting gateway from persistent source backup $stamp on loopback port 8010."
  nohup env PYTHONPATH="$DEPS" PLATFORM_HOST=127.0.0.1 PLATFORM_PORT=8010 PLATFORM_API_KEY="$(cat "$KEY")" VLLM_UPSTREAM_URL=http://127.0.0.1:8000/v1 RAG_DOCS_DIR="$VOL/rag-demo-docs" RAG_MANAGED_DOCS_DIR="$VOL/rag-managed-docs" RAG_MIN_SCORE=2.30 RAG_MANAGED_MIN_SCORE=0.0 "$RUNTIME/bin/python" "$GW/platform_gateway.py" >>"$DIAG/gateway.log" 2>&1 </dev/null &
  echo "$!" > "$DIAG/gateway.pid"
  ready=0
  for _ in $(seq 1 30); do
    if healthy http://127.0.0.1:8010/health; then ready=1; break; fi
    sleep 1
  done
  [[ "$ready" == 1 ]] || fail "Gateway failed health check. Inspect $DIAG/gateway.log."
else
  log "Reusing healthy gateway; no restart."
fi

if ! healthy http://127.0.0.1:8080/api/status; then
  if [[ ! -f "$REPO/web/server.py" || ! -d "$REPO/web/static" ]]; then
    rm -rf "$REPO"
    git clone --quiet --depth 1 --branch cursor/local-web-console https://github.com/henokmeron/AI-PLAYBOOK.md.git "$REPO" >>"$LOG" 2>&1 || fail "Could not retrieve versioned web console source."
  fi
  [[ -s "$KEY" ]] || fail "Gateway key missing at $KEY; cannot start console."
  log "Starting loopback-only web console on port 8080."
  nohup env WEB_HOST=127.0.0.1 WEB_PORT=8080 PLATFORM_GATEWAY_URL=http://127.0.0.1:8010 PLATFORM_API_KEY_FILE="$KEY" PLATFORM_MODEL_ID="$MODEL" "$RUNTIME/bin/python" "$REPO/web/server.py" >>"$DIAG/console.log" 2>&1 </dev/null &
  echo "$!" > "$DIAG/console.pid"
  ready=0
  for _ in $(seq 1 30); do
    if healthy http://127.0.0.1:8080/api/status; then ready=1; break; fi
    sleep 1
  done
  [[ "$ready" == 1 ]] || fail "Console failed health check. Inspect $DIAG/console.log."
else
  log "Reusing healthy console; no restart."
fi

log "Main stack healthy (vLLM/gateway/console). This verifies API health, not chat/RAG accuracy."
printf 'Console access: SSH tunnel to 127.0.0.1:8080 (Windows example uses local 18080); do not publish 8010/8080.\n'
printf 'Isolated Document Q&A test stack (optional): bash ops/start-test-console-8082.sh\n'
printf 'Persistent diagnostics: %s\n' "$DIAG"
