#!/usr/bin/env python3
"""Check a release archive and extract it into an empty directory.

This does not start Qwen, the gateway, or the console, and it does not read
or print secrets. Service start remains the existing Pod procedure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ops.release.package import ReleaseError, extract_archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract a verified source release.")
    parser.add_argument("--archive", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    try:
        extract_archive(Path(args.archive), Path(args.destination), args.sha256.strip())
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"extracted={args.destination}")
    print("automatic: checksum verified and source extracted")
    print("human: provision an operator before restarting the console")
    print("human: on the Pod, keep model weights on /workspace and use ops/release/START.sh or deploy-console-only.sh")
    print("human: do not treat this extraction as a running deployment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
