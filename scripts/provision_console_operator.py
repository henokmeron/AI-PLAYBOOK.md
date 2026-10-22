#!/usr/bin/env python3
"""Provision named console operators (local administrative process).

Examples:

  # First administrator (password from stdin; never pass on argv)
  OPERATOR_AUTH_DIR=/tmp/console-operators \\
    python3 scripts/provision_console_operator.py create-admin --username alice

  # Additional operator (requires OPERATOR_ADMIN_USERNAME / OPERATOR_ADMIN_PASSWORD
  # in the environment for this local CLI only — not used by the web UI)
  python3 scripts/provision_console_operator.py add --username bob --role operator

  python3 scripts/provision_console_operator.py disable --username bob
  python3 scripts/provision_console_operator.py set-role --username bob --role viewer
  python3 scripts/provision_console_operator.py list

  # Forgotten password. Needs write access to OPERATOR_AUTH_DIR, like create-admin.
  # Every session of that operator is signed out.
  python3 scripts/provision_console_operator.py reset-password --username alice

Passwords are read from the OPERATOR_PASSWORD environment variable or, if unset,
from a hidden prompt (or a single stdin line when not interactive). If
OPERATOR_ADMIN_PASSWORD is unset, the administrator password is prompted for.
Values are never printed.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_WEB = _REPO / "web"
for path in (_REPO, _WEB):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from auth.service import AuthError, AuthService  # noqa: E402
from auth.permissions import role_names  # noqa: E402


def _read_password(prompt: str) -> str:
    env = os.environ.get("OPERATOR_PASSWORD", "")
    if env:
        return env
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    return sys.stdin.readline().rstrip("\n")


def _service() -> AuthService:
    return AuthService()


def cmd_create_admin(args: argparse.Namespace) -> int:
    service = _service()
    if service.configured():
        print("ERROR: operators already exist; use add / set-role / disable instead.", file=sys.stderr)
        return 2
    password = _read_password("Administrator password: ")
    confirm = _read_password("Confirm password: ") if sys.stdin.isatty() and not os.environ.get("OPERATOR_PASSWORD") else password
    if password != confirm:
        print("ERROR: passwords do not match.", file=sys.stderr)
        return 2
    try:
        record = service.create_operator(
            args.username, password, "admin", allow_first_admin=True, actor="provision-cli",
        )
    except AuthError as exc:
        print(f"ERROR: {exc.message}", file=sys.stderr)
        return 2
    print(f"Created administrator {record.username} (id {record.operator_id[:12]}…).")
    print(f"Auth directory: {service.store.directory}")
    return 0


def _require_local_admin(service: AuthService) -> str:
    """CLI gate: prove admin credentials from the environment for local ops."""
    username = os.environ.get("OPERATOR_ADMIN_USERNAME", "").strip()
    password = os.environ.get("OPERATOR_ADMIN_PASSWORD", "")
    if username and not password and sys.stdin.isatty():
        password = getpass.getpass(f"Password for administrator {username}: ")
    if not username or not password:
        raise AuthError(
            "set OPERATOR_ADMIN_USERNAME (the administrator password is prompted for) for this administrative CLI action",
            status=401,
        )
    session = service.login(username, password, peer_ip="cli")
    if session.role != "admin":
        service.logout(session.session_id)
        raise AuthError("only an administrator may manage operator accounts", status=403)
    actor = session.username
    service.logout(session.session_id)
    return actor


def cmd_add(args: argparse.Namespace) -> int:
    service = _service()
    try:
        actor = _require_local_admin(service)
        password = _read_password("New operator password: ")
        record = service.create_operator(args.username, password, args.role, actor=actor)
    except AuthError as exc:
        print(f"ERROR: {exc.message}", file=sys.stderr)
        return 2
    print(f"Created {record.role} {record.username}.")
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    service = _service()
    try:
        actor = _require_local_admin(service)
        record = service.set_disabled(args.username, True, actor=actor)
    except AuthError as exc:
        print(f"ERROR: {exc.message}", file=sys.stderr)
        return 2
    print(f"Disabled {record.username}.")
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    service = _service()
    try:
        actor = _require_local_admin(service)
        record = service.set_disabled(args.username, False, actor=actor)
    except AuthError as exc:
        print(f"ERROR: {exc.message}", file=sys.stderr)
        return 2
    print(f"Enabled {record.username}.")
    return 0


def cmd_set_role(args: argparse.Namespace) -> int:
    service = _service()
    try:
        actor = _require_local_admin(service)
        record = service.set_role(args.username, args.role, actor=actor)
    except AuthError as exc:
        print(f"ERROR: {exc.message}", file=sys.stderr)
        return 2
    print(f"Set {record.username} role to {record.role}.")
    return 0


def _read_new_password(prompt: str) -> str:
    password = _read_password(prompt)
    if sys.stdin.isatty() and not os.environ.get("OPERATOR_PASSWORD"):
        if password != getpass.getpass("Confirm password: "):
            raise AuthError("passwords do not match")
    return password


def cmd_reset_password(args: argparse.Namespace) -> int:
    service = _service()
    try:
        password = _read_new_password(f"New password for {args.username}: ")
        record = service.reset_password(args.username, password, actor="provision-cli")
    except AuthError as exc:
        print(f"ERROR: {exc.message}", file=sys.stderr)
        return 2
    print(f"Password reset for {record.username}. Their existing sessions were signed out.")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    service = _service()
    rows = service.list_operators()
    if not rows:
        print("No operators provisioned.")
        return 0
    for row in rows:
        state = "disabled" if row["disabled"] else "active"
        print(f"{row['username']}\t{row['role']}\t{state}\t{row['operator_id']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision named console operators.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("create-admin", help="Create the first administrator")
    p_admin.add_argument("--username", required=True)
    p_admin.set_defaults(func=cmd_create_admin)

    p_add = sub.add_parser("add", help="Add an operator (requires admin env credentials)")
    p_add.add_argument("--username", required=True)
    p_add.add_argument("--role", choices=list(role_names()), default="operator")
    p_add.set_defaults(func=cmd_add)

    p_dis = sub.add_parser("disable", help="Disable an operator")
    p_dis.add_argument("--username", required=True)
    p_dis.set_defaults(func=cmd_disable)

    p_en = sub.add_parser("enable", help="Enable an operator")
    p_en.add_argument("--username", required=True)
    p_en.set_defaults(func=cmd_enable)

    p_role = sub.add_parser("set-role", help="Change an operator role")
    p_role.add_argument("--username", required=True)
    p_role.add_argument("--role", choices=list(role_names()), required=True)
    p_role.set_defaults(func=cmd_set_role)

    p_reset = sub.add_parser("reset-password", help="Set a new password (local store access required)")
    p_reset.add_argument("--username", required=True)
    p_reset.set_defaults(func=cmd_reset_password)

    p_list = sub.add_parser("list", help="List operators (no secrets)")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
