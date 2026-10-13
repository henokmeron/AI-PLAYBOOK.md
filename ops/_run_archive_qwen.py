#!/usr/bin/env python3
"""Run archive-qwen-runtime.sh after LF-normalizing the script on the Pod."""
from __future__ import annotations

import subprocess
from pathlib import Path

SRC = Path("/tmp/archive-qwen-runtime.sh")
DST = Path("/tmp/archive-qwen-runtime.lf.sh")


def main() -> int:
    text = SRC.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    DST.write_bytes(text)
    DST.chmod(0o755)
    proc = subprocess.run(["bash", str(DST)], check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
