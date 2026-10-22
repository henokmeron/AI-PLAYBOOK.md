#!/bin/bash
# Fast-forward one clean checkout. Does not signal Qwen, the gateway, or the console.
set -euo pipefail

CHECKOUT="${SOURCE_CHECKOUT:-/tmp/AI-PLAYBOOK}"
BRANCH="${SOURCE_BRANCH:-main}"

if [[ "${SOURCE_UPDATE_APPROVED:-}" != "yes" ]]; then
  echo "dry-run: set SOURCE_UPDATE_APPROVED=yes to fast-forward ${CHECKOUT}. No process is restarted."
  exit 0
fi

if [[ ! -d "${CHECKOUT}/.git" ]]; then
  echo "refusing: ${CHECKOUT} is not a git checkout. Nothing was changed." >&2
  exit 2
fi

cd "${CHECKOUT}"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "refusing: ${CHECKOUT} has tracked edits. Nothing was changed." >&2
  exit 2
fi

before="$(git rev-parse HEAD)"
git fetch origin "${BRANCH}"
git merge --ff-only "origin/${BRANCH}"
after="$(git rev-parse HEAD)"
echo "source-only ${before} -> ${after}"
echo "Qwen, the gateway, and the console were not signalled."
