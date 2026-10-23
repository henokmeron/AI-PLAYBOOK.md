"""Durability for operator accounts and enrolled devices.

The console reads both from local disk, where mode 0700/0600 can be
enforced. A Pod stop deletes ``/tmp``. The Global Volume keeps checksummed
copies:

- ``operators.json`` — scrypt hashes, not passwords
- ``endpoint-devices.json`` — enrolment-code hashes, device-secret hashes,
  and diagnostic summaries

Sessions, the gateway key, the Microsoft token, and the Microsoft client id
are not backed up. The volume can reject chmod, so those secrets stay off it.
The volume copies are not a private POSIX store. A restore writes them back
to local disk and restricts that copy. Nothing in this module prints file
contents.
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
_MAX_ENDPOINT_BYTES = 2_000_000
_KEEP_BACKUPS = 5
_HEX_HASH = re.compile(r"^[0-9a-f]{64}$")
_DEVICE_ID = re.compile(r"^[0-9a-f]{32}$")
_FORBIDDEN_ENDPOINT_KEYS = frozenset({
    "password",
    "password_hash",
    "device_secret",
    "enrolment_code",
    "enrollment_code",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "client_secret",
    "gateway_key",
    "authorization",
    "csrf_token",
    "session_id",
})
_ENDPOINT_CODE_KEYS = frozenset({"tenant_id", "code_hash", "expires_at", "used"})
_ENDPOINT_DEVICE_KEYS = frozenset({
    "tenant_id",
    "device_id",
    "display_name",
    "secret_hash",
    "status",
    "created_at",
    "last_report_at",
    "report",
    "fixture_label",
})
LIVE_OPERATOR_DIR = Path("/tmp/console-operators")
VOLUME_BACKUP_DIR = Path("/workspace/platform-state/operator-backups")
LIVE_ENDPOINT_FILE = Path("/tmp/endpoint-devices.json")
VOLUME_ENDPOINT_BACKUP_DIR = Path("/workspace/platform-state/endpoint-backups")
_ENDPOINT_BLOB = "endpoint-devices.json"


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
        "operator_live_dir": "/tmp/console-operators",
        "operator_live_durable": False,
        "operator_backup_dir": "/workspace/platform-state/operator-backups" if mounted else None,
        "operator_backup_contains": ["operators.json", "SHA256SUMS"],
        "endpoint_live_file": "/tmp/endpoint-devices.json",
        "endpoint_live_durable": False,
        "endpoint_backup_dir": "/workspace/platform-state/endpoint-backups" if mounted else None,
        "endpoint_backup_contains": [_ENDPOINT_BLOB, "SHA256SUMS"],
        "not_backed_up": [
            "sessions.json",
            "/tmp/platform-gateway.key",
            "/tmp/microsoft-365-token.json",
            "/tmp/microsoft-client-id",
        ],
        "ops_events_dir": "/workspace/ops-centre",
        "note": (
            "Live operator files and the device list stay on Pod-local disk so "
            "permissions can be enforced. Volume backups store scrypt hashes, "
            "enrolment-code hashes, device-secret hashes, and diagnostic summaries. "
            "They survive a Pod stop. They are not a private POSIX store: Global "
            "Volume chmod may be rejected. A restore copies them back to local disk "
            "and restricts that copy. Sessions, the gateway key, and the Microsoft "
            "token are not copied."
        ),
    }


def _read_regular(path: Path, limit: int = _MAX_OPERATOR_BYTES) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PlatformStateError("state file must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags | nofollow) if nofollow else os.open(path, flags)
    except OSError:
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise PlatformStateError("state file could not be read") from exc
    try:
        data = os.read(fd, limit + 1)
    finally:
        os.close(fd)
    if len(data) > limit:
        raise PlatformStateError("state file is too large")
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


def _write_tree(backup_dir: Path, blob_name: str, data: bytes) -> Path:
    if backup_dir.is_symlink():
        raise PlatformStateError("backup directory must not be a symbolic link")
    backup_dir.mkdir(parents=True, exist_ok=True)
    folder: Path | None = None
    for _attempt in range(5):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        if not _BACKUP_NAME.fullmatch(stamp):
            continue
        candidate = backup_dir / stamp
        if candidate.exists() or candidate.is_symlink():
            continue
        try:
            candidate.mkdir(parents=False)
        except FileExistsError:
            continue
        folder = candidate
        break
    if folder is None:
        raise PlatformStateError("backup directory already exists")
    blob = folder / blob_name
    manifest = folder / "SHA256SUMS"
    blob.write_bytes(data)
    manifest.write_text(f"{_sha256(data)}  {blob_name}\n", encoding="utf-8")
    _rotate(backup_dir)
    return folder


def write_backup(live_file: Path, backup_dir: Path) -> Path:
    """Copy a private operator file to a checksummed directory. Sessions are not copied."""
    data, _admins = _load_private(live_file)
    return _write_tree(backup_dir, "operators.json", data)


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


def _configured_dir(name: str, environ: dict[str, str] | None = None) -> Path | None:
    source = os.environ if environ is None else environ
    raw = source.get(name, "").strip()
    if not raw:
        return None
    return Path(raw)


def mirror_operators_from_env(live_dir: Path, environ: dict[str, str] | None = None) -> str:
    """Checksum the live operator file when OPERATOR_BACKUP_DIR is set.

    Returns ``ok``, ``skipped``, or ``failed``. A failure leaves the live file
    in place and does not copy sessions.
    """
    backup = _configured_dir("OPERATOR_BACKUP_DIR", environ)
    if backup is None:
        return "skipped"
    try:
        write_backup(Path(live_dir) / "operators.json", backup)
    except (OSError, PlatformStateError):
        return "failed"
    return "ok"


def _reject_endpoint_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            folded = str(key).replace("-", "_").casefold()
            if (
                folded in _FORBIDDEN_ENDPOINT_KEYS
                or folded.endswith("_secret")
                or folded.endswith("_token")
                or folded.endswith("_password")
            ):
                raise PlatformStateError("endpoint file must store hashes, not secrets")
            _reject_endpoint_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_endpoint_keys(item)


def _endpoint_document(data: bytes) -> dict[str, Any]:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PlatformStateError("endpoint file is not valid JSON") from exc
    if not isinstance(document, dict) or document.get("version") != 1:
        raise PlatformStateError("endpoint file is not usable")
    allowed = {"version", "codes", "devices"}
    if set(document) - allowed:
        raise PlatformStateError("endpoint file is not usable")
    _reject_endpoint_keys(document)
    codes = document.get("codes")
    devices = document.get("devices")
    if not isinstance(codes, list) or not isinstance(devices, list):
        raise PlatformStateError("endpoint file is not usable")
    for item in codes:
        if not isinstance(item, dict) or set(item) - _ENDPOINT_CODE_KEYS:
            raise PlatformStateError("endpoint file is not usable")
        if not isinstance(item.get("code_hash"), str) or not _HEX_HASH.fullmatch(item["code_hash"]):
            raise PlatformStateError("endpoint file is not usable")
        if not isinstance(item.get("tenant_id"), str) or not item["tenant_id"].strip():
            raise PlatformStateError("endpoint file is not usable")
    for item in devices:
        if not isinstance(item, dict) or set(item) - _ENDPOINT_DEVICE_KEYS:
            raise PlatformStateError("endpoint file is not usable")
        if item.get("status") not in {"enrolled", "revoked"}:
            raise PlatformStateError("endpoint file is not usable")
        if not isinstance(item.get("secret_hash"), str) or not _HEX_HASH.fullmatch(item["secret_hash"]):
            raise PlatformStateError("endpoint file is not usable")
        if not isinstance(item.get("device_id"), str) or not _DEVICE_ID.fullmatch(item["device_id"]):
            raise PlatformStateError("endpoint file is not usable")
        report = item.get("report")
        if report is not None and not isinstance(report, dict):
            raise PlatformStateError("endpoint file is not usable")
    return document


def _load_endpoint(path: Path) -> tuple[bytes, int]:
    from integrations.state_guard import StatePermissionError, assert_private

    if _inside(path, VOLUME_ENDPOINT_BACKUP_DIR) or _on_volume(path):
        raise PlatformStateError("endpoint live file must stay on local disk")
    try:
        assert_private(path)
    except StatePermissionError as exc:
        raise PlatformStateError("endpoint file is not private") from exc
    data = _read_regular(path, _MAX_ENDPOINT_BYTES)
    document = _endpoint_document(data)
    return data, len(document["devices"])


def _on_volume(path: Path) -> bool:
    try:
        resolved = path.resolve()
        workspace = Path("/workspace").resolve()
    except OSError:
        return False
    return resolved == workspace or workspace in resolved.parents


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def _latest_endpoint_backup(backup_dir: Path) -> tuple[Path, bytes] | None:
    if not backup_dir.is_dir() or backup_dir.is_symlink():
        return None
    names = sorted(
        (
            item.name
            for item in backup_dir.iterdir()
            if item.is_dir() and not item.is_symlink() and _BACKUP_NAME.fullmatch(item.name)
        ),
        reverse=True,
    )
    for name in names:
        folder = backup_dir / name
        blob = folder / _ENDPOINT_BLOB
        manifest = folder / "SHA256SUMS"
        if blob.is_symlink() or manifest.is_symlink() or not blob.is_file() or not manifest.is_file():
            continue
        try:
            data = _read_regular(blob, _MAX_ENDPOINT_BYTES)
            line = manifest.read_text(encoding="utf-8").splitlines()[0]
            digest, label = line.split(maxsplit=1)
        except (OSError, UnicodeError, IndexError, ValueError):
            continue
        if digest != _sha256(data) or label != _ENDPOINT_BLOB:
            continue
        try:
            _endpoint_document(data)
        except PlatformStateError:
            continue
        return folder, data
    return None


def _dedicated_directory(path: Path) -> bool:
    """True when this directory may be chmodded to 0700.

    ``/tmp`` is shared. Restricting it would break the pod. A dedicated
    folder such as ``/tmp/console-operators`` may be restricted.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return False
    blocked = {"", "/", "/tmp", "/var/tmp", "/workspace"}
    texts = {
        path.as_posix().rstrip("/").lower(),
        resolved.as_posix().rstrip("/").lower(),
    }
    if texts & blocked:
        return False
    if path.name.lower() == "tmp" and len(path.parts) <= 2:
        return False
    if resolved.name.lower() == "tmp" and len(resolved.parts) <= 2:
        return False
    return True


def write_endpoint_backup(live_file: Path, backup_dir: Path) -> Path:
    """Copy a private device list to a checksummed directory. Secrets are refused."""
    if _inside(Path(live_file), Path(backup_dir)):
        raise PlatformStateError("endpoint backup must not replace the live file")
    data, _devices = _load_endpoint(Path(live_file))
    return _write_tree(Path(backup_dir), _ENDPOINT_BLOB, data)


def restore_endpoint_backup(backup_dir: Path, live_file: Path) -> int:
    """Install the newest valid device-list backup as a private local file.

    An existing live file is not replaced. The parent directory is restricted
    only when it is a dedicated folder. ``/tmp`` is never chmodded.
    """
    from integrations.state_guard import restrict_private

    live_file = Path(live_file)
    parent = live_file.parent
    if live_file.is_symlink() or parent.is_symlink():
        raise PlatformStateError("endpoint file must not be a symbolic link")
    if live_file.exists():
        raise PlatformStateError("endpoint file already exists and was not replaced")
    if _on_volume(live_file) or _inside(live_file, backup_dir):
        raise PlatformStateError("endpoint live file must stay on local disk")
    found = _latest_endpoint_backup(backup_dir)
    if found is None:
        raise PlatformStateError("no valid endpoint backup was found")
    _folder, data = found
    parent.mkdir(parents=True, exist_ok=True)
    if _dedicated_directory(parent):
        restrict_private(parent)
    temporary = live_file.with_suffix(live_file.suffix + ".tmp")
    if temporary.is_symlink():
        raise PlatformStateError("endpoint file must not be a symbolic link")
    temporary.write_bytes(data)
    restrict_private(temporary)
    temporary.replace(live_file)
    restrict_private(live_file)
    _restored, devices = _load_endpoint(live_file)
    return devices


def assess_endpoint(*, live_file: Path, backup_dir: Path | None, apply: bool) -> dict[str, Any]:
    """Return device-list readiness. No hashes and no secrets are included.

    A missing live file with no backup is ready: nothing has enrolled yet.
    ``apply`` false does not write.
    """
    live_file = Path(live_file)
    backup = Path(backup_dir) if backup_dir else None
    status: dict[str, Any] = {
        "ready": False,
        "action": "none",
        "backup": "skipped" if backup is None else "absent",
        "devices": 0,
        "secrets_copied": False,
        "sessions_restored": False,
    }
    if live_file.is_symlink() or live_file.parent.is_symlink():
        raise PlatformStateError("endpoint file must not be a symbolic link")
    if live_file.exists():
        data, devices = _load_endpoint(live_file)
        status["ready"] = True
        status["devices"] = devices
        status["action"] = "live"
        if backup is None:
            return status
        if not apply:
            status["backup"] = "would_backup"
            return status
        try:
            write_endpoint_backup(live_file, backup)
        except (OSError, PlatformStateError):
            status["action"] = "live"
            status["backup"] = "failed"
            return status
        status["action"] = "backed_up"
        status["backup"] = "ok"
        if _sha256(_read_regular(live_file, _MAX_ENDPOINT_BYTES)) != _sha256(data):
            raise PlatformStateError("endpoint file changed while it was being backed up")
        return status
    if backup is None or _latest_endpoint_backup(backup) is None:
        status["ready"] = True
        status["action"] = "none"
        status["backup"] = "absent" if backup is not None else "skipped"
        return status
    if not apply:
        status["ready"] = True
        status["action"] = "would_restore"
        status["backup"] = "present"
        return status
    try:
        devices = restore_endpoint_backup(backup, live_file)
    except OSError as exc:
        raise PlatformStateError("endpoint backup could not be restored") from exc
    status["ready"] = True
    status["devices"] = devices
    status["action"] = "restored"
    status["backup"] = "ok"
    return status


def mirror_endpoint_from_env(live_file: Path, environ: dict[str, str] | None = None) -> str:
    """Checksum the live device list when ENDPOINT_BACKUP_DIR is set."""
    backup = _configured_dir("ENDPOINT_BACKUP_DIR", environ)
    if backup is None:
        return "skipped"
    try:
        write_endpoint_backup(Path(live_file), backup)
    except (OSError, PlatformStateError):
        return "failed"
    return "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or recover operator and device state. Does not print secrets.")
    parser.add_argument("--layout", action="store_true", help="Print the storage map and exit")
    parser.add_argument("--check", action="store_true", help="Report readiness without writing")
    parser.add_argument("--live-dir", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--endpoint-live", type=Path)
    parser.add_argument("--endpoint-backup", type=Path)
    args = parser.parse_args(argv)
    if args.layout:
        sys.stdout.write(json.dumps(layout_report(), sort_keys=True) + "\n")
        return 0
    if args.live_dir is None and args.endpoint_live is None:
        sys.stderr.write("operator live directory or endpoint live file is required\n")
        return 2
    apply = not args.check
    payload: dict[str, Any] = {}
    try:
        if args.live_dir is not None:
            payload["operators"] = assess(live_dir=args.live_dir, backup_dir=args.backup_dir, apply=apply)
        if args.endpoint_live is not None:
            payload["endpoint"] = assess_endpoint(
                live_file=args.endpoint_live,
                backup_dir=args.endpoint_backup,
                apply=apply,
            )
    except PlatformStateError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    if len(payload) == 1:
        status = next(iter(payload.values()))
    else:
        status = payload
    ready = all(item.get("ready") for item in payload.values())
    sys.stdout.write(json.dumps(status, sort_keys=True) + "\n")
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
