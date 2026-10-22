"""Microsoft sign-in for the local console.

This is the authorization-code flow with PKCE against Microsoft Entra ID.
The browser is sent to Microsoft and comes back with a one-time code. The
code is exchanged on the server. Access and refresh tokens stay in a local
file and are never returned to the page.

No application id is built in. Until MICROSOFT_CLIENT_ID is set, sign-in
refuses to start.
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
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .errors import (
    AuthenticationError,
    Conflict,
    InvalidRequest,
    NotFound,
    PermissionDenied,
    RateLimited,
    TransientError,
)
from .state_guard import StatePermissionError, assert_private, restrict_private

AZURE_SCOPE = "https://management.azure.com/user_impersonation"
# Initial sign-in is User.Read plus Mail.Read. Chat, file reads, SharePoint, and
# Azure inventory stay in the catalog but are not requested until those
# permissions are approved. Mail.ReadWrite is requested only for an unsent
# draft or draft update. Files.ReadWrite is requested only for upload, update,
# or delete of one file the operator named. Mail.Send is never requested.
READ_SCOPES = (
    "openid",
    "profile",
    "email",
    "offline_access",
    "User.Read",
    "Mail.Read",
)
DRAFT_SCOPES = READ_SCOPES + ("Mail.ReadWrite",)
FILE_SCOPES = READ_SCOPES + ("Files.ReadWrite",)
# Kept for older imports and status rows. Prefer READ_SCOPES / DRAFT_SCOPES.
SCOPES = READ_SCOPES
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
ARM_ROOT = "https://management.azure.com"
# login.microsoftonline.com/common is never used. A directory id keeps its own
# organisation button and also offers a personal button on /consumers/.
DEFAULT_TENANT = "d595636e-9ef4-4890-b8a7-bde8dd5cab03"
PERMISSIONS_NOTE = (
    "Sign-in identifies the account and requests delegated User.Read and Mail.Read. "
    "The organisation button uses this directory. A personal Microsoft account, "
    "including one that uses a Gmail address, uses the personal button and the consumers endpoint. "
    "Teams, OneDrive reads, SharePoint, and Azure inventory are not requested. "
    "Creating or updating an unsent mail draft needs a second consent for Mail.ReadWrite. "
    "Uploading, updating, or deleting one named file needs Files.ReadWrite and that path. "
    "Mail.Send is not requested. Sending mail stays off."
)
_READ_ACCESS = {"", "read", "readonly", "read-only"}
_DRAFT_ACCESS = {"draft", "mail_draft", "mail-draft", "mail_update", "mail-update"}
_FILE_ACCESS = {"file", "files", "file_write", "files-write", "file-write"}
_DRIVE_ROOTS = {
    "",
    "/",
    "\\",
    ".",
    "..",
    "root",
    "root:",
    "/root",
    "me/drive/root",
    "/me/drive/root",
    "me/drive/root:",
    "/me/drive/root:",
    "drive/root",
    "/drive/root",
}
# `organizations` and `consumers` are offered only when MICROSOFT_TENANT names them.
# A directory id keeps the organisation button and adds the personal button.
# `common` is never selected.
SIGN_IN_ACCOUNTS = (
    (
        "work",
        "organizations",
        "Sign in with a work or school account",
        "Only accounts in an organisational directory. A personal Microsoft account is not offered.",
    ),
    (
        "personal",
        "consumers",
        "Sign in with a personal Microsoft account",
        "Only a personal account, such as Outlook, Hotmail, Live, or a Gmail address that is a personal Microsoft account. This uses the consumers endpoint.",
    ),
)
_DIRECTORY_ID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
_TENANT_RE = re.compile(
    r"(?:organizations|consumers|"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+)\Z"
)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def validate_client_id(value: str) -> str:
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError) as exc:
        raise InvalidRequest("Microsoft client id must be the application id from Entra") from exc


def validate_tenant(value: str) -> str:
    tenant = value.strip()
    if tenant.casefold() == "common":
        raise InvalidRequest(
            "Microsoft tenant common is not used. This app is single-tenant "
            "for directory d595636e-9ef4-4890-b8a7-bde8dd5cab03."
        )
    if not _TENANT_RE.fullmatch(tenant):
        raise InvalidRequest(
            "Microsoft tenant must be organizations, consumers, a directory id, or a domain"
        )
    return tenant


def resolve_tenant(value: str | None) -> str:
    """Empty and `common` both mean the single-tenant directory. `common` is not sent."""
    tenant = (value or "").strip()
    if not tenant or tenant.casefold() == "common":
        return DEFAULT_TENANT
    return validate_tenant(tenant)


def validate_redirect(value: str) -> str:
    """Loopback only. Microsoft matches localhost ports loosely; 127.0.0.1 must be exact.

    A public redirect is rejected. The saved Entra platform for this URI is
    Mobile and desktop applications.
    """
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
        or parts.path != "/api/microsoft/callback"
    ):
        raise InvalidRequest(
            "Microsoft redirect URI must be http://127.0.0.1 or http://localhost "
            "with a port and the path /api/microsoft/callback"
        )
    return value.strip()


def validate_drive_path(value: str) -> str:
    """One named file. Empty paths and the drive root are refused."""
    if not isinstance(value, str):
        raise InvalidRequest("file path is empty or names the drive root")
    raw = value.strip()
    if raw.casefold() in {item.casefold() for item in _DRIVE_ROOTS}:
        raise InvalidRequest("file path is empty or names the drive root")
    normalized = raw.replace("\\", "/").strip("/")
    if not normalized or normalized.casefold() in {
        "root", ".", "..", "me/drive/root", "drive/root",
    }:
        raise InvalidRequest("file path is empty or names the drive root")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise InvalidRequest("file path is not usable")
    if any(any(ord(ch) < 32 or ch in ':*?"<>|' for ch in part) for part in parts):
        raise InvalidRequest("file path is not usable")
    if len(normalized) > 400 or len(parts) > 20:
        raise InvalidRequest("file path is not usable")
    return normalized


def _named_file_access(access: str) -> tuple[str, str | None]:
    text = (access or "read").strip()
    lowered = text.casefold()
    for prefix in ("files:", "file:"):
        if lowered.startswith(prefix):
            return "files", text[len(prefix):]
    return lowered, None


def scope_names(scope: str) -> set[str]:
    names: set[str] = set()
    for part in scope.split():
        names.add(part.rsplit("/", 1)[-1].casefold())
    return names


def assert_safe_config_path(value: Path, *, label: str) -> Path:
    """Keep Microsoft config off the source tree and the shared volume."""
    if not value.is_absolute():
        raise InvalidRequest(f"Microsoft {label} must be an absolute path")
    resolved = value.resolve()
    repo = Path(__file__).resolve().parents[1]
    forbidden = [repo]
    if os.name == "posix":
        forbidden.append(Path("/workspace"))
    for root in forbidden:
        if resolved == root or root in resolved.parents:
            raise InvalidRequest(f"Microsoft {label} must stay off the source tree and the shared volume")
    return resolved


def assert_safe_token_path(value: Path) -> Path:
    """Tokens stay in a private file, never in git and never on the shared volume."""
    return assert_safe_config_path(value, label="token file")


def load_client_id(environ: dict[str, str] | None = None) -> str:
    """Read the Entra application id from the environment or a private file.

    The value is configuration, not a password. It is still kept out of Git and
    out of the shared volume. The file contents are never logged here.
    """
    source = os.environ if environ is None else environ
    direct = source.get("MICROSOFT_CLIENT_ID", "").strip()
    if direct:
        return validate_client_id(direct)
    raw_path = source.get("MICROSOFT_CLIENT_ID_FILE", "").strip()
    if not raw_path:
        return ""
    path = assert_safe_config_path(Path(raw_path), label="client id file")
    if path.is_symlink():
        raise InvalidRequest("Microsoft client id file must not be a symbolic link")
    if not path.is_file():
        return ""
    try:
        assert_private(path)
    except StatePermissionError as exc:
        raise InvalidRequest("Microsoft client id file is not private") from exc
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise InvalidRequest("Microsoft client id file could not be read") from exc
    if not text:
        return ""
    return validate_client_id(text.splitlines()[0].strip())


def client_id_source(environ: dict[str, str] | None = None) -> str:
    """Name the variable that supplies the application id, or return "".

    An unsafe, non-private, or invalid id file counts as not configured.
    """
    source = os.environ if environ is None else environ
    if str(source.get("MICROSOFT_CLIENT_ID", "")).strip():
        return "MICROSOFT_CLIENT_ID"
    if not str(source.get("MICROSOFT_CLIENT_ID_FILE", "")).strip():
        return ""
    try:
        return "MICROSOFT_CLIENT_ID_FILE" if load_client_id(dict(source)) else ""
    except InvalidRequest:
        return ""


def scopes_for(access: str = "read", *, target: str | None = None) -> tuple[str, ...]:
    """Delegated scopes only. Writes are requested for one named flow."""
    choice, embedded = _named_file_access(access)
    if choice in _READ_ACCESS:
        return READ_SCOPES
    if choice in _DRAFT_ACCESS:
        return DRAFT_SCOPES
    if choice in _FILE_ACCESS:
        named = target if target is not None else embedded
        if embedded is not None and target is not None:
            if validate_drive_path(embedded) != validate_drive_path(target):
                raise InvalidRequest("Name one file before requesting Files.ReadWrite.")
        if named is None or not str(named).strip():
            raise InvalidRequest("Name the file before requesting Files.ReadWrite.")
        validate_drive_path(str(named))
        return FILE_SCOPES
    raise InvalidRequest("Microsoft sign-in access must be read, draft, or a named file")


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_at: float
    account: str
    scope: str
    authority: str = ""

    def public(self) -> dict[str, Any]:
        return {"account": self.account, "scope": self.scope, "connected": True}


class MicrosoftOAuth:
    def __init__(
        self,
        *,
        client_id: str = "",
        tenant: str = "",
        redirect_uri: str = "http://127.0.0.1:18080/api/microsoft/callback",
        token_file: Path | None = None,
        clock: Callable[[], float] = time.time,
        transport: Callable[[str, str, dict[str, str], bytes | None], tuple[int, dict[str, Any]]] | None = None,
    ) -> None:
        self.client_id = client_id.strip()
        self.tenant = resolve_tenant(tenant)
        self.redirect_uri = redirect_uri.strip()
        self.token_file = assert_safe_token_path(token_file) if token_file is not None else None
        self._clock = clock
        self._live_transport = transport is None
        self._transport = transport or _https_transport
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[str, float, str]] = {}
        self.bundle: TokenBundle | None = None
        self.graph_calls = 0
        self.live_mail = False
        if self.token_file is not None and self.token_file.is_file():
            self._load()

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "MicrosoftOAuth":
        source = os.environ if environ is None else environ
        path = source.get("MICROSOFT_TOKEN_FILE", "").strip()
        if not path and os.name == "posix":
            path = "/tmp/microsoft-365-token.json"
        return cls(
            client_id=load_client_id(dict(source)),
            tenant=source.get("MICROSOFT_TENANT", ""),
            redirect_uri=source.get(
                "MICROSOFT_REDIRECT_URI", "http://127.0.0.1:18080/api/microsoft/callback"
            ),
            token_file=Path(path) if path else None,
        )

    def configured(self) -> bool:
        return bool(self.client_id)

    def account_choices(self) -> list[dict[str, str]]:
        """Sign-in options the page may offer.

        A directory id keeps the organisation button on that directory and adds
        the personal button on the consumers endpoint. A domain is not widened.
        `common` is never offered.
        """
        if self.tenant == "organizations":
            rows = (SIGN_IN_ACCOUNTS[0],)
        elif self.tenant == "consumers":
            rows = (SIGN_IN_ACCOUNTS[1],)
        elif _DIRECTORY_ID_RE.fullmatch(self.tenant):
            rows = (
                (
                    "directory",
                    self.tenant,
                    "Sign in with your organisation",
                    "Use the work account in this directory.",
                ),
                SIGN_IN_ACCOUNTS[1],
            )
        else:
            rows = ((
                "directory",
                self.tenant,
                "Sign in with your organisation",
                "Use the work account in this directory.",
            ),)
        return [
            {"id": key, "label": label, "detail": detail, "tenant": tenant}
            for key, tenant, label, detail in rows
        ]

    def tenant_for_account(self, account: str | None) -> str:
        choice = (account or "").strip().lower()
        choices = {item["id"]: item["tenant"] for item in self.account_choices()}
        if choice in {"", "any", "directory"} and "directory" in choices:
            return choices["directory"]
        if choice in {"", "any", "directory"} and len(choices) == 1:
            return next(iter(choices.values()))
        if choice not in choices:
            raise InvalidRequest(
                "Choose the organisation directory or a personal Microsoft account. "
                "The common directory is not used."
            )
        return choices[choice]

    def public_status(self) -> dict[str, Any]:
        account = self.bundle.account if self.bundle is not None else None
        if not self.configured():
            status = "unconfigured"
        elif self.bundle is not None:
            status = "connected"
        else:
            status = "disconnected"
        return {
            "configured": self.configured(),
            "connected": self.bundle is not None,
            "status": status,
            "account": account,
            "mail_read": self.has_mail_read(),
            "mail_write": self.has_graph_scope("Mail.ReadWrite"),
            "chat_read": self.has_graph_scope("Chat.Read"),
            "files_read": self.has_graph_scope("Files.Read"),
            "files_write": self.has_graph_scope("Files.ReadWrite"),
            "sites_read": self.has_graph_scope("Sites.Read.All"),
            "azure_read": self.has_azure_read(),
            "accounts": self.account_choices(),
            "permissions": PERMISSIONS_NOTE,
            "directory": self.tenant,
            "mailbox": "read" if self.live_mail else "NOT CONFIGURED",
            "redirect_uri": self.redirect_uri if self.configured() else None,
            "provider_scopes": list(READ_SCOPES) if self.configured() else [],
            "draft_scopes": list(DRAFT_SCOPES) if self.configured() else [],
            "file_scopes": list(FILE_SCOPES) if self.configured() else [],
            "setup": "" if self.configured() else (
                "Sign-in needs the Entra application id in MICROSOFT_CLIENT_ID "
                "or MICROSOFT_CLIENT_ID_FILE. The buttons stay unavailable until that "
                "id is set. No account is connected."
            ),
        }

    def authorization_url(
        self,
        account: str | None = None,
        *,
        access: str = "read",
        target: str | None = None,
    ) -> str:
        if not self.configured():
            raise AuthenticationError(self.public_status()["setup"])
        client_id = validate_client_id(self.client_id)
        redirect = validate_redirect(self.redirect_uri)
        tenant = validate_tenant(self.tenant_for_account(account))
        scopes = scopes_for(access, target=target)
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        now = self._clock()
        with self._lock:
            expired = [key for key, item in self._pending.items() if now > item[1]]
            for key in expired:
                self._pending.pop(key, None)
            if len(self._pending) >= 32:
                raise AuthenticationError("Too many unfinished Microsoft sign-in attempts. Wait and try again.")
            self._pending[state] = (verifier, now + 600, tenant)
        query = urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect,
            "response_mode": "query",
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        })
        return (
            "https://login.microsoftonline.com/"
            + urllib.parse.quote(tenant, safe="")
            + "/oauth2/v2.0/authorize?"
            + query
        )

    def delegated_scopes(self) -> set[str]:
        if self.bundle is None:
            return set()
        return scope_names(self.bundle.scope)

    def has_mail_read(self) -> bool:
        return self.has_graph_scope("Mail.Read")

    def has_graph_scope(self, name: str) -> bool:
        return name.rsplit("/", 1)[-1].casefold() in self.delegated_scopes()

    def has_azure_read(self) -> bool:
        scopes = self.delegated_scopes()
        return "user_impersonation" in scopes or AZURE_SCOPE.casefold() in scopes

    def complete(self, code: str, state: str) -> TokenBundle:
        with self._lock:
            pending = self._pending.pop(state, None)
        if pending is None or self._clock() > pending[1]:
            raise AuthenticationError("Microsoft sign-in state is missing or expired")
        if not code or len(code) > 2048:
            raise AuthenticationError("Microsoft did not return a usable sign-in code")
        authority = validate_tenant(pending[2])
        token = self._token({
            "client_id": validate_client_id(self.client_id),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": validate_redirect(self.redirect_uri),
            "code_verifier": pending[0],
        }, tenant=authority)
        account = self._account(token["access_token"])
        self.bundle = TokenBundle(
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token", ""),
            expires_at=self._clock() + int(token.get("expires_in", 3600)) - 60,
            account=account,
            scope=str(token.get("scope", "")),
            authority=authority,
        )
        self._save()
        return self.bundle

    def access_token(self) -> str:
        if self.bundle is None:
            raise AuthenticationError("Microsoft 365 is not connected. No request was sent.")
        if self._clock() >= self.bundle.expires_at:
            if not self.bundle.refresh_token:
                self.disconnect()
                raise AuthenticationError("Microsoft sign-in expired. Connect the account again.")
            refresh_scope = self.bundle.scope.strip() or " ".join(READ_SCOPES)
            refreshed = self._token({
                "client_id": validate_client_id(self.client_id),
                "grant_type": "refresh_token",
                "refresh_token": self.bundle.refresh_token,
                "scope": refresh_scope,
            }, tenant=self.bundle.authority or self.tenant)
            self.bundle.access_token = refreshed["access_token"]
            self.bundle.refresh_token = refreshed.get("refresh_token", self.bundle.refresh_token)
            self.bundle.expires_at = self._clock() + int(refreshed.get("expires_in", 3600)) - 60
            if isinstance(refreshed.get("scope"), str) and refreshed["scope"].strip():
                self.bundle.scope = refreshed["scope"]
            self._save()
        return self.bundle.access_token

    def graph_get(
        self,
        path: str,
        query: dict[str, str] | None = None,
        *,
        required_scope: str = "Mail.Read",
    ) -> dict[str, Any]:
        token = self.access_token()
        if not self.has_graph_scope(required_scope):
            raise PermissionDenied(
                f"{required_scope} is not granted. No Microsoft Graph request was sent."
            )
        url = GRAPH_ROOT + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        self.graph_calls += 1
        status, payload = self._transport("GET", url, {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "ConsistencyLevel": "eventual",
        }, None)
        if status == 200 and isinstance(payload, dict):
            bare = path.split("?", 1)[0]
            if self._live_transport and (bare == "/me/messages" or bare.startswith("/me/messages/")):
                self.live_mail = True
            return payload
        if status == 401:
            raise AuthenticationError(
                "Microsoft rejected the saved sign-in. Connect the account again. No Graph data was returned."
            )
        if status == 403:
            raise PermissionDenied(
                f"Microsoft refused this read. {required_scope} is missing. No Graph data was returned."
            )
        if status == 404:
            raise NotFound("Microsoft Graph did not find that item.")
        if status == 429:
            raise RateLimited("Microsoft Graph is throttling this read.")
        if status == 400:
            raise InvalidRequest("Microsoft Graph rejected the query.")
        if status >= 500:
            raise TransientError("Microsoft Graph did not return the data.")
        raise AuthenticationError("Microsoft Graph did not return the data.")

    def _refuse_mail_send(self, path: str, required_scope: str) -> None:
        if required_scope.casefold() == "mail.send":
            raise PermissionDenied("Mail.Send is not available. No Microsoft Graph request was sent.")
        lowered = path.split("?", 1)[0].casefold().rstrip("/")
        if lowered.endswith("/send") or lowered.endswith("/sendmail") or "/me/sendmail" in lowered:
            raise PermissionDenied("Mail.Send is not available. No Microsoft Graph request was sent.")

    def _require_scope(self, required_scope: str) -> str:
        if not self.has_graph_scope(required_scope):
            raise PermissionDenied(
                f"{required_scope} is not granted. No Microsoft Graph request was sent."
            )
        return self.access_token()

    def _write_result(
        self,
        status: int,
        payload: Any,
        *,
        required_scope: str,
        action: str,
        allow_empty: bool = False,
    ) -> dict[str, Any]:
        if status in {200, 201} and isinstance(payload, dict):
            return payload
        if allow_empty and status == 204:
            return {"status": "deleted"}
        if status == 401:
            raise AuthenticationError(
                "Microsoft rejected the saved sign-in. Connect the account again. No Graph data was returned."
            )
        if status == 403:
            raise PermissionDenied(
                f"Microsoft refused this {action}. {required_scope} is missing. No Graph data was returned."
            )
        if status == 404:
            raise NotFound("Microsoft Graph did not find that item.")
        if status == 409:
            raise Conflict("Microsoft Graph found a conflict. The file was not replaced.")
        if status == 429:
            raise RateLimited("Microsoft Graph is throttling this request.")
        if status == 400:
            raise InvalidRequest(f"Microsoft Graph rejected the {action}.")
        if status >= 500:
            raise TransientError(f"Microsoft Graph did not complete the {action}.")
        raise AuthenticationError(f"Microsoft Graph did not complete the {action}.")

    def graph_post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        required_scope: str,
    ) -> dict[str, Any]:
        """Create an unsent mail draft. Never used for Mail.Send or Azure writes."""
        self._refuse_mail_send(path, required_scope)
        if path.split("?", 1)[0].rstrip("/") != "/me/messages":
            raise PermissionDenied(
                "Only an unsent mail draft can be created. No Microsoft Graph request was sent."
            )
        token = self._require_scope(required_scope)
        payload_bytes = json.dumps(body).encode("utf-8")
        self.graph_calls += 1
        status, payload = self._transport(
            "POST",
            GRAPH_ROOT + path,
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            payload_bytes,
        )
        return self._write_result(status, payload, required_scope=required_scope, action="draft")

    def graph_patch(
        self,
        path: str,
        body: dict[str, Any],
        *,
        required_scope: str,
    ) -> dict[str, Any]:
        """Update an unsent draft. The path cannot be a send action."""
        self._refuse_mail_send(path, required_scope)
        bare = path.split("?", 1)[0].rstrip("/")
        if not bare.startswith("/me/messages/") or bare == "/me/messages":
            raise PermissionDenied(
                "Only an unsent mail draft can be updated. No Microsoft Graph request was sent."
            )
        token = self._require_scope(required_scope)
        payload_bytes = json.dumps(body).encode("utf-8")
        self.graph_calls += 1
        status, payload = self._transport(
            "PATCH",
            GRAPH_ROOT + path,
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            payload_bytes,
        )
        return self._write_result(status, payload, required_scope=required_scope, action="draft update")

    def graph_put(
        self,
        path: str,
        content: bytes,
        *,
        required_scope: str,
    ) -> dict[str, Any]:
        """Upload or replace one named drive file. Never a mail send."""
        self._refuse_mail_send(path, required_scope)
        if required_scope != "Files.ReadWrite":
            raise PermissionDenied(
                "Files.ReadWrite is required to upload a file. No Microsoft Graph request was sent."
            )
        bare = path.split("?", 1)[0]
        if not bare.startswith("/me/drive/root:/") or ":/content" not in bare:
            raise PermissionDenied(
                "Only a named drive file can be uploaded. No Microsoft Graph request was sent."
            )
        prefix = bare.split(":/content", 1)[0]
        if (
            bare.endswith("/me/drive/root:/content")
            or prefix.endswith("/me/drive/root:")
            or prefix.endswith("/me/drive/root:/")
            or "/me/drive/root:/" not in prefix
        ):
            raise InvalidRequest("file path is empty or names the drive root")
        if not isinstance(content, bytes) or not content:
            raise InvalidRequest("file content is empty")
        if len(content) > 4_000_000:
            raise InvalidRequest("file content is too large for a simple upload")
        token = self._require_scope(required_scope)
        self.graph_calls += 1
        status, payload = self._transport(
            "PUT",
            GRAPH_ROOT + path,
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/octet-stream",
            },
            content,
        )
        return self._write_result(status, payload, required_scope=required_scope, action="file upload")

    def graph_delete(self, path: str, *, required_scope: str) -> dict[str, Any]:
        """Delete one named drive file. Empty and root paths are refused."""
        self._refuse_mail_send(path, required_scope)
        if required_scope != "Files.ReadWrite":
            raise PermissionDenied(
                "Files.ReadWrite is required to delete a file. No Microsoft Graph request was sent."
            )
        bare = path.split("?", 1)[0].rstrip("/")
        if not bare.startswith("/me/drive/root:/"):
            raise PermissionDenied(
                "Only a named drive file can be deleted. No Microsoft Graph request was sent."
            )
        if bare in {"/me/drive/root:", "/me/drive/root"} or bare.endswith("/me/drive/root:"):
            raise InvalidRequest("file path is empty or names the drive root")
        token = self._require_scope(required_scope)
        self.graph_calls += 1
        status, payload = self._transport(
            "DELETE",
            GRAPH_ROOT + path,
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            None,
        )
        return self._write_result(
            status, payload, required_scope=required_scope, action="file delete", allow_empty=True,
        )

    def arm_get(self, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
        """Read-only Azure Resource Manager call. Never mutates Azure resources."""
        if not self.has_azure_read():
            raise PermissionDenied(
                "Azure inventory is NOT CONFIGURED. ARM user_impersonation was not granted. "
                "No Azure request was sent."
            )
        token = self.access_token()
        url = ARM_ROOT + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        self.graph_calls += 1
        status, payload = self._transport("GET", url, {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }, None)
        if status == 200 and isinstance(payload, dict):
            return payload
        if status == 401:
            raise AuthenticationError(
                "Azure rejected the saved sign-in. Connect the account again. No Azure data was returned."
            )
        if status == 403:
            raise PermissionDenied("Azure refused this inventory read. No Azure data was returned.")
        if status == 404:
            raise NotFound("Azure did not find that resource.")
        if status == 429:
            raise RateLimited("Azure is throttling inventory reads.")
        if status >= 500:
            raise TransientError("Azure did not return the inventory data.")
        raise AuthenticationError("Azure did not return the inventory data.")

    def disconnect(self) -> None:
        self.bundle = None
        self.live_mail = False
        if self.token_file is not None and self.token_file.exists():
            self.token_file.unlink()

    def _account(self, token: str) -> str:
        self.graph_calls += 1
        status, payload = self._transport(
            "GET", GRAPH_ROOT + "/me?$select=userPrincipalName,mail,displayName",
            {"Authorization": f"Bearer {token}", "Accept": "application/json"}, None,
        )
        if status != 200 or not isinstance(payload, dict):
            raise AuthenticationError("Microsoft did not confirm the signed-in account.")
        account = payload.get("mail") or payload.get("userPrincipalName") or ""
        if not isinstance(account, str) or "@" not in account:
            raise AuthenticationError("Microsoft did not return an account address.")
        return account[:200]

    def _token(self, fields: dict[str, str], *, tenant: str | None = None) -> dict[str, Any]:
        if "client_secret" in fields or "client_assertion" in fields:
            raise AuthenticationError("This sign-in flow does not use a client secret.")
        tenant = validate_tenant(tenant or self.tenant)
        body = urllib.parse.urlencode(fields).encode("utf-8")
        status, payload = self._transport(
            "POST",
            "https://login.microsoftonline.com/"
            + urllib.parse.quote(tenant, safe="")
            + "/oauth2/v2.0/token",
            {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            body,
        )
        error = payload.get("error") if isinstance(payload, dict) else ""
        if not isinstance(error, str):
            error = ""
        if (
            fields.get("grant_type") == "refresh_token"
            and error in {"invalid_grant", "interaction_required", "invalid_client"}
        ):
            self.disconnect()
            raise AuthenticationError(
                "Microsoft revoked the saved sign-in. Connect the account again. No mailbox data was returned."
            )
        if status >= 500 or status == 429:
            raise TransientError("Microsoft did not respond. The saved sign-in was kept.")
        if status != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
            raise AuthenticationError("Microsoft did not issue an access token.")
        return payload

    def _save(self) -> None:
        if self.token_file is None or self.bundle is None:
            return
        if self.token_file.is_symlink():
            raise AuthenticationError("Microsoft token file must be a regular file")
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.token_file.with_name(self.token_file.name + ".tmp")
        if temporary.is_symlink():
            raise AuthenticationError("Microsoft token file must be a regular file")
        payload = json.dumps({
            "access_token": self.bundle.access_token,
            "refresh_token": self.bundle.refresh_token,
            "expires_at": self.bundle.expires_at,
            "account": self.bundle.account,
            "scope": self.bundle.scope,
            "authority": self.bundle.authority,
        }, separators=(",", ":")).encode("utf-8")
        descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(descriptor, payload)
        finally:
            os.close(descriptor)
        if os.name == "posix":
            os.chmod(temporary, 0o600)
        os.replace(temporary, self.token_file)
        try:
            restrict_private(self.token_file)
        except StatePermissionError as exc:
            raise AuthenticationError("Microsoft token file permissions could not be enforced") from exc

    def _load(self) -> None:
        if self.token_file is None or not self.token_file.is_file() or self.token_file.is_symlink():
            return
        try:
            assert_private(self.token_file)
        except StatePermissionError:
            return
        try:
            data = json.loads(self.token_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict) or not data.get("access_token"):
            return
        raw_authority = data.get("authority", "")
        authority = ""
        if isinstance(raw_authority, str) and raw_authority.strip():
            try:
                authority = validate_tenant(raw_authority)
            except InvalidRequest:
                return
        elif raw_authority not in {"", None}:
            return
        self.bundle = TokenBundle(
            access_token=str(data.get("access_token", "")),
            refresh_token=str(data.get("refresh_token", "")),
            expires_at=float(data.get("expires_at", 0)),
            account=str(data.get("account", "")),
            scope=str(data.get("scope", "")),
            authority=authority,
        )

    def __repr__(self) -> str:
        return f"MicrosoftOAuth(configured={self.configured()}, connected={self.bundle is not None})"


def _https_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None,
) -> tuple[int, dict[str, Any]]:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in {"login.microsoftonline.com", "graph.microsoft.com"}:
        raise AuthenticationError("Microsoft requests are limited to the official hosts.")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=20) as response:
            raw = response.read(1_000_000)
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read(1_000_000)
        status = int(exc.code)
    except OSError as exc:
        raise TransientError("Microsoft could not be reached. The saved sign-in was kept.") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}
    return status, payload if isinstance(payload, dict) else {}
