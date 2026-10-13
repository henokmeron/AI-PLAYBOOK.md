#!/usr/bin/env bash
# Durable one-command start for the RunPod-first release (Qwen3.5-27B only; Gemma never auto-starts).
# Installed at /workspace/ai-platform-release/START.sh; canonical copy is ops/release/START.sh in Git.
# Never extracts a runtime onto /workspace and never discards local source edits.
#
# Usage: bash /workspace/ai-platform-release/START.sh [--start|--preflight|--check]
set -Eeuo pipefail

export REPO_ROOT="${REPO_ROOT:-/tmp/AI-PLAYBOOK}"
BRANCH="${PLATFORM_BRANCH:-feature/qwen3.5-27b-integration}"
REMOTE="${PLATFORM_REMOTE:-https://github.com/henokmeron/AI-PLAYBOOK.md.git}"
SNAP_DIR=/workspace/ai-platform-backups/source-snapshots
MANIFEST_DIR=/workspace/ai-platform-backups/manifests
MODE="${1:---start}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] START: $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }
git_repo() { git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" "$@"; }

findmnt -n /workspace >/dev/null 2>&1 || fail "/workspace is not mounted. Attach the Global Volume to this Pod first."

restore_from_snapshot() {
  # Newest runpod-first source snapshot whose SHA-256 matches its manifest.
  local snap name sum expected actual
  while read -r snap; do
    [[ -n "$snap" ]] || continue
    name="$(basename "$snap" .tar.gz)"
    sum="$MANIFEST_DIR/$name.sha256"
    [[ -f "$sum" ]] || { log "WARN: no checksum manifest for $snap; skipping"; continue; }
    expected="$(awk '{print $1; exit}' "$sum")"
    actual="$(sha256sum "$snap" | awk '{print $1}')"
    if [[ "$actual" == "$expected" ]]; then
      mkdir -p "$REPO_ROOT"
      tar -xzf "$snap" -C "$REPO_ROOT"
      log "Restored source from verified snapshot $snap (no git history)"
      return 0
    fi
    log "WARN: checksum mismatch for $snap; skipping"
  done < <(ls -1t "$SNAP_DIR"/AI-PLAYBOOK.md-runpod-first-*.tar.gz 2>/dev/null || true)
  return 1
}

if [[ -d "$REPO_ROOT/.git" ]]; then
  # Older launchers ran `cp -a <fuse-dir>/. $REPO_ROOT/`, which handed the checkout to the FUSE
  # owner (nobody) and made git refuse it ("dubious ownership"). Repair before using git.
  if [[ "$(stat -c %u "$REPO_ROOT")" != "$(id -u)" ]]; then
    log "Repairing ownership of $REPO_ROOT"
    chown -R "$(id -u):$(id -g)" "$REPO_ROOT"
  fi
  if git_repo fetch --quiet origin "$BRANCH"; then
    if [[ -n "$(git_repo status --porcelain --untracked-files=no)" ]]; then
      log "WARN: $REPO_ROOT has local tracked edits; leaving them in place (not updating)"
    else
      git_repo checkout --quiet "$BRANCH"
      git_repo merge --ff-only --quiet "origin/$BRANCH" \
        || log "WARN: cannot fast-forward $REPO_ROOT to origin/$BRANCH; using current checkout"
    fi
  else
    log "WARN: git fetch failed (offline?); using existing checkout"
  fi
elif [[ -f "$REPO_ROOT/api/local_gateway.py" ]]; then
  log "Using existing source tree at $REPO_ROOT (no .git; restored from snapshot earlier)"
elif [[ -e "$REPO_ROOT" && -n "$(ls -A "$REPO_ROOT" 2>/dev/null)" ]]; then
  fail "$REPO_ROOT exists but is not a platform checkout. Move it aside or set REPO_ROOT, then re-run."
else
  if ! git clone --quiet --branch "$BRANCH" --single-branch "$REMOTE" "$REPO_ROOT"; then
    log "WARN: git clone failed; falling back to the newest verified source snapshot on the Global Volume"
    restore_from_snapshot || fail "No GitHub access and no verified source snapshot under $SNAP_DIR."
  fi
fi

log "Source at $REPO_ROOT: $(git_repo rev-parse --short HEAD 2>/dev/null || echo 'snapshot (no git)')"
exec bash "$REPO_ROOT/ops/start-first-release.sh" "$MODE"
