#!/bin/bash
# Fast-forward one clean checkout. Does not signal Qwen, the gateway, or the console.
set -euo pipefail

CHECKOUT="${SOURCE_CHECKOUT:-/tmp/AI-PLAYBOOK}"
BRANCH="${SOURCE_BRANCH:-main}"
EXPECTED_ORIGIN="https://github.com/henokmeron/AI-PLAYBOOK.md.git"

if [[ "${SOURCE_UPDATE_APPROVED:-}" != "yes" ]]; then
  echo "dry-run: set SOURCE_UPDATE_APPROVED=yes to fast-forward ${CHECKOUT}."
  echo "preflight: origin must be ${EXPECTED_ORIGIN}; the checkout must be git and have no tracked edits."
  echo "rollback: git merge --ff-only leaves HEAD unchanged when it refuses."
  echo "acceptance: after a fast-forward, HEAD must equal origin/${BRANCH}. Health URLs are not called."
  echo "Qwen, the gateway, and the console are not signalled."
  exit 0
fi

if [[ ! -d "${CHECKOUT}/.git" ]]; then
  echo "refusing: ${CHECKOUT} is not a git checkout. Nothing was changed." >&2
  exit 2
fi

cd "${CHECKOUT}"
origin_url="$(git remote get-url origin)"
if [[ "${origin_url}" != "${EXPECTED_ORIGIN}" ]]; then
  echo "refusing: origin is not ${EXPECTED_ORIGIN}. Nothing was changed." >&2
  exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "refusing: ${CHECKOUT} has tracked edits. Nothing was changed." >&2
  exit 2
fi

before="$(git rev-parse HEAD)"
git fetch origin "${BRANCH}"
git merge --ff-only "origin/${BRANCH}"
after="$(git rev-parse HEAD)"
published="$(git rev-parse "origin/${BRANCH}")"
if [[ "${after}" != "${published}" ]]; then
  echo "acceptance failed: HEAD ${after} is not origin/${BRANCH} ${published}." >&2
  echo "rollback: do not reset. A refused fast-forward leaves HEAD at ${before}." >&2
  exit 2
fi
echo "source-only ${before} -> ${after}"
echo "acceptance: HEAD matches origin/${BRANCH}. Health URLs were not called."
echo "rollback: a refused fast-forward leaves HEAD at the previous commit."
echo "Qwen, the gateway, and the console were not signalled."
