#!/bin/sh
# Dependencies a stock CPython image needs before python -m ops.run_tests.
# Installs git, pypdf, and openpyxl. A git archive has no .git, so this also
# records the published origin when that directory is missing. It does not
# fetch, clone, commit, copy model weights, or start a service.
set -eu
ROOT=${1:-.}
ORIGIN=https://github.com/henokmeron/AI-PLAYBOOK.md.git

if ! command -v git >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y git
fi

python -m pip install --disable-pip-version-check \
  "pypdf==6.20.0" \
  "openpyxl==3.1.5" \
  "et-xmlfile==2.0.0" \
  "defusedxml==0.7.1"

if [ ! -e "$ROOT/.git" ]; then
  git init -q "$ROOT"
fi
if ! git -C "$ROOT" remote get-url origin >/dev/null 2>&1; then
  git -C "$ROOT" remote add origin "$ORIGIN"
fi

git --version
git -C "$ROOT" remote -v
python -c 'import pypdf, openpyxl; print("pypdf=" + pypdf.__version__); print("openpyxl=" + openpyxl.__version__)'
