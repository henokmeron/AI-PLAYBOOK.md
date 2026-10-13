#!/usr/bin/env bash
# Live smoke against isolated Qwen on :8002. Does not call Gemma :8000.
# Exit 0 only when /v1/models and one chat completion succeed.
set -Eeuo pipefail
BASE="${QWEN_BASE_URL:-http://127.0.0.1:8002/v1}"
MODEL="${QWEN_MODEL_ID:-/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654}"

echo "Checking $BASE/models"
curl -fsS --max-time 10 "$BASE/models" | head -c 500
echo
echo "Chat completion smoke"
resp=$(curl -fsS --max-time 180 "$BASE/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: qwen works\"}],\"max_tokens\":16,\"temperature\":0}")
echo "$resp" | head -c 1000
echo
echo "$resp" | grep -qi 'qwen works' || {
  echo "ERROR: completion did not contain expected phrase" >&2
  exit 1
}
echo "PASS: Qwen smoke"
