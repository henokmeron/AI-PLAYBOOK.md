"""Secret providers. Secret values are wrapped so repr/str/logging never reveal them."""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Mapping, Protocol

from .errors import AuthenticationError

SECRET_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]{1,63}\Z")
MAX_SECRET_FILE_BYTES = 16 * 1024


class Secret:
    __slots__ = ("_value", "name")

    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"Secret(name={self.name!r}, value='[REDACTED]')"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        return repr(self)

    def __eq__(self, other: object) -> bool:  # avoid accidental comparisons leaking via logs
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def __reduce__(self):
        raise TypeError("Secret objects cannot be pickled")


class SecretProvider(Protocol):
    def get(self, name: str) -> Secret: ...


def _check_name(name: str) -> str:
    if not isinstance(name, str) or not SECRET_NAME_RE.fullmatch(name):
        raise ValueError("secret names must be UPPER_SNAKE_CASE (2-64 characters)")
    return name


class EnvSecretProvider:
    """Read secrets from environment variables limited to an explicit allowlist."""

    def __init__(self, allowed: set[str], environ: Mapping[str, str] | None = None) -> None:
        self._allowed = frozenset(_check_name(n) for n in allowed)
        self._environ = os.environ if environ is None else environ

    def get(self, name: str) -> Secret:
        _check_name(name)
        if name not in self._allowed:
            raise AuthenticationError(f"secret {name} is not allowlisted for this provider")
        value = self._environ.get(name, "")
        if not value.strip():
            raise AuthenticationError(f"secret {name} is not configured")
        return Secret(name, value.strip())


class FileSecretProvider:
    """Read one secret per file under ``directory`` (for example a tmpfs mount).

    On POSIX the file must not be readable by group/other and must be a regular
    file (no symlinks). Values are stripped of surrounding whitespace and BOM.
    """

    def __init__(self, directory: Path, enforce_permissions: bool | None = None) -> None:
        self.directory = Path(directory).resolve(strict=True)
        self._enforce = (os.name == "posix") if enforce_permissions is None else enforce_permissions

    def get(self, name: str) -> Secret:
        path = self.directory / _check_name(name)
        try:
            info = path.lstat()
        except FileNotFoundError:
            raise AuthenticationError(f"secret {name} is not configured") from None
        if not stat.S_ISREG(info.st_mode):
            raise AuthenticationError(f"secret {name} is not a regular file")
        if self._enforce and info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise AuthenticationError(f"secret {name} file permissions are too open (require 600)")
        if info.st_size > MAX_SECRET_FILE_BYTES:
            raise AuthenticationError(f"secret {name} file is too large")
        value = path.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        if not value:
            raise AuthenticationError(f"secret {name} is empty")
        return Secret(name, value)
