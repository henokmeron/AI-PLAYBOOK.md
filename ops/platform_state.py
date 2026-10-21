"""Operator durability without putting live secrets on the Global Volume.

The console reads operators from local disk, where mode 0700/0600 can be
enforced. A Pod stop deletes ``/tmp``. The Global Volume keeps a checksummed
copy of ``operators.json`` only. That copy is scrypt hashes, not passwords.
Sessions, the gateway key, and the Microsoft token are not backed up: the
volume can reject chmod, so it is the wrong place for those secrets.

Nothing in this module prints file contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BACKUP_NAME = re.compile(r"^\d{8}T\d{6}\d{0,6}Z$")
_MAX_OPERATOR_BYTES = 1_000_000
_KEEP_BACKUPS = 5
LIVE_OPERATOR_DIR = Path("/tmp/console-operators")
VOLUME_BACKUP_DIR = Path("/workspace/platform-state/operator-backups")


class PlatformStateError(Exception):
    """The operator store cannot be used. The message has no secret material."""


def volume_is_global() -> bool:
    """True when /workspace is the RunPod Global Volume."""
    mounts = Path("/proc/self/mountinfo")
    try:
        text = mounts.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 9:
            continue
        # mountinfo: ... mountpoint ... - fstype source super
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        mount_point = fields[4]
        fstype = fields[separator + 1] if separator + 1 < len(fields) else ""
        if mount_point == "/workspace" and fstype == "fuse.geesefs":
            return True
    return False


def layout_report(*, volume_mounted: bool | None = None) -> dict[str, Any]:
    mounted = volume_is_global() if volume_mounted is None else volume_mounted
    return {
        "source_checkout": "/tmp/AI-PLAYBOOK",
        "source_durable": False,
        "weights": "/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654",
        "runtime_archive": "/workspace/runtime-setup/qwen-vllm/vllm-qwen-env.tar.zst",
        "runtime_env": "/tmp/vllm-qwen-env",
        "runtime_env_durable": False,
        "release_launcher": "/workspace/ai-platform-release/START.sh",
        "operator_live_dir": str(LIVE_OPERATOR_DIR),
        "operator_live_durable": False,
        "operator_backup_dir": str(VOLUME_BACKUP_DIR) if mounted else None,
        "operator_backup_contains": ["operators.json", "SHA256SUMS"],
        "not_backed_up": [
            "sessions.json",
            "/tmp/platform-gateway.key",
            "/tmp/microsoft-365-token.json",
        ],
        "ops_events_dir": "/workspace/ops-centre",
        "note": (
            "Live operator files stay on Pod-local disk so permissions can be enforced. "
            "The volume backup stores scrypt hashes and survives a Pod stop. "
            "It is not a private POSIX store: Global Volume chmod may be rejected. "
            "A restore copies the hashes back to local disk and restricts that copy."
        ),
    }


def _read_regular(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PlatformStateError("operator file must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags | nofollow) if nofollow else os.open(path, flags)
    except OSError:
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise PlatformStateError("operator file could not be read") from exc
    try:
        data = os.read(fd, _MAX_OPERATOR_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > _MAX_OPERATOR_BYTES:
        raise PlatformStateError("operator file is too large")
    return data


def _admin_count(document: dict[str, Any]) -> int:
    from web.auth.passwords import scrypt_hash_well_formed

    rows = document.get("operators")
    if not isinstance(rows, list) or not rows:
        raise PlatformStateError("operator file has no accounts")
    admins = 0
    for item in rows:
        if not isinstance(item, dict):
            raise PlatformStateError("operator file has an unusable row")
        if "password" in item:
            raise PlatformStateError("operator file must store a scrypt hash, not a password")
        try:
            role = str(item["role"])
            disabled = bool(item.get("disabled", False))
            operator_id = str(item["operator_id"]).strip()
            username = str(item["username"]).strip()
            password_hash = str(item["password_hash"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PlatformStateError("operator file has an unusable row") from exc
        if not operator_id or not username or role not in {"admin", "operator", "viewer"}:
            raise PlatformStateError("operator file has an unusable row")
        if not scrypt_hash_well_formed(password_hash):
            raise PlatformStateError("operator file must store a scrypt hash, not a password")
        if role == "admin" and not disabled:
            admins += 1
    if admins < 1:
        raise PlatformStateError("an enabled administrator is required")
    return admins


def _load_private(path: Path) -> tuple[bytes, int]:
    from integrations.state_guard import StatePermissionError, assert_private

    try:
        assert_private(path.parent)
        assert_private(path)
    except StatePermissionError as exc:
        raise PlatformStateError("operator file is not private") from exc
    data = _read_regular(path)
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PlatformStateError("operator file is not valid JSON") from exc
    if not isinstance(document, dict):
        raise PlatformStateError("operator file is not valid JSON")
    return data, _admin_count(document)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _latest_valid_backup(backup_dir: Path) -> tuple[Path, bytes] | None:
    if not backup_dir.is_dir() or backup_dir.is_symlink():
        return None
    names = sorted(
        (item.name for item in backup_dir.iterdir() if item.is_dir() and not item.is_symlink() and _BACKUP_NAME.fullmatch(item.name)),
        reverse=True,
    )
    for name in names:
        folder = backup_dir / name
        blob = folder / "operators.json"
        manifest = folder / "SHA256SUMS"
        if blob.is_symlink() or manifest.is_symlink() or not blob.is_file() or not manifest.is_file():
            continue
        try:
            data = _read_regular(blob)
            line = manifest.read_text(encoding="utf-8").splitlines()[0]
            digest, _label = line.split(maxsplit=1)
        except (OSError, UnicodeError, IndexError, ValueError):
            continue
        if digest != _sha256(data) or not line.endswith("operators.json"):
            continue
        try:
            document = json.loads(data.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        try:
            _admin_count(document)
        except PlatformStateError:
            continue
        return folder, data
    return None


def _rotate(backup_dir: Path) -> None:
    names = sorted(
        (item.name for item in backup_dir.iterdir() if item.is_dir() and not item.is_symlink() and _BACKUP_NAME.fullmatch(item.name)),
    )
    for name in names[:-_KEEP_BACKUPS]:
        target = backup_dir / name
        if target.is_symlink():
            continue
        shutil.rmtree(target, ignore_errors=True)


def write_backup(live_file: Path, backup_dir: Path) -> Path:
    """Copy a private operator file to a checksummed directory. Sessions are not copied."""
    data, _admins = _load_private(live_file)
    if backup_dir.is_symlink():
        raise PlatformStateError("backup directory must not be a symbolic link")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = backup_dir / stamp
    if folder.exists() or folder.is_symlink():
        raise PlatformStateError("backup directory already exists")
    folder.mkdir(parents=False)
    blob = folder / "operators.json"
    manifest = folder / "SHA256SUMS"
    blob.write_bytes(data)
    manifest.write_text(f"{_sha256(data)}  operators.json\n", encoding="utf-8")
    _rotate(backup_dir)
    return folder


def restore_backup(backup_dir: Path, live_dir: Path) -> int:
    """Install the newest valid backup as a private local operator file.

    Existing live files are not replaced. Session files are not restored.
    """
    from integrations.state_guard import restrict_private

    if live_dir.is_symlink():
        raise PlatformStateError("operator directory must not be a symbolic link")
    destination = live_dir / "operators.json"
    if destination.exists() or destination.is_symlink():
        raise PlatformStateError("operator file already exists and was not replaced")
    found = _latest_valid_backup(backup_dir)
    if found is None:
        raise PlatformStateError("no valid operator backup was found")
    _folder, data = found
    live_dir.mkdir(parents=True, exist_ok=True)
    restrict_private(live_dir)
    temporary = live_dir / "operators.json.tmp"
    if temporary.is_symlink():
        raise PlatformStateError("operator file must not be a symbolic link")
    temporary.write_bytes(data)
    restrict_private(temporary)
    temporary.replace(destination)
    restrict_private(destination)
    _data, admins = _load_private(destination)
    return admins


def assess(*, live_dir: Path, backup_dir: Path | None, apply: bool) -> dict[str, Any]:
    """Return a status document with no hashes and no passwords.

    ``apply`` false does not write. ``apply`` true backs up a healthy live
    file, or restores one backup when the live file is absent.
    """
    live_dir = Path(live_dir)
    backup = Path(backup_dir) if backup_dir else None
    live_file = live_dir / "operators.json"
    status: dict[str, Any] = {
        "ready": False,
        "action": "none",
        "backup": "skipped" if backup is None else "not_needed",
        "sessions_restored": False,
        "admins": 0,
    }
    if live_file.is_symlink() or live_dir.is_symlink():
        raise PlatformStateError("operator file must not be a symbolic link")
    if live_file.exists():
        data, admins = _load_private(live_file)
        status["ready"] = True
        status["admins"] = admins
        status["action"] = "live"
        if backup is None:
            return status
        if not apply:
            status["backup"] = "would_backup"
            return status
        try:
            write_backup(live_file, backup)
        except (OSError, PlatformStateError):
            status["action"] = "live"
            status["backup"] = "failed"
            return status
        status["action"] = "backed_up"
        status["backup"] = "ok"
        if _sha256(_read_regular(live_file)) != _sha256(data):
            raise PlatformStateError("operator file changed while it was being backed up")
        return status
    if backup is None or _latest_valid_backup(backup) is None:
        raise PlatformStateError("no private administrator is provisioned and no backup can restore one")
    if not apply:
        status["ready"] = True
        status["action"] = "would_restore"
        status["backup"] = "present"
        return status
    try:
        admins = restore_backup(backup, live_dir)
    except OSError as exc:
        raise PlatformStateError("operator backup could not be restored") from exc
    status["ready"] = True
    status["admins"] = admins
    status["action"] = "restored"
    status["backup"] = "ok"
    status["sessions_restored"] = False
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or recover the operator store. Does not print secrets.")
    parser.add_argument("--layout", action="store_true", help="Print the storage map and exit")
    parser.add_argument("--check", action="store_true", help="Report readiness without writing")
    parser.add_argument("--live-dir", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args(argv)
    if args.layout:
        sys.stdout.write(json.dumps(layout_report(), sort_keys=True) + "\n")
        return 0
    if args.live_dir is None:
        sys.stderr.write("operator live directory is required\n")
        return 2
    try:
        status = assess(live_dir=args.live_dir, backup_dir=args.backup_dir, apply=not args.check)
    except PlatformStateError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    sys.stdout.write(json.dumps(status, sort_keys=True) + "\n")
    return 0 if status["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
