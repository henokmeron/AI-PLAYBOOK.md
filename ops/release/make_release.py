#!/usr/bin/env python3
"""Create a checksummed source package for the current verified main commit.

The package is written outside the repository. This script does not start a
Pod, copy files to RunPod, or include model weights.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ops.release.package import (
    ReleaseError,
    build_manifest,
    default_release_dir,
    dirty_entries,
    git_executable,
    git_output,
    read_checksum_sidecar,
    sha256_file,
    verify_archive,
    write_checksum_sidecar,
    write_manifest,
)


def run_release_tests(repo: Path) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "ops.test_release_package"],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError("release tests failed")
    return ["ops.test_release_package"]


def create_package(repo: Path, destination: Path | None = None, *, run_tests: bool = True) -> dict:
    dirty = dirty_entries(repo)
    if dirty:
        raise ReleaseError("working tree is not clean: " + "; ".join(dirty[:8]))
    tests = run_release_tests(repo) if run_tests else []
    head = git_output(repo, "rev-parse", "HEAD")
    origin = git_output(repo, "rev-parse", "origin/main")
    if head != origin:
        raise ReleaseError("local main does not match origin/main")
    output = (destination or default_release_dir()) / head
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"AI-PLAYBOOK-{head}.tar.gz"
    if not archive.is_file():
        subprocess.run(
            [git_executable(), "-C", str(repo), "archive", "--format=tar.gz", "-o", str(archive), head],
            check=True,
        )
    checksum = sha256_file(archive)
    verify_archive(archive, checksum)
    sidecar = write_checksum_sidecar(output, archive.name, checksum)
    if read_checksum_sidecar(sidecar) != checksum:
        raise ReleaseError("checksum file does not match the archive")
    manifest = build_manifest(head, archive.name, checksum, tests)
    manifest_path = output / f"AI-PLAYBOOK-{head}.manifest.json"
    write_manifest(manifest_path, manifest)
    manifest["manifest_path"] = str(manifest_path)
    manifest["archive_path"] = str(archive)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package the verified main commit.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    try:
        manifest = create_package(Path(args.repo).resolve(), Path(args.output) if args.output else None)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"release_id={manifest['release_id']}")
    print(f"sha256={manifest['sha256']}")
    print(f"archive={manifest['archive_path']}")
    print("persistent_volume_copy=not_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
