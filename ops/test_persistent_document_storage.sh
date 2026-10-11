#!/usr/bin/env bash
# Verify live document upload and RAG retrieval on the mounted Global Volume.
# Leaves a small fictional canary document for a future cross-Pod persistence check.
set -Eeuo pipefail

PYTHON=/tmp/vllm-clean-env/bin/python
KEY_FILE=/tmp/platform-gateway.key
BASE_URL=http://127.0.0.1:8010
GLOBAL=/workspace
MANAGED_ROOT="$GLOBAL/rag-managed-docs"
MODEL_MARKER="$GLOBAL/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it/config.json"

if [[ ! -x "$PYTHON" ]]; then echo "ERROR: working Python env missing; no installation attempted." >&2; exit 2; fi
if [[ ! -r "$KEY_FILE" ]]; then echo "ERROR: current gateway API key missing; no changes made." >&2; exit 3; fi
if [[ "$(findmnt -T "$GLOBAL" -n -o TARGET 2>/dev/null | head -n 1 || true)" != "$GLOBAL" || ! -f "$MODEL_MARKER" ]]; then
  echo "ERROR: mounted Global Volume could not be verified; refusing to write files." >&2
  exit 4
fi
if ! curl -fsS "$BASE_URL/health" -o /tmp/persistent-document-health.json; then
  echo "ERROR: live gateway health check failed; no document uploaded." >&2
  exit 5
fi
if ! grep -q '"status":"ok"' /tmp/persistent-document-health.json; then
  echo "ERROR: live gateway health response is not OK; no document uploaded." >&2
  cat /tmp/persistent-document-health.json >&2
  exit 6
fi

KEY="$(cat "$KEY_FILE")"
COLLECTION="global-canary-$(date +%s)"
FILENAME="global-volume-canary.md"
CANARY_CODE="GLOBALVOL-58317"
CONTENT="Persistent storage verification code: $CANARY_CODE. This is a fictional canary used to verify the mounted Global Volume document API."

echo "=== GLOBAL VOLUME AND GATEWAY ==="
echo "Mount verified: $GLOBAL"
cat /tmp/persistent-document-health.json
echo

echo "=== UPLOAD CANARY THROUGH LIVE API ==="
payload="$("$PYTHON" - "$COLLECTION" "$FILENAME" "$CONTENT" <<'PY'
import base64, json, sys
collection, filename, content = sys.argv[1:4]
print(json.dumps({
    "collection": collection,
    "filename": filename,
    "content_base64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
}))
PY
)"
upload_code="$(curl -sS -o /tmp/persistent-document-upload.json -w '%{http_code}' -X POST "$BASE_URL/v1/rag/documents" \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d "$payload")"
cat /tmp/persistent-document-upload.json
echo
if [[ "$upload_code" != "201" ]]; then
  echo "ERROR: upload failed with HTTP $upload_code." >&2
  exit 7
fi

EXPECTED_FILE="$MANAGED_ROOT/$COLLECTION/$FILENAME"
if [[ ! -f "$EXPECTED_FILE" ]]; then
  echo "ERROR: API reported success but file is absent at expected Global Volume path: $EXPECTED_FILE" >&2
  exit 8
fi
echo "PASS: file physically exists on Global Volume: $EXPECTED_FILE"

echo "=== LIST VIA LIVE API ==="
list_json="$(curl -fsS -G "$BASE_URL/v1/rag/documents" \
  -H "Authorization: Bearer $KEY" --data-urlencode "collection=$COLLECTION")"
printf '%s' "$list_json" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print(d); assert any(x.get("filename")=="global-volume-canary.md" for x in d.get("documents",[]))'
echo "PASS: live API lists the canary."

echo "=== ASK ABOUT THE CANARY VIA LIVE API ==="
ask_payload="$("$PYTHON" - "$COLLECTION" <<'PY'
import json, sys
print(json.dumps({
    "collection": sys.argv[1],
    "question": "What is the persistent storage verification code?",
    "top_k": 3,
}))
PY
)"
ask_response="$(curl -fsS -X POST "$BASE_URL/v1/rag/ask" \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d "$ask_payload")"
printf '%s' "$ask_response" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); answer=d.get("answer",""); print("Status:",d.get("status")); print("Answer:",answer); print("Sources:",d.get("sources")); assert d.get("status")=="answered"; assert "globalvol-58317" in answer.casefold(); assert any(x.get("file")=="global-volume-canary.md" for x in d.get("sources",[]))'
echo "PASS: live RAG response cites the Global Volume canary."

echo
echo "SUCCESS: document upload/list/retrieval verified at the mounted Global Volume path."
echo "Canary collection: $COLLECTION"
echo "Canary file:       $EXPECTED_FILE"
echo "The small fictional canary is intentionally retained for a future Pod re-attach persistence check."
