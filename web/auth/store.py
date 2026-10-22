"""File-backed operator and session persistence.

POSIX mode 0700/0600 and a Windows protected ACL are required. A failed
permission change is not ignored. See integrations.state_guard for what
Windows can and cannot guarantee.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class OperatorRecord:
    operator_id: str
    username: str
    password_hash: str = field(repr=False)
    role: str
    disabled: bool = False
    created_at: str = ""
    updated_at: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "username": self.username,
            "role": self.role,
            "disabled": self.disabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SessionRecord:
    session_id: str
    operator_id: str
    username: str
    role: str
    csrf_token: str
    created_at: float
    last_seen: float
    expires_at: float
    absolute_expires_at: float


class AuthStore:
    def __init__(self, directory: Path, *, clock: Callable[[], float] | None = None) -> None:
        self.directory = Path(directory)
        self.operators_path = self.directory / "operators.json"
        self.sessions_path = self.directory / "sessions.json"
        self._clock = clock or (lambda: __import__("time").time())
        self._lock = threading.RLock()
        self.operators: dict[str, OperatorRecord] = {}
        self.sessions: dict[str, SessionRecord] = {}
        self.directory.mkdir(parents=True, exist_ok=True)
        self._harden_dir()
        self._load_operators()
        self._load_sessions()

    def _harden_dir(self) -> None:
        from integrations.state_guard import restrict_private

        restrict_private(self.directory)

    def _harden_file(self, path: Path) -> None:
        if not path.is_file() or path.is_symlink():
            return
        from integrations.state_guard import restrict_private

        restrict_private(path)

    def _load_operators(self) -> None:
        if not self.operators_path.is_file():
            return
        try:
            raw = json.loads(self.operators_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = raw.get("operators") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return
        for item in rows:
            if not isinstance(item, dict):
                continue
            try:
                record = OperatorRecord(
                    operator_id=str(item["operator_id"]),
                    username=str(item["username"]),
                    password_hash=str(item["password_hash"]),
                    role=str(item["role"]),
                    disabled=bool(item.get("disabled", False)),
                    created_at=str(item.get("created_at") or ""),
                    updated_at=str(item.get("updated_at") or ""),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self.operators[record.operator_id] = record

    def _load_sessions(self) -> None:
        if not self.sessions_path.is_file():
            return
        try:
            raw = json.loads(self.sessions_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = raw.get("sessions") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return
        now = self._clock()
        for item in rows:
            if not isinstance(item, dict):
                continue
            try:
                record = SessionRecord(
                    session_id=str(item["session_id"]),
                    operator_id=str(item["operator_id"]),
                    username=str(item["username"]),
                    role=str(item["role"]),
                    csrf_token=str(item["csrf_token"]),
                    created_at=float(item["created_at"]),
                    last_seen=float(item["last_seen"]),
                    expires_at=float(item["expires_at"]),
                    absolute_expires_at=float(item["absolute_expires_at"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if record.expires_at > now and record.absolute_expires_at > now:
                self.sessions[record.session_id] = record

    def save_operators(self) -> None:
        with self._lock:
            payload = {
                "operators": [
                    {
                        **op.public(),
                        "password_hash": op.password_hash,
                    }
                    for op in sorted(self.operators.values(), key=lambda item: item.username)
                ]
            }
            tmp = self.operators_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            from integrations.state_guard import replace_file
            replace_file(tmp, self.operators_path)
            self._harden_file(self.operators_path)

    def save_sessions(self) -> None:
        with self._lock:
            now = self._clock()
            alive = {
                sid: sess
                for sid, sess in self.sessions.items()
                if sess.expires_at > now and sess.absolute_expires_at > now
            }
            self.sessions = alive
            payload = {"sessions": [asdict(item) for item in alive.values()]}
            tmp = self.sessions_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            from integrations.state_guard import replace_file
            replace_file(tmp, self.sessions_path)
            self._harden_file(self.sessions_path)

    def by_username(self, username: str) -> OperatorRecord | None:
        needle = username.strip().casefold()
        for record in self.operators.values():
            if record.username.casefold() == needle:
                return record
        return None
