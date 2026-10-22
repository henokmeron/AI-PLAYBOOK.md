#!/usr/bin/env python3
"""Check a release archive and extract it into an empty directory.

This does not start Qwen, the gateway, or the console, and it does not read
or print secrets. Service start remains the existing Pod procedure.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ops.git_parity import EXPECTED_ORIGIN
from ops.release.package import ReleaseError, extract_archive, git_executable


def attach_published_origin(destination: Path) -> None:
    """Record the published origin in an extracted tree.

    ``git archive`` omits ``.git``. The parity suite reads ``git remote -v``
    and does not fetch. This does not commit, fetch, or change git config
    outside the destination. An existing origin that already matches is left
    as it is.
    """
    destination = destination.resolve()
    if not destination.is_dir():
        raise ReleaseError("destination is not a directory")
    exe = git_executable()
    if not (destination / ".git").exists():
        init = subprocess.run(
            [exe, "-c", "init.defaultBranch=main", "-C", str(destination), "init", "-q"],
            check=False,
            capture_output=True,
            text=True,
        )
        if init.returncode != 0:
            detail = (init.stderr or init.stdout or "git init failed").strip()
            raise ReleaseError(detail)
    probe = subprocess.run(
        [exe, "-C", str(destination), "remote", "get-url", "origin"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        added = subprocess.run(
            [exe, "-C", str(destination), "remote", "add", "origin", EXPECTED_ORIGIN],
            check=False,
            capture_output=True,
            text=True,
        )
        if added.returncode != 0:
            detail = (added.stderr or added.stdout or "git remote add failed").strip()
            raise ReleaseError(detail)
        return
    if probe.stdout.strip() != EXPECTED_ORIGIN:
        raise ReleaseError("origin is already set to a different url")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract a verified source release.")
    parser.add_argument("--archive", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    try:
        destination = Path(args.destination)
        extract_archive(Path(args.archive), destination, args.sha256.strip())
        attach_published_origin(destination)
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"extracted={args.destination}")
    print("automatic: checksum verified and source extracted")
    print("automatic: published origin recorded in .git; no fetch and no commit")
    print("human: in a clean image, run sh ops/release/install-clean-env.sh <checkout>")
    print("human: provision an operator before restarting the console")
    print("human: on the Pod, keep model weights on /workspace and use ops/release/START.sh or deploy-console-only.sh")
    print("human: do not treat this extraction as a running deployment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
