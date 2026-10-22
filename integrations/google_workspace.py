"""Read-only Google Workspace skeleton for Gmail, Drive, Calendar, and Docs.

Official delegated scopes only. No client secret, no Gmail send, and no write
scope. Without GOOGLE_CLIENT_ID the status is NOT CONFIGURED. A mock transport
cannot mark the connector connected.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .catalog import Catalog, ConnectorSpec, Effect, OperationSpec
from .errors import AuthenticationError, InvalidRequest, NotFound, PermissionDenied, RateLimited, TransientError

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"
CALENDAR_READONLY = "https://www.googleapis.com/auth/calendar.readonly"
DOCS_READONLY = "https://www.googleapis.com/auth/documents.readonly"
READ_SCOPES = (GMAIL_READONLY, DRIVE_READONLY, CALENDAR_READONLY, DOCS_READONLY)
FORBIDDEN_SCOPES = frozenset({
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/documents",
})
GMAIL_ROOT = "https://gmail.googleapis.com/gmail/v1"
DRIVE_ROOT = "https://www.googleapis.com/drive/v3"
CALENDAR_ROOT = "https://www.googleapis.com/calendar/v3"
DOCS_ROOT = "https://docs.googleapis.com/v1"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
_CLIENT_RE = re.compile(r"[A-Za-z0-9_-]{6,80}\.apps\.googleusercontent\.com\Z")
_DOC_ID = re.compile(r"[A-Za-z0-9_-]{8,128}\Z")
_ALLOWED_HOSTS = frozenset({
    "accounts.google.com",
    "oauth2.googleapis.com",
    "gmail.googleapis.com",
    "www.googleapis.com",
    "docs.googleapis.com",
})
_QUERY = {"type": "object", "additionalProperties": False, "properties": {}}
_DOC_QUERY = {
    "type": "object",
    "additionalProperties": False,
    "required": ["document_id"],
    "properties": {"document_id": {"type": "string", "minLength": 8, "maxLength": 128}},
}
_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "items"],
    "properties": {
        "status": {"type": "string"},
        "detail": {"type": "string", "maxLength": 300},
        "items": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "name"],
                "properties": {
                    "id": {"type": "string", "maxLength": 200},
                    "name": {"type": "string", "maxLength": 300},
                },
            },
        },
    },
}


def _op(name: str, summary: str, scopes: tuple[str, ...], schema: dict[str, Any] | None = None) -> OperationSpec:
    return OperationSpec(
        name=name,
        summary=summary,
        effect=Effect.READ,
        scope="google:read",
        input_schema=schema or _QUERY,
        output_schema=_RESULT,
        provider_permissions=scopes,
        tool_name="google_" + name,
        requires_approval=False,
        idempotent=True,
        evidence="mock-tested",
    )


GOOGLE_WORKSPACE = ConnectorSpec(
    connector_id="google_workspace",
    version="0.1.0",
    service="Google Workspace",
    summary="Read-only Gmail, Drive, Calendar, and Docs. Not connected until a live read.",
    auth="oauth_delegated",
    operations=(
        _op("list_gmail", "List recent Gmail message ids the account can read.", (GMAIL_READONLY,)),
        _op("list_drive", "List Drive files the account can read.", (DRIVE_READONLY,)),
        _op("list_calendar", "List events on the primary calendar.", (CALENDAR_READONLY,)),
        _op(
            "list_docs",
            "List Google Docs the account can read. The list uses Drive and the Docs read scope.",
            (DOCS_READONLY, DRIVE_READONLY),
        ),
        _op("read_doc", "Read the title of one Google Doc.", (DOCS_READONLY,), _DOC_QUERY),
    ),
)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def validate_client_id(value: str) -> str:
    client_id = value.strip()
    if not _CLIENT_RE.fullmatch(client_id):
        raise InvalidRequest("Google client id must be an OAuth client id ending in .apps.googleusercontent.com")
    return client_id


def validate_redirect(value: str) -> str:
    parts = urllib.parse.urlsplit(value.strip())
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "http"
        or host not in {"127.0.0.1", "localhost"}
        or not parts.port
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path != "/api/google/callback"
    ):
        raise InvalidRequest(
            "Google redirect URI must be http://127.0.0.1 or http://localhost "
            "with a port and the path /api/google/callback"
        )
    return value.strip()


def google_configuration(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """A client id does not connect Google. The id itself is never returned."""
    source = env or {}
    present = bool(str(source.get("GOOGLE_CLIENT_ID", "")).strip())
    return {
        "status": "NOT CONFIGURED",
        "client_id": "present" if present else "absent",
        "connected": False,
    }


def _clip(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else ""
    return text.replace("\r", " ").replace("\n", " ")[:limit]


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_at: float
    account: str
    scope: str


class GoogleWorkspace:
    def __init__(
        self,
        *,
        client_id: str = "",
        redirect_uri: str = "http://127.0.0.1:18080/api/google/callback",
        clock: Callable[[], float] = time.time,
        transport: Callable[[str, str, dict[str, str], bytes | None], tuple[int, dict[str, Any]]] | None = None,
    ) -> None:
        self.client_id = client_id.strip()
        self.redirect_uri = redirect_uri.strip()
        self._clock = clock
        self._live_transport = transport is None
        self._transport = transport or _https_transport
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[str, float]] = {}
        self.bundle: TokenBundle | None = None
        self.calls = 0
        self.live_read = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "GoogleWorkspace":
        source = os.environ if environ is None else environ
        return cls(client_id=str(source.get("GOOGLE_CLIENT_ID", "")))

    def configured(self) -> bool:
        if not self.client_id:
            return False
        try:
            validate_client_id(self.client_id)
        except InvalidRequest:
            return False
        return True

    def public_status(self) -> dict[str, Any]:
        connected = bool(self.live_read and self.bundle is not None and self._live_transport)
        return {
            "configured": self.configured(),
            "connected": connected,
            "status": "read" if connected else "NOT CONFIGURED",
            "account": self.bundle.account if connected and self.bundle is not None else None,
            "scopes": list(READ_SCOPES) if self.configured() else [],
            "setup": "" if self.configured() else (
                "Google Workspace is NOT CONFIGURED. Set GOOGLE_CLIENT_ID. No account is connected."
            ),
        }

    def apply(self, catalog: Catalog, tenant_id: str) -> None:
        """Keep the catalog row disconnected. A client id is not a live Google read."""
        record = catalog.connection(tenant_id, GOOGLE_WORKSPACE.connector_id)
        record.connected = False
        record.account = None
        record.granted_scopes = frozenset()
        record.detail = "Google Workspace is NOT CONFIGURED. No account is connected."

    def authorization_url(self) -> str:
        if not self.configured():
            raise AuthenticationError(self.public_status()["setup"])
        client_id = validate_client_id(self.client_id)
        redirect = validate_redirect(self.redirect_uri)
        if any(scope in FORBIDDEN_SCOPES for scope in READ_SCOPES):
            raise PermissionDenied("Google sign-in cannot request a write scope.")
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        now = self._clock()
        with self._lock:
            expired = [key for key, item in self._pending.items() if now > item[1]]
            for key in expired:
                self._pending.pop(key, None)
            self._pending[state] = (verifier, now + 600)
        query = urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect,
            "scope": " ".join(READ_SCOPES),
            "state": state,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "select_account",
        })
        return AUTH_URL + "?" + query

    def complete(self, code: str, state: str) -> None:
        with self._lock:
            pending = self._pending.pop(state, None)
        if pending is None or self._clock() > pending[1]:
            raise AuthenticationError("Google sign-in state is missing or expired")
        if not code or len(code) > 2048:
            raise AuthenticationError("Google did not return a usable sign-in code")
        token = self._token({
            "client_id": validate_client_id(self.client_id),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": validate_redirect(self.redirect_uri),
            "code_verifier": pending[0],
        })
        scope = str(token.get("scope") or " ".join(READ_SCOPES))
        self.bundle = TokenBundle(
            access_token=str(token["access_token"]),
            refresh_token=str(token.get("refresh_token") or ""),
            expires_at=self._clock() + int(token.get("expires_in", 3600)) - 60,
            account="",
            scope=scope,
        )
        if GMAIL_READONLY in scope.split():
            profile = self._get(
                GMAIL_ROOT + "/users/me/profile",
                (GMAIL_READONLY,),
            )
            address = profile.get("emailAddress")
            if isinstance(address, str) and "@" in address:
                self.bundle.account = address[:200]
        self.live_read = False

    def perform(self, operation: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(params or {})
        if operation == "list_gmail":
            return self.list_gmail()
        if operation == "list_drive":
            return self.list_drive()
        if operation == "list_calendar":
            return self.list_calendar()
        if operation == "list_docs":
            return self.list_docs()
        if operation == "read_doc":
            return self.read_doc(str(payload.get("document_id", "")))
        raise PermissionDenied(f"Google Workspace {operation} is not enabled. No request was sent.")

    def list_gmail(self) -> dict[str, Any]:
        payload = self._get(
            GMAIL_ROOT + "/users/me/messages?maxResults=5",
            (GMAIL_READONLY,),
        )
        raw = payload.get("messages", [])
        if not isinstance(raw, list):
            raise InvalidRequest("Gmail did not return a message list.")
        items = []
        for row in raw:
            if isinstance(row, dict) and row.get("id"):
                message_id = _clip(row.get("id"), 180)
                items.append({"id": message_id, "name": message_id})
            if len(items) >= 5:
                break
        result: dict[str, Any] = {"status": "ok", "items": items}
        if not items:
            result["detail"] = "No Gmail messages were returned."
        return result

    def list_drive(self) -> dict[str, Any]:
        payload = self._get(
            DRIVE_ROOT + "/files?pageSize=5&fields=files(id,name)",
            (DRIVE_READONLY,),
        )
        return self._named_files(payload, "No Drive files were returned.")

    def list_calendar(self) -> dict[str, Any]:
        payload = self._get(
            CALENDAR_ROOT + "/calendars/primary/events?maxResults=5&singleEvents=true",
            (CALENDAR_READONLY,),
        )
        raw = payload.get("items", [])
        if not isinstance(raw, list):
            raise InvalidRequest("Calendar did not return an event list.")
        items = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            items.append({
                "id": _clip(row.get("id"), 180),
                "name": _clip(row.get("summary"), 300) or "(no title)",
            })
            if len(items) >= 5:
                break
        result: dict[str, Any] = {"status": "ok", "items": items}
        if not items:
            result["detail"] = "No calendar events were returned."
        return result

    def list_docs(self) -> dict[str, Any]:
        query = urllib.parse.urlencode({
            "pageSize": "5",
            "fields": "files(id,name)",
            "q": "mimeType='application/vnd.google-apps.document'",
        })
        payload = self._get(DRIVE_ROOT + "/files?" + query, (DOCS_READONLY, DRIVE_READONLY))
        return self._named_files(payload, "No Google Docs were returned.")

    def read_doc(self, document_id: str) -> dict[str, Any]:
        if not _DOC_ID.fullmatch(document_id):
            raise InvalidRequest("document id is not usable")
        quoted = urllib.parse.quote(document_id, safe="")
        payload = self._get(
            DOCS_ROOT + "/documents/" + quoted + "?fields=documentId,title",
            (DOCS_READONLY,),
        )
        return {
            "status": "ok",
            "items": [{
                "id": _clip(payload.get("documentId") or document_id, 180),
                "name": _clip(payload.get("title"), 300) or "(untitled)",
            }],
        }

    def _named_files(self, payload: dict[str, Any], empty: str) -> dict[str, Any]:
        raw = payload.get("files", [])
        if not isinstance(raw, list):
            raise InvalidRequest("Drive did not return a file list.")
        items = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            items.append({
                "id": _clip(row.get("id"), 180),
                "name": _clip(row.get("name"), 300) or "(unnamed)",
            })
            if len(items) >= 5:
                break
        result: dict[str, Any] = {"status": "ok", "items": items}
        if not items:
            result["detail"] = empty
        return result

    def _granted(self) -> set[str]:
        if self.bundle is None:
            return set()
        return set(self.bundle.scope.split())

    def _get(self, url: str, required: tuple[str, ...]) -> dict[str, Any]:
        if not self.configured():
            raise AuthenticationError("Google Workspace is NOT CONFIGURED. No request was sent.")
        if self.bundle is None:
            raise AuthenticationError("Google Workspace is not connected. No request was sent.")
        granted = self._granted()
        for scope in required:
            if scope in FORBIDDEN_SCOPES or scope not in READ_SCOPES:
                raise PermissionDenied(f"{scope} is not a read-only scope. No Google request was sent.")
            if scope not in granted:
                raise PermissionDenied(f"{scope} is not granted. No Google request was sent.")
        self.calls += 1
        status, payload = self._transport("GET", url, {
            "Authorization": f"Bearer {self.bundle.access_token}",
            "Accept": "application/json",
        }, None)
        if status == 200 and isinstance(payload, dict):
            if self._live_transport:
                self.live_read = True
            return payload
        if status == 401:
            raise AuthenticationError("Google rejected the saved sign-in. No Google data was returned.")
        if status == 403:
            raise PermissionDenied("Google refused this read. No Google data was returned.")
        if status == 404:
            raise NotFound("Google did not find that item.")
        if status == 429:
            raise RateLimited("Google is throttling this read.")
        if status >= 500:
            raise TransientError("Google did not return the data.")
        raise AuthenticationError("Google did not return the data.")

    def _token(self, fields: dict[str, str]) -> dict[str, Any]:
        if "client_secret" in fields or "client_assertion" in fields:
            raise AuthenticationError("This Google sign-in does not use a client secret.")
        body = urllib.parse.urlencode(fields).encode("utf-8")
        status, payload = self._transport(
            "POST",
            TOKEN_URL,
            {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            body,
        )
        if status != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
            raise AuthenticationError("Google did not issue an access token.")
        granted = set(str(payload.get("scope") or "").split())
        if granted & FORBIDDEN_SCOPES:
            raise PermissionDenied("Google returned a write scope. The token was not stored.")
        return payload

    def __repr__(self) -> str:
        return (
            f"GoogleWorkspace(configured={self.configured()}, "
            f"connected={self.public_status()['connected']})"
        )


def _https_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None,
) -> tuple[int, dict[str, Any]]:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in _ALLOWED_HOSTS:
        raise AuthenticationError("Google requests are limited to the official hosts.")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=20) as response:
            raw = response.read(1_000_000)
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read(1_000_000)
        status = int(exc.code)
    except OSError as exc:
        raise TransientError("Google could not be reached.") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}
    return status, payload if isinstance(payload, dict) else {}
