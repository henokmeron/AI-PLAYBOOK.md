"""Secure secret storage for enrolled device credentials.

Windows: DPAPI (Data Protection API) via CryptProtectData/CryptUnprotectData.
Fallback: Private file with restricted ACL (development/non-Windows).

Never log or print the secret after creation. The DPAPI blob is user-scoped;
if the user profile is deleted or the machine is re-imaged, the device must
re-enrol. This is intentional: the secret is tied to the Windows user account.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from .errors import InvalidRequest
from .state_guard import StatePermissionError, assert_private, restrict_private


def _dpapi_available() -> bool:
    """Check if DPAPI is available on this system."""
    return os.name == "nt"


def _dpapi_encrypt(plaintext: str) -> bytes:
    """Encrypt a secret using Windows DPAPI (user scope)."""
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    data = plaintext.encode("utf-8")
    input_blob = DataBlob(len(data), ctypes.cast(ctypes.c_char_p(data), ctypes.POINTER(ctypes.c_char)))
    output_blob = DataBlob()

    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "AI-PLAYBOOK device secret",
        None,
        None,
        None,
        0x1,
        ctypes.byref(output_blob),
    ):
        raise InvalidRequest("device secret could not be encrypted")

    try:
        encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        if output_blob.pbData:
            kernel32.LocalFree(output_blob.pbData)

    return encrypted


def _dpapi_decrypt(encrypted: bytes) -> str:
    """Decrypt a DPAPI-protected blob."""
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    input_blob = DataBlob(len(encrypted), ctypes.cast(ctypes.c_char_p(encrypted), ctypes.POINTER(ctypes.c_char)))
    output_blob = DataBlob()

    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(output_blob),
    ):
        raise InvalidRequest("device secret could not be decrypted")

    try:
        plaintext = ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
    finally:
        if output_blob.pbData:
            kernel32.LocalFree(output_blob.pbData)

    return plaintext


def write_secret(path: Path, secret: str, *, metadata: dict[str, Any] | None = None) -> None:
    """Write a device secret to secure storage.
    
    Windows: DPAPI-encrypted blob in a JSON file with metadata.
    Other: Private file (mode 0600) with plaintext + metadata.
    
    Never print the secret value. Metadata may include device_id, stored_at,
    schema_version, but never the secret itself.
    """
    if not isinstance(secret, str) or len(secret) < 32:
        raise InvalidRequest("device secret is too short")

    safe_path = _validate_path(path)
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    meta = dict(metadata or {})
    meta["storage_type"] = "dpapi" if _dpapi_available() else "private_file"
    meta["schema_version"] = 1

    if _dpapi_available():
        encrypted = _dpapi_encrypt(secret)
        payload = {
            "encrypted": base64.b64encode(encrypted).decode("ascii"),
            "metadata": meta,
        }
        content = json.dumps(payload, sort_keys=True)
    else:
        payload = {
            "secret": secret,
            "metadata": meta,
        }
        content = json.dumps(payload, sort_keys=True)

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(safe_path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
    except Exception:
        safe_path.unlink(missing_ok=True)
        raise

    try:
        restrict_private(safe_path)
    except StatePermissionError as exc:
        safe_path.unlink(missing_ok=True)
        raise InvalidRequest("device secret file could not be made private") from exc


def read_secret(path: Path) -> tuple[str, dict[str, Any]]:
    """Read a device secret from secure storage.
    
    Returns: (secret, metadata)
    
    Supports migration: if an old plaintext token file exists and is private,
    it will be read successfully (metadata will indicate legacy format).
    """
    safe_path = _validate_path(path)
    
    try:
        assert_private(safe_path)
    except StatePermissionError as exc:
        raise InvalidRequest("device secret file is not private") from exc

    content = safe_path.read_text(encoding="utf-8").strip()
    
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        if len(content) >= 32:
            return content, {"storage_type": "legacy_plaintext", "schema_version": 0}
        raise InvalidRequest("device secret file is not usable")

    if not isinstance(payload, dict):
        raise InvalidRequest("device secret file is not usable")

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    if "encrypted" in payload:
        if not _dpapi_available():
            raise InvalidRequest("DPAPI-encrypted secret cannot be read on non-Windows system")
        try:
            encrypted = base64.b64decode(payload["encrypted"])
        except Exception as exc:
            raise InvalidRequest("device secret file is not usable") from exc
        secret = _dpapi_decrypt(encrypted)
        return secret, metadata

    if "secret" in payload:
        secret = str(payload["secret"])
        if len(secret) < 32:
            raise InvalidRequest("device secret file is not usable")
        return secret, metadata

    raise InvalidRequest("device secret file is not usable")


def migrate_to_dpapi(path: Path) -> bool:
    """Migrate a legacy plaintext secret file to DPAPI storage.
    
    Returns True if migration was performed, False if already using DPAPI or not needed.
    Only migrates on Windows when the file is private.
    """
    if not _dpapi_available():
        return False

    safe_path = _validate_path(path)
    if not safe_path.is_file():
        return False

    try:
        secret, metadata = read_secret(path)
    except InvalidRequest:
        return False

    storage_type = metadata.get("storage_type", "unknown")
    if storage_type == "dpapi":
        return False

    backup_path = safe_path.with_suffix(safe_path.suffix + ".backup")
    safe_path.rename(backup_path)

    try:
        write_secret(safe_path, secret, metadata={"migrated_from": storage_type})
        backup_path.unlink()
        return True
    except Exception:
        if backup_path.is_file():
            backup_path.rename(safe_path)
        raise


def _validate_path(path: Path) -> Path:
    """Validate that the secret path is safe (absolute, not a link, off git tree)."""
    if not path.is_absolute():
        raise InvalidRequest("secret file must be an absolute path")

    if path.is_symlink() or path.parent.is_symlink():
        raise InvalidRequest("secret file must be a regular path")

    resolved = path.resolve()
    if resolved.is_symlink():
        raise InvalidRequest("secret file must be a regular path")

    repo = Path(__file__).resolve().parents[1]
    forbidden = [repo]
    if os.name == "posix":
        forbidden.append(Path("/workspace"))

    for root in forbidden:
        if resolved == root or root in resolved.parents:
            raise InvalidRequest("secret file must stay off the source tree and the shared volume")

    return resolved


def remove_secret(path: Path) -> None:
    """Delete the local device secret file. Does not revoke the server record."""
    safe_path = _validate_path(path)
    if safe_path.is_file():
        safe_path.unlink()
