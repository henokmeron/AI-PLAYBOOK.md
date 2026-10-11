#!/usr/bin/env bash
# Download, run and smoke-test the loopback-only gateway without touching vLLM.
set -euo pipefail
API_BASE=https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/api
PYTHON=/tmp/vllm-clean-env/bin/python
GATEWAY_FILE=/tmp/platform_gateway.py
LOG_FILE=/tmp/platform-gateway.log
PID_FILE=/tmp/platform-gateway.pid
KEY_FILE=/tmp/platform-gateway.key
URL=http://127.0.0.1:8010

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: expected working Python at $PYTHON; do not reinstall automatically." >&2
  exit 2
fi
if curl -fsS "$URL/health" >/dev/null 2>&1; then
  echo "ERROR: a gateway already responds at $URL. Reuse/check it rather than starting a second copy." >&2
  exit 3
fi

curl -fsSL "$API_BASE/local_gateway.py" -o "$GATEWAY_FILE"
umask 077
"$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(40))' > "$KEY_FILE"
export PLATFORM_API_KEY
PLATFORM_API_KEY="$(cat "$KEY_FILE")"
nohup "$PYTHON" "$GATEWAY_FILE" > "$LOG_FILE" 2>&1 </dev/null &
echo "$!" > "$PID_FILE"

ready=0
for _ in $(seq 1 30); do
  if curl -fsS "$URL/health" >/tmp/platform-gateway-health.json 2>/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  echo "ERROR: gateway health check failed. Recent logs:" >&2
  tail -30 "$LOG_FILE" >&2 || true
  exit 4
fi

echo "=== HEALTH ==="
cat /tmp/platform-gateway-health.json
echo

echo "=== AUTH REQUIRED ==="
unauth_code="$(curl -sS -o /tmp/platform-gateway-unauth.json -w '%{http_code}' \
  -X POST "$URL/v1/chat/completions" -H 'Content-Type: application/json' -d '{"messages":[]}' )"
cat /tmp/platform-gateway-unauth.json
echo
if [[ "$unauth_code" != "401" ]]; then
  echo "FAIL: unauthenticated request returned $unauth_code, expected 401" >&2
  exit 5
fi
echo "PASS: unauthenticated request rejected"

echo "=== AUTHENTICATED REAL GENERATION ==="
response="$(curl -fsS -X POST "$URL/v1/chat/completions" \
  -H "Authorization: Bearer $PLATFORM_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it","messages":[{"role":"user","content":"Reply with exactly: gateway works"}],"temperature":0,"max_tokens":12}')"
printf '%s\n' "$response"
if ! printf '%s' "$response" | grep -qi 'gateway works'; then
  echo "FAIL: expected generated phrase not found. Gateway logs:" >&2
  tail -30 "$LOG_FILE" >&2 || true
  exit 6
fi
echo "PASS: authenticated request reached Gemma and generated the expected phrase"
echo
echo "All gateway smoke tests passed. The loopback-only gateway remains running."
echo "Log: $LOG_FILE"
echo "PID: $PID_FILE"
echo "Temporary API key: $KEY_FILE (not printed, not backed up)"
