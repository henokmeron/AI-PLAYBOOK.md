#!/usr/bin/env python3
"""Clone/sync feature branch on Pod and launch first-release stack."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

REPO = Path("/tmp/AI-PLAYBOOK")
BRANCH = "feature/qwen3.5-27b-integration"
REMOTE = "https://github.com/henokmeron/AI-PLAYBOOK.md.git"


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, **kwargs)


def main() -> int:
    if not (REPO / ".git").is_dir():
        run(["git", "clone", "--branch", BRANCH, "--single-branch", REMOTE, str(REPO)])
    else:
        run(["git", "-C", str(REPO), "fetch", "origin", BRANCH])
        run(["git", "-C", str(REPO), "checkout", BRANCH])
        run(["git", "-C", str(REPO), "reset", "--hard", f"origin/{BRANCH}"])

    # Ensure PyYAML for registry endpoints
    subprocess.call(
        ["/usr/bin/python3", "-m", "pip", "install", "--quiet", "pyyaml"],
    )

    # Normalize scripts
    for rel in (
        "ops/start-first-release.sh",
        "ops/restore-qwen-runtime.sh",
        "ops/start-qwen-isolated.sh",
        "rag/setup_pypdf.sh",
        "rag/setup_openpyxl.sh",
    ):
        path = REPO / rel
        if path.is_file():
            data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            path.write_bytes(data)

    env = os.environ.copy()
    env["REPO_ROOT"] = str(REPO)
    run(["bash", str(REPO / "ops/start-first-release.sh"), "--start"], env=env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
