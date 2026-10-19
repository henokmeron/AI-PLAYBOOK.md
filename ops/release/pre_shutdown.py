#!/usr/bin/env python3
"""Prepare a release before a planned Pod shutdown.

This script does not stop, start, resize, or recreate the Pod.
READY_TO_SHUTDOWN is returned only when the local package and the persistent
volume copy were both verified. A missing SSH key or an unreachable volume
is BLOCKED.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ops.release.make_release import create_package
from ops.release.package import ReleaseError


def checkpoint_status(package_ok: bool, volume_verified: bool) -> str:
    if package_ok and volume_verified:
        return "READY_TO_SHUTDOWN"
    if package_ok and not volume_verified:
        return "BLOCKED"
    return "NOT_VERIFIED"


def ssh_key_present() -> bool:
    return Path.home().joinpath(".ssh", "id_ed25519").is_file()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the pre-shutdown release checkpoint.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--volume-verified", action="store_true")
    args = parser.parse_args(argv)
    package_ok = False
    manifest = None
    try:
        manifest = create_package(Path(args.repo).resolve())
        package_ok = True
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
    volume_verified = bool(args.volume_verified)
    if not ssh_key_present() and not volume_verified:
        print("persistent_volume=NOT_VERIFIED")
        print("blocker=SSH key %USERPROFILE%\\.ssh\\id_ed25519 is missing, so the volume was not contacted")
    elif not volume_verified:
        print("persistent_volume=NOT_VERIFIED")
        print("blocker=no read-back checksum from /workspace/releases was supplied")
    status = checkpoint_status(package_ok, volume_verified)
    print(f"status={status}")
    if manifest:
        print(f"release_id={manifest['release_id']}")
        print(f"sha256={manifest['sha256']}")
        print(f"archive={manifest['archive_path']}")
    print("pod_stopped=false")
    print(f"github_main={os.environ.get('GITHUB_MAIN_VERIFIED', 'see origin/main')}")
    return 0 if status == "READY_TO_SHUTDOWN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
