#!/usr/bin/env bash
# Read-only preflight for restart and future cold-start drills.
# Does not stop, restart, or modify running services.
set -Eeuo pipefail
umask 077

VOL=/workspace
SETUP="$VOL/runtime-setup"
BACKUPS="$VOL/ai-platform-backups/deployed-runtime"
WHEELHOUSE="$SETUP/rag-wheelhouse"
MODEL="$VOL/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it"
DOC_BACKUPS="$SETUP/web-console-backups"
failures=0

pass(){ printf '[PASS] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; }
fail(){ printf '[FAIL] %s\n' "$*"; failures=$((failures+1)); }

printf '=== Recovery preflight (read-only; no service restarts) ===\n'
printf 'Mode note: this script only validates artifacts and reachability.\n'
printf 'It is NOT a Pod recreation drill and does NOT start or stop services.\n\n'

if [[ -d "$VOL" && -f "$MODEL/config.json" ]]; then
  pass "Global Volume mounted and Gemma config present"
  shard_count=$(find "$MODEL" -maxdepth 1 -type f -name '*.safetensors' 2>/dev/null | wc -l)
  if [[ "$shard_count" -ge 2 ]]; then
    pass "model weight shards present ($shard_count)"
  else
    fail "expected at least two *.safetensors shards under model directory"
  fi
else
  fail "Global Volume or Gemma config missing at $MODEL"
fi

if [[ -f "$SETUP/SHA256SUMS" && -f "$SETUP/vllm-clean-env.tar.zst" ]]; then
  if (cd "$SETUP" && sha256sum -c SHA256SUMS); then
    pass "saved runtime checksums"
  else
    fail "saved runtime checksum mismatch"
  fi
else
  fail "runtime archive or checksum manifest missing"
fi

if [[ -f "$SETUP/vllm-clean-env.tar.zst" ]] && command -v zstd >/dev/null 2>&1; then
  if zstd -t "$SETUP/vllm-clean-env.tar.zst" >/dev/null; then
    pass "runtime archive integrity"
  else
    fail "runtime archive cannot be decompressed"
  fi
else
  warn "zstd unavailable; archive decompression test skipped"
fi

for f in platform_gateway.py rag_engine.py document_loaders.py document_library.py; do
  count=$(find "$BACKUPS" -maxdepth 1 -type f -name "*-$f" 2>/dev/null | wc -l)
  if [[ "$count" -gt 0 ]]; then
    pass "$f backup copies exist ($count)"
  else
    fail "$f backup missing"
  fi
done

if [[ -d "$WHEELHOUSE" ]]; then
  pass "parser wheelhouse directory exists"
  for f in pypdf-6.20.0-py3-none-any.whl openpyxl-3.1.5-py2.py3-none-any.whl et_xmlfile-2.0.0-py3-none-any.whl defusedxml-0.7.1-py2.py3-none-any.whl; do
    if [[ -s "$WHEELHOUSE/$f" ]]; then
      pass "wheel present: $f"
    else
      fail "wheel missing: $f"
    fi
  done
  for manifest in SHA256SUMS XLSX-SHA256SUMS; do
    if [[ -s "$WHEELHOUSE/$manifest" ]]; then
      if (cd "$WHEELHOUSE" && sha256sum -c "$manifest"); then
        pass "wheelhouse manifest: $manifest"
      else
        fail "wheelhouse manifest mismatch: $manifest"
      fi
    else
      warn "wheelhouse manifest missing: $manifest"
    fi
  done
else
  fail "parser wheelhouse missing"
fi

if [[ -x /tmp/vllm-clean-env/bin/vllm && -x /tmp/vllm-clean-env/bin/python ]]; then
  pass "temporary vLLM environment present under /tmp/vllm-clean-env"
else
  warn "temporary vLLM environment missing under /tmp (expected after Pod recreation until restore)"
fi

if [[ -d /tmp/rag-deps/pypdf && -d /tmp/rag-deps/openpyxl ]]; then
  pass "isolated parser deps present under /tmp/rag-deps"
else
  warn "isolated parser deps missing under /tmp/rag-deps (restore with rag/setup_*.sh)"
fi

if [[ -f /tmp/platform-gateway.key ]]; then
  perms=$(stat -c '%a' /tmp/platform-gateway.key 2>/dev/null || echo unknown)
  if [[ "$perms" == "600" ]]; then
    pass "gateway key file present with mode 600"
  else
    warn "gateway key file present with mode $perms (prefer 600)"
  fi
else
  warn "gateway key file missing under /tmp (created on first gateway start; never commit)"
fi

latest_doc_backup=""
if [[ -d "$DOC_BACKUPS" ]]; then
  latest_doc_backup=$(ls -1dt "$DOC_BACKUPS"/document-qa-conversation-* 2>/dev/null | head -1 || true)
fi
if [[ -n "$latest_doc_backup" && -s "$latest_doc_backup/source.tgz" && -s "$latest_doc_backup/MANIFEST.txt" ]]; then
  pass "Document Q&A recovery snapshot present: $(basename "$latest_doc_backup")"
else
  warn "no Document Q&A recovery snapshot under $DOC_BACKUPS"
fi

startup_script=""
for candidate in \
  /tmp/AI-PLAYBOOK-upload-test/ops/start-platform.sh \
  /tmp/AI-PLAYBOOK/ops/start-platform.sh \
  "$(dirname "$0")/start-platform.sh"
do
  if [[ -f "$candidate" ]]; then
    startup_script="$candidate"
    break
  fi
done
if [[ -n "$startup_script" ]]; then
  if bash -n "$startup_script"; then
    pass "startup script shell syntax: $startup_script"
  else
    fail "startup script shell syntax invalid: $startup_script"
  fi
else
  warn "start-platform.sh not found in common checkouts; syntax check skipped"
fi

printf '\n=== Live service reachability (informational) ===\n'
for spec in \
  '127.0.0.1:8000/v1/models|vLLM' \
  '127.0.0.1:8010/health|main gateway' \
  '127.0.0.1:8080/api/status|main console' \
  '127.0.0.1:8012/health|test gateway' \
  '127.0.0.1:8082/api/status|test console'
do
  url="${spec%%|*}"
  label="${spec##*|}"
  if curl -fsS --max-time 3 "http://$url" >/dev/null; then
    pass "service reachable: $label ($url)"
  else
    warn "service not currently reachable: $label ($url)"
  fi
done

printf '\n=== Restart vs Pod recreation ===\n'
printf 'Service restart (same Pod): bash ops/start-platform.sh --check && bash ops/start-platform.sh --start\n'
printf '  Reuses healthy listeners; restores /tmp artifacts only when missing; does not recreate the Pod.\n'
printf 'Pod recreation: attach the same Global Volume at /workspace, then run preflight, then start-platform --start.\n'
printf '  Requires restoring /tmp/vllm-clean-env from the archive and recreating the gateway key if absent.\n'
printf 'Isolated Document Q&A test stack: bash ops/start-test-console-8082.sh (ports 8012/8082 only).\n'
printf 'Windows browser tunnel for test console: ssh -N -L 18082:127.0.0.1:8082 ... (see recovery-runbook.md).\n'

printf '\nFailures: %s\n' "$failures"
if [[ "$failures" -gt 0 ]]; then
  printf 'Do not run a cold-start recovery drill until the FAIL items are resolved. Current live services were not modified.\n'
  exit 1
fi
printf 'Preflight passed its required artifact checks. This is not yet a cold-start recovery test.\n'
