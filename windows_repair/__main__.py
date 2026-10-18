"""Run one local read-only disk check. Does not change this computer."""
from __future__ import annotations

import json

from .engine import execute
from .remote_support import status_from_env


def main() -> int:
    report = {
        "disk": execute("win.storage.space"),
        "remote_support": status_from_env(),
        "note": "problem_resolved false means this check did not declare a fault fixed.",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
