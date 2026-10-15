"""Decide whether a console-only reload is safe.

This does not start Qwen, does not start the gateway, and does not stop either
process. A dry run is the default. The shell wrapper is the only thing that
may replace the process listening on port 8080, and only after this module
returns ``restart-console``.
"""
from __future__ import annotations

import argparse
import sys

QWEN_PORT = 8002
GATEWAY_PORT = 8010
CONSOLE_PORT = 8080


class DeployRefusal(RuntimeError):
    """The requested console reload would be unsafe or is not approved."""


def _pids(value: str) -> list[int]:
    if not value.strip():
        return []
    rows = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise DeployRefusal("a process id was not a number; nothing was stopped")
        rows.append(int(part))
    return rows


def decide(
    *,
    approved: bool,
    health_8002: int,
    health_8010: int,
    pid_8002: str = "",
    pid_8010: str = "",
    pid_8080: str = "",
) -> str:
    """Return ``dry-run`` or ``restart-console``.

    Health values are HTTP status codes. ``000`` means the port did not answer.
    """
    if health_8002 != 200 or health_8010 != 200:
        raise DeployRefusal(
            "Qwen on port 8002 and the gateway on port 8010 must already answer HTTP 200. "
            "This path will not start them and will not stop them."
        )
    qwen = _pids(pid_8002)
    gateway = _pids(pid_8010)
    console = _pids(pid_8080)
    if not qwen or not gateway:
        raise DeployRefusal("Qwen and gateway process ids are required. Nothing was stopped.")
    protected = set(qwen) | set(gateway)
    if set(console) & protected:
        raise DeployRefusal("the console process id matches Qwen or the gateway. Nothing was stopped.")
    if not approved:
        return "dry-run"
    if len(console) != 1:
        raise DeployRefusal("expected exactly one process on port 8080. Nothing was stopped.")
    return "restart-console"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a console-only reload. Does not stop any process.")
    parser.add_argument("--approved", choices=("yes", "no"), default="no")
    parser.add_argument("--health-8002", type=int, required=True)
    parser.add_argument("--health-8010", type=int, required=True)
    parser.add_argument("--pid-8002", default="")
    parser.add_argument("--pid-8010", default="")
    parser.add_argument("--pid-8080", default="")
    args = parser.parse_args(argv)
    try:
        decision = decide(
            approved=args.approved == "yes",
            health_8002=args.health_8002,
            health_8010=args.health_8010,
            pid_8002=args.pid_8002,
            pid_8010=args.pid_8010,
            pid_8080=args.pid_8080,
        )
    except DeployRefusal as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
