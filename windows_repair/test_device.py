"""Enrol a dedicated test device and run one read-only diagnostic.

This does not install a Windows service and does not restart the Print Spooler.
"""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from .device_store import DeviceStore, dev_self_test


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Windows repair test device")
    parser.add_argument("command", choices=("self-test", "enrol"))
    parser.add_argument("--state", required=True, help="Absolute path outside this source tree")
    args = parser.parse_args(argv)
    path = Path(args.state)
    if args.command == "self-test":
        print(json.dumps(dev_self_test(path), indent=2, default=str))
        return 0
    secret = secrets.token_urlsafe(32)
    device_id = DeviceStore(path).enrol("local-test", secret)
    print(json.dumps({
        "device_id": device_id,
        "tenant_id": "local-test",
        "device_secret": secret,
        "repair_authority": False,
        "note": "Save the secret outside git. This enrolment does not allow repairs.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
