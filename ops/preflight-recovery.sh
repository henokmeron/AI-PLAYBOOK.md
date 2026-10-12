#!/usr/bin/env bash
# Read-only preflight for a future cold-start drill. Does not stop/restart services.
set -Eeuo pipefail
umask 077
VOL=/workspace
SETUP="$VOL/runtime-setup"
BACKUPS="$VOL/ai-platform-backups/deployed-runtime"
WHEELHOUSE="$SETUP/rag-wheelhouse"
failures=0
pass(){ printf '[PASS] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; }
fail(){ printf '[FAIL] %s\n' "$*"; failures=$((failures+1)); }

printf '=== Recovery preflight (read-only; no service restarts) ===\n'
if [[ -f "$SETUP/SHA256SUMS" && -f "$SETUP/vllm-clean-env.tar.zst" ]]; then
  if (cd "$SETUP" && sha256sum -c SHA256SUMS); then pass 'saved runtime checksums'; else fail 'saved runtime checksum mismatch'; fi
else fail 'runtime archive or checksum manifest missing'; fi

if [[ -f "$SETUP/vllm-clean-env.tar.zst" ]] && command -v zstd >/dev/null 2>&1; then
  if zstd -t "$SETUP/vllm-clean-env.tar.zst" >/dev/null; then pass 'runtime archive integrity'; else fail 'runtime archive cannot be decompressed'; fi
else warn 'zstd unavailable; archive decompression test skipped'; fi

for f in platform_gateway.py rag_engine.py document_loaders.py document_library.py; do
  count=$(find "$BACKUPS" -maxdepth 1 -type f -name "*-$f" 2>/dev/null | wc -l)
  if [[ "$count" -gt 0 ]]; then pass "$f backup copies exist ($count)"; else fail "$f backup missing"; fi
done

if [[ -d "$WHEELHOUSE" ]]; then
  pass "parser wheelhouse directory exists"
  for f in pypdf-6.20.0-py3-none-any.whl openpyxl-3.1.5-py2.py3-none-any.whl et_xmlfile-2.0.0-py3-none-any.whl defusedxml-0.7.1-py2.py3-none-any.whl; do
    if [[ -s "$WHEELHOUSE/$f" ]]; then pass "wheel present: $f"; else fail "wheel missing: $f"; fi
  done
  for manifest in SHA256SUMS XLSX-SHA256SUMS; do
    if [[ -s "$WHEELHOUSE/$manifest" ]]; then
      if (cd "$WHEELHOUSE" && sha256sum -c "$manifest"); then pass "wheelhouse manifest: $manifest"; else fail "wheelhouse manifest mismatch: $manifest"; fi
    else warn "wheelhouse manifest missing: $manifest"; fi
  done
else fail 'parser wheelhouse missing'; fi

if [[ -f /tmp/AI-PLAYBOOK/ops/start-platform.sh ]]; then
  if bash -n /tmp/AI-PLAYBOOK/ops/start-platform.sh; then pass 'startup script shell syntax'; else fail 'startup script shell syntax invalid'; fi
else warn 'checkout startup script not found at /tmp/AI-PLAYBOOK; syntax check skipped'; fi

for spec in '127.0.0.1:8000/v1/models' '127.0.0.1:8010/health' '127.0.0.1:8080/api/status'; do
  if curl -fsS --max-time 3 "http://$spec" >/dev/null; then pass "service reachable: $spec"; else warn "service not currently reachable: $spec"; fi
done

printf '\nFailures: %s\n' "$failures"
if [[ "$failures" -gt 0 ]]; then
  printf 'Do not run a cold-start recovery drill until the FAIL items are resolved. Current live services were not modified.\n'
  exit 1
fi
printf 'Preflight passed its required artifact checks. This is not yet a cold-start recovery test.\n'
