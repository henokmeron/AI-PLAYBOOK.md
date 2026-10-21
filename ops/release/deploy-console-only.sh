#!/usr/bin/env bash
# Replace only the loopback console on port 8080.
# Does not start or stop Qwen (:8002) or the gateway (:8010).
# Does not delete model weights, runtime archives, snapshots, or managed documents.
#
# Default is a dry run. To replace the console after the Python check passes:
#   CONSOLE_RESTART_APPROVED=yes bash ops/release/deploy-console-only.sh
#
# If ports 8002 and 8010 are down, this script stops and tells you to use
# START.sh only with separate approval. It will not call START.sh itself.
set -Eeuo pipefail

REPO_ROOT="${REPO_ROOT:-/tmp/AI-PLAYBOOK}"
BRANCH="${PLATFORM_BRANCH:-main}"
DIAG="${DIAG:-/tmp/platform-diagnostics}"
KEY="${PLATFORM_API_KEY_FILE:-/tmp/platform-gateway.key}"
APPROVED="${CONSOLE_RESTART_APPROVED:-no}"
if [[ "$APPROVED" != "yes" ]]; then
  APPROVED=no
fi

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] CONSOLE: $*"; }
fail() { echo "ERROR: $*" >&2; exit 2; }

http_code() {
  local code
  code="$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://127.0.0.1:$1/health" || true)"
  if [[ ! "$code" =~ ^[0-9]{3}$ ]]; then
    code=000
  fi
  printf '%s' "$code"
}

pids_for() {
  ss -lptn "sport = :$1" 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | paste -sd, -
}

if ! findmnt -n -o FSTYPE /workspace 2>/dev/null | grep -qx fuse.geesefs; then
  fail "/workspace is not the Global Volume. Nothing was stopped."
fi

H8002="$(http_code 8002)"
H8010="$(http_code 8010)"
P8002="$(pids_for 8002)"
P8010="$(pids_for 8010)"
P8080="$(pids_for 8080)"

# Named-operator auth is checked before any console process is stopped.
# Provision the first admin BEFORE approving a restart:
#   OPERATOR_AUTH_DIR=/tmp/console-operators \
#     python3 "$REPO_ROOT/scripts/provision_console_operator.py" create-admin --username <name>
OPERATOR_AUTH_DIR="${OPERATOR_AUTH_DIR:-/tmp/console-operators}"
OPS_READY="$(
  python3 "$REPO_ROOT/ops/release/console_deploy.py" \
    --operators-file "$OPERATOR_AUTH_DIR/operators.json" || true
)"
case "$OPS_READY" in
  yes) ;;
  *) OPS_READY=no ;;
esac

DECISION="$(
  python3 "$REPO_ROOT/ops/release/console_deploy.py" \
    --approved "$APPROVED" \
    --operators-ready "$OPS_READY" \
    --health-8002 "$H8002" \
    --health-8010 "$H8010" \
    --pid-8002 "$P8002" \
    --pid-8010 "$P8010" \
    --pid-8080 "$P8080"
)" || fail "console reload refused. Qwen and the gateway were not signalled."

if [[ "$DECISION" != "restart-console" ]]; then
  log "dry-run only. Qwen :8002 HTTP $H8002 pid ${P8002:-none}. Gateway :8010 HTTP $H8010 pid ${P8010:-none}. Console pid ${P8080:-none}."
  log "Set CONSOLE_RESTART_APPROVED=yes to replace the console after both health checks are 200."
  exit 0
fi

if [[ "$P8080" == *","* || -z "$P8080" ]]; then
  fail "refusing to choose which process on port 8080 to stop."
fi

mkdir -p "$DIAG"
if [[ -d "$REPO_ROOT/.git" ]]; then
  git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" fetch --quiet origin "$BRANCH"
  if [[ -z "$(git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" status --porcelain --untracked-files=no)" ]]; then
    git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" checkout --quiet "$BRANCH"
    git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" merge --ff-only --quiet "origin/$BRANCH"
  else
    log "WARN: tracked edits in $REPO_ROOT were left in place"
  fi
fi

kill -0 "$P8002" && kill -0 "$P8010" || fail "Qwen or the gateway disappeared before the console restart. Nothing further was stopped."
kill "$P8080"
sleep 1
if kill -0 "$P8080" 2>/dev/null; then
  fail "the previous console process is still running. Qwen and the gateway were not signalled."
fi

nohup env \
  WEB_HOST=127.0.0.1 \
  WEB_PORT=8080 \
  PLATFORM_GATEWAY_URL=http://127.0.0.1:8010 \
  PLATFORM_API_KEY_FILE="$KEY" \
  PLATFORM_MODEL_ID=qwen3.5-27b \
  OPERATOR_AUTH_DIR="$OPERATOR_AUTH_DIR" \
  WEB_COOKIE_SECURE="${WEB_COOKIE_SECURE:-false}" \
  MICROSOFT_CLIENT_ID="${MICROSOFT_CLIENT_ID:-}" \
  MICROSOFT_TENANT="${MICROSOFT_TENANT:-common}" \
  MICROSOFT_REDIRECT_URI="${MICROSOFT_REDIRECT_URI:-http://127.0.0.1:18080/api/microsoft/callback}" \
  MICROSOFT_TOKEN_FILE="${MICROSOFT_TOKEN_FILE:-/tmp/microsoft-365-token.json}" \
  ENDPOINT_STATE_FILE="${ENDPOINT_STATE_FILE:-/tmp/endpoint-devices.json}" \
  RAG_DOCS_DIR="${RAG_DOCS_DIR:-/workspace/rag-demo-docs}" \
  RAG_MANAGED_DOCS_DIR="${RAG_MANAGED_DOCS_DIR:-/workspace/rag-managed-docs}" \
  /usr/bin/python3 "$REPO_ROOT/web/server.py" \
  >"$DIAG/console.log" 2>&1 </dev/null 9>&- &
echo $! >"$DIAG/console.pid"

kill -0 "$P8002" && kill -0 "$P8010" || fail "Qwen or the gateway is no longer running after the console start."
H8002_AFTER="$(http_code 8002)"
H8010_AFTER="$(http_code 8010)"
H8080_AFTER="$(http_code 8080)"
OUTCOME="$(
  python3 "$REPO_ROOT/ops/release/console_deploy.py" \
    --assess \
    --health-8002 "$H8002_AFTER" \
    --health-8010 "$H8010_AFTER" \
    --health-8080 "$H8080_AFTER"
)" || fail "replacement health check failed. Qwen and the gateway were not signalled."
if [[ "$OUTCOME" != "keep" ]]; then
  fail "replacement is not healthy. Do not treat the new console as ready. Qwen and the gateway were not signalled."
fi
log "console process replaced. Qwen pid $P8002 and gateway pid $P8010 were left running."
