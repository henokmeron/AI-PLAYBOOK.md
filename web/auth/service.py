"""Named-operator authentication, sessions, and authorization."""
from __future__ import annotations

import os
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .passwords import DUMMY_PASSWORD_HASH, PasswordError, hash_password, verify_password
from .permissions import Permission, Role, permissions_for, role_names
from .store import AuthStore, OperatorRecord, SessionRecord, utc_now

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")
COOKIE_NAME = "console_session"
CSRF_HEADER = "X-CSRF-Token"
# Browsers set this and pages cannot. same-site is another port on this host.
_ALLOWED_FETCH_SITES = frozenset({"same-origin", "none"})
DEFAULT_IDLE_SECONDS = 8 * 3600
DEFAULT_ABSOLUTE_SECONDS = 24 * 3600
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES_PER_KEY = 10
GENERIC_LOGIN_ERROR = "Invalid username or password."


def browser_fetch_site_allowed(value: str | None) -> bool:
    """Whether a browser navigation may start a state-changing GET.

    ``None`` means the client did not send ``Sec-Fetch-Site`` (a non-browser
    tool). ``same-origin`` is the console page. ``none`` is the address bar.
    ``same-site`` is another port on this computer and ``cross-site`` is
    another site. Those, and any other value, are refused. The header is
    forbidden to script, so a page cannot claim to be same-origin.
    """
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().casefold() in _ALLOWED_FETCH_SITES


class AuthError(Exception):
    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


EventRecorder = Callable[..., Any]


def default_auth_dir() -> Path:
    env = os.environ.get("OPERATOR_AUTH_DIR", "").strip()
    if env:
        return Path(env)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "AI-PLAYBOOK" / "console-operators"
    return Path("/tmp/console-operators")


class AuthService:
    """Server-side operator identities and cookie sessions.

    Human authentication is separate from the gateway bearer key. Privileged
    browser APIs must call ``require_permission`` after validating a session.
    """

    def __init__(
        self,
        directory: Path | str | None = None,
        *,
        idle_seconds: int = DEFAULT_IDLE_SECONDS,
        absolute_seconds: int = DEFAULT_ABSOLUTE_SECONDS,
        clock: Callable[[], float] | None = None,
        record_event: EventRecorder | None = None,
    ) -> None:
        self.store = AuthStore(Path(directory or default_auth_dir()), clock=clock)
        self.idle_seconds = max(300, int(idle_seconds))
        self.absolute_seconds = max(self.idle_seconds, int(absolute_seconds))
        self._clock = clock or time.time
        self._record_event = record_event
        self._fail_lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}

    def configured(self) -> bool:
        return any(not op.disabled for op in self.store.operators.values())

    def _audit(self, event_type: str, outcome: str, *, actor: str | None = None, summary: str = "", detail: dict | None = None, severity: str = "info") -> None:
        if self._record_event is None:
            return
        try:
            self._record_event(
                event_type=event_type,
                component="auth",
                outcome=outcome,
                severity=severity,
                actor=actor,
                summary=summary[:400],
                detail=detail or {},
            )
        except Exception:  # noqa: BLE001 — audit must not break auth
            pass

    def create_operator(
        self,
        username: str,
        password: str,
        role: str,
        *,
        actor: str | None = None,
        allow_first_admin: bool = False,
    ) -> OperatorRecord:
        username = username.strip().casefold()
        if not USERNAME_RE.fullmatch(username):
            raise AuthError("username must be 3-32 chars: lowercase letter, then letters, digits, _ or -")
        try:
            role_value = Role(role).value
        except ValueError as exc:
            raise AuthError(f"role must be one of: {', '.join(role_names())}") from exc
        with self.store._lock:
            if self.store.by_username(username) is not None:
                raise AuthError("username is already taken", status=409)
            admins = [op for op in self.store.operators.values() if op.role == Role.ADMIN.value and not op.disabled]
            if not self.store.operators:
                if not allow_first_admin or role_value != Role.ADMIN.value:
                    raise AuthError("the first account must be an administrator created with the provision tool")
            elif allow_first_admin:
                raise AuthError("operators already exist; use an authenticated admin process")
            elif not admins:
                raise AuthError("an active administrator is required to create accounts")
            try:
                password_hash = hash_password(password)
            except PasswordError as exc:
                raise AuthError(str(exc)) from exc
            now = utc_now()
            record = OperatorRecord(
                operator_id=uuid.uuid4().hex,
                username=username,
                password_hash=password_hash,
                role=role_value,
                disabled=False,
                created_at=now,
                updated_at=now,
            )
            self.store.operators[record.operator_id] = record
            self.store.save_operators()
        self._audit(
            "auth.operator_created",
            "created",
            actor=actor,
            summary=f"Operator {username} created with role {role_value}",
            detail={"username": username, "role": role_value, "operator_id": record.operator_id},
        )
        return record

    def set_role(self, username: str, role: str, *, actor: str) -> OperatorRecord:
        try:
            role_value = Role(role).value
        except ValueError as exc:
            raise AuthError(f"role must be one of: {', '.join(role_names())}") from exc
        with self.store._lock:
            record = self.store.by_username(username)
            if record is None:
                raise AuthError("operator not found", status=404)
            if record.role == Role.ADMIN.value and role_value != Role.ADMIN.value:
                admins = [
                    op for op in self.store.operators.values()
                    if op.role == Role.ADMIN.value and not op.disabled and op.operator_id != record.operator_id
                ]
                if not admins:
                    raise AuthError("cannot demote the last active administrator", status=409)
            record.role = role_value
            record.updated_at = utc_now()
            self.store.save_operators()
            self._revoke_operator_sessions(record.operator_id)
        self._audit(
            "auth.role_changed",
            "updated",
            actor=actor,
            summary=f"Role for {record.username} set to {role_value}",
            detail={"username": record.username, "role": role_value},
        )
        return record

    def set_disabled(self, username: str, disabled: bool, *, actor: str) -> OperatorRecord:
        with self.store._lock:
            record = self.store.by_username(username)
            if record is None:
                raise AuthError("operator not found", status=404)
            if disabled and record.role == Role.ADMIN.value:
                admins = [
                    op for op in self.store.operators.values()
                    if op.role == Role.ADMIN.value and not op.disabled and op.operator_id != record.operator_id
                ]
                if not admins:
                    raise AuthError("cannot disable the last active administrator", status=409)
            record.disabled = bool(disabled)
            record.updated_at = utc_now()
            self.store.save_operators()
            if disabled:
                self._revoke_operator_sessions(record.operator_id)
        self._audit(
            "auth.operator_disabled" if disabled else "auth.operator_enabled",
            "disabled" if disabled else "enabled",
            actor=actor,
            summary=f"Operator {record.username} {'disabled' if disabled else 'enabled'}",
            detail={"username": record.username},
        )
        return record

    def list_operators(self) -> list[dict[str, Any]]:
        return [op.public() for op in sorted(self.store.operators.values(), key=lambda item: item.username)]

    def _failure_keys(self, username: str, peer_ip: str) -> list[str]:
        return [f"ip:{peer_ip or 'unknown'}", f"user:{(username or '').casefold() or '-'}"]

    def _prune_failures(self, key: str, now: float) -> list[float]:
        window_start = now - LOGIN_WINDOW_SECONDS
        rows = [stamp for stamp in self._failures.get(key, []) if stamp >= window_start]
        self._failures[key] = rows
        return rows

    def login_rate_limited(self, username: str, peer_ip: str) -> bool:
        now = self._clock()
        with self._fail_lock:
            for key in self._failure_keys(username, peer_ip):
                if len(self._prune_failures(key, now)) >= LOGIN_MAX_FAILURES_PER_KEY:
                    return True
        return False

    def _register_failure(self, username: str, peer_ip: str) -> None:
        now = self._clock()
        with self._fail_lock:
            for key in self._failure_keys(username, peer_ip):
                rows = self._prune_failures(key, now)
                rows.append(now)
                self._failures[key] = rows

    def _clear_failures(self, username: str, peer_ip: str) -> None:
        with self._fail_lock:
            for key in self._failure_keys(username, peer_ip):
                self._failures.pop(key, None)

    def login(self, username: str, password: str, *, peer_ip: str = "") -> SessionRecord:
        if not self.configured():
            raise AuthError("operator authentication is not configured", status=503)
        if self.login_rate_limited(username, peer_ip):
            self._audit(
                "auth.login_rate_limited",
                "denied",
                summary="Login rate limit reached",
                detail={"peer": peer_ip},
                severity="medium",
            )
            raise AuthError("Too many failed sign-in attempts. Try again later.", status=429)
        record = self.store.by_username(username or "")
        stored_hash = record.password_hash if record is not None else DUMMY_PASSWORD_HASH
        password_ok = verify_password(password or "", stored_hash)
        ok = record is not None and not record.disabled and password_ok
        if not ok:
            self._register_failure(username or "", peer_ip)
            self._audit(
                "auth.login_failed",
                "failed",
                summary="Failed console sign-in",
                detail={"peer": peer_ip},
                severity="medium",
            )
            raise AuthError(GENERIC_LOGIN_ERROR, status=401)
        assert record is not None
        self._clear_failures(username, peer_ip)
        session = self._new_session(record)
        self._audit(
            "auth.login_succeeded",
            "success",
            actor=record.username,
            summary=f"Operator {record.username} signed in",
            detail={"peer": peer_ip, "role": record.role},
        )
        return session

    def _new_session(self, record: OperatorRecord) -> SessionRecord:
        now = self._clock()
        session = SessionRecord(
            session_id=secrets.token_urlsafe(32),
            operator_id=record.operator_id,
            username=record.username,
            role=record.role,
            csrf_token=secrets.token_urlsafe(32),
            created_at=now,
            last_seen=now,
            expires_at=now + self.idle_seconds,
            absolute_expires_at=now + self.absolute_seconds,
        )
        with self.store._lock:
            self.store.sessions[session.session_id] = session
            self.store.save_sessions()
        return session

    def validate_session(self, session_id: str | None) -> SessionRecord | None:
        if not session_id or not isinstance(session_id, str):
            return None
        with self.store._lock:
            session = self.store.sessions.get(session_id)
            if session is None:
                return None
            now = self._clock()
            if now >= session.expires_at or now >= session.absolute_expires_at:
                self.store.sessions.pop(session_id, None)
                self.store.save_sessions()
                self._audit(
                    "auth.session_expired",
                    "expired",
                    actor=session.username,
                    summary=f"Session expired for {session.username}",
                )
                return None
            operator = self.store.operators.get(session.operator_id)
            if operator is None or operator.disabled:
                self.store.sessions.pop(session_id, None)
                self.store.save_sessions()
                return None
            session.username = operator.username
            session.role = operator.role
            session.last_seen = now
            session.expires_at = min(now + self.idle_seconds, session.absolute_expires_at)
            self.store.save_sessions()
            return session

    def logout(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self.store._lock:
            session = self.store.sessions.pop(session_id, None)
            self.store.save_sessions()
        if session is not None:
            self._audit(
                "auth.logout",
                "success",
                actor=session.username,
                summary=f"Operator {session.username} signed out",
            )

    def rotate_session(self, session_id: str | None) -> SessionRecord:
        """Replace the session id and CSRF token; invalidate the previous cookie value."""
        current = self.validate_session(session_id)
        if current is None:
            raise AuthError("authentication required", status=401)
        with self.store._lock:
            self.store.sessions.pop(current.session_id, None)
            operator = self.store.operators.get(current.operator_id)
            if operator is None or operator.disabled:
                self.store.save_sessions()
                raise AuthError("authentication required", status=401)
            replacement = SessionRecord(
                session_id=secrets.token_urlsafe(32),
                operator_id=operator.operator_id,
                username=operator.username,
                role=operator.role,
                csrf_token=secrets.token_urlsafe(32),
                created_at=current.created_at,
                last_seen=self._clock(),
                expires_at=min(self._clock() + self.idle_seconds, current.absolute_expires_at),
                absolute_expires_at=current.absolute_expires_at,
            )
            self.store.sessions[replacement.session_id] = replacement
            self.store.save_sessions()
        self._audit(
            "auth.session_rotated",
            "rotated",
            actor=replacement.username,
            summary=f"Session rotated for {replacement.username}",
        )
        return replacement

    def _revoke_operator_sessions(self, operator_id: str) -> None:
        removed = [
            sid for sid, sess in self.store.sessions.items() if sess.operator_id == operator_id
        ]
        for sid in removed:
            self.store.sessions.pop(sid, None)
        if removed:
            self.store.save_sessions()
            self._audit(
                "auth.session_revoked",
                "revoked",
                summary="Sessions revoked after account change",
                detail={"operator_id": operator_id, "count": len(removed)},
            )

    def has_permission(self, session: SessionRecord, permission: Permission | str) -> bool:
        try:
            perm = permission if isinstance(permission, Permission) else Permission(permission)
        except ValueError:
            return False
        try:
            return perm in permissions_for(session.role)
        except ValueError:
            return False

    def public_status(self, session: SessionRecord | None) -> dict[str, Any]:
        return {
            "configured": self.configured(),
            "authenticated": session is not None,
            "username": session.username if session else None,
            "role": session.role if session else None,
            "operator_id": session.operator_id if session else None,
            "csrf_token": session.csrf_token if session else None,
            "permissions": sorted(p.value for p in permissions_for(session.role)) if session else [],
            "cookie_name": COOKIE_NAME,
            "setup": (
                ""
                if self.configured()
                else "No operators are provisioned. Create the first administrator with scripts/provision_console_operator.py."
            ),
        }
