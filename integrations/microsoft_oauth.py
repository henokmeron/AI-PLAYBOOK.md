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
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .errors import AuthenticationError, InvalidRequest

SCOPES = ("openid", "profile", "email", "offline_access", "User.Read", "Mail.Read")
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def validate_client_id(value: str) -> str:
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError) as exc:
        raise InvalidRequest("Microsoft client id must be the application id from Entra") from exc


def validate_redirect(value: str) -> str:
    parts = urllib.parse.urlsplit(value.strip())
    host = (parts.hostname or "").lower()
    loopback = parts.scheme == "http" and host in {"127.0.0.1", "localhost"} and parts.port
    secure = parts.scheme == "https" and host and parts.port
    if parts.username or parts.password or parts.fragment or not (loopback or secure):
        raise InvalidRequest("Microsoft redirect URI must be loopback http or https with a port")
    if not parts.path.startswith("/api/microsoft/callback"):
        raise InvalidRequest("Microsoft redirect URI must use /api/microsoft/callback")
    return value.strip()


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_at: float
    account: str
    scope: str

    def public(self) -> dict[str, Any]:
        return {"account": self.account, "scope": self.scope, "connected": True}


class MicrosoftOAuth:
    def __init__(
        self,
        *,
        client_id: str = "",
        tenant: str = "common",
        redirect_uri: str = "http://127.0.0.1:18080/api/microsoft/callback",
        token_file: Path | None = None,
        clock: Callable[[], float] = time.time,
        transport: Callable[[str, str, dict[str, str], bytes | None], tuple[int, dict[str, Any]]] | None = None,
    ) -> None:
        self.client_id = client_id.strip()
        self.tenant = tenant.strip() or "common"
        self.redirect_uri = redirect_uri.strip()
        self.token_file = token_file
        self._clock = clock
        self._transport = transport or _https_transport
        self._pending: dict[str, tuple[str, float]] = {}
        self.bundle: TokenBundle | None = None
        self.graph_calls = 0
        if token_file is not None and token_file.is_file():
            self._load()

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "MicrosoftOAuth":
        source = os.environ if environ is None else environ
        path = source.get("MICROSOFT_TOKEN_FILE", "").strip()
        return cls(
            client_id=source.get("MICROSOFT_CLIENT_ID", ""),
            tenant=source.get("MICROSOFT_TENANT", "common"),
            redirect_uri=source.get(
                "MICROSOFT_REDIRECT_URI", "http://127.0.0.1:18080/api/microsoft/callback"
            ),
            token_file=Path(path) if path else None,
        )

    def configured(self) -> bool:
        return bool(self.client_id)

    def public_status(self) -> dict[str, Any]:
        account = self.bundle.account if self.bundle else None
        return {
            "configured": self.configured(),
            "connected": self.bundle is not None,
            "account": account,
            "redirect_uri": self.redirect_uri if self.configured() else None,
            "provider_scopes": list(SCOPES) if self.configured() else [],
            "setup": "" if self.configured() else (
                "Sign-in needs an Entra application id in MICROSOFT_CLIENT_ID. "
                "No Microsoft account is connected."
            ),
        }

    def authorization_url(self) -> str:
        if not self.configured():
            raise AuthenticationError(self.public_status()["setup"])
        client_id = validate_client_id(self.client_id)
        redirect = validate_redirect(self.redirect_uri)
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        self._pending[state] = (verifier, self._clock() + 600)
        query = urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect,
            "response_mode": "query",
            "scope": " ".join(SCOPES),
            "state": state,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
        })
        return f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/authorize?{query}"

    def complete(self, code: str, state: str) -> TokenBundle:
        pending = self._pending.pop(state, None)
        if pending is None or self._clock() > pending[1]:
            raise AuthenticationError("Microsoft sign-in state is missing or expired")
        if not code or len(code) > 2048:
            raise AuthenticationError("Microsoft did not return a usable sign-in code")
        token = self._token({
            "client_id": validate_client_id(self.client_id),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": validate_redirect(self.redirect_uri),
            "code_verifier": pending[0],
        })
        account = self._account(token["access_token"])
        self.bundle = TokenBundle(
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token", ""),
            expires_at=self._clock() + int(token.get("expires_in", 3600)) - 60,
            account=account,
            scope=str(token.get("scope", "")),
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
            refreshed = self._token({
                "client_id": validate_client_id(self.client_id),
                "grant_type": "refresh_token",
                "refresh_token": self.bundle.refresh_token,
                "scope": " ".join(SCOPES),
            })
            self.bundle.access_token = refreshed["access_token"]
            self.bundle.refresh_token = refreshed.get("refresh_token", self.bundle.refresh_token)
            self.bundle.expires_at = self._clock() + int(refreshed.get("expires_in", 3600)) - 60
            self._save()
        return self.bundle.access_token

    def graph_get(self, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
        token = self.access_token()
        url = GRAPH_ROOT + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        self.graph_calls += 1
        status, payload = self._transport("GET", url, {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "ConsistencyLevel": "eventual",
        }, None)
        if status == 401:
            raise AuthenticationError("Microsoft rejected the saved sign-in. Connect the account again.")
        if status == 403:
            raise AuthenticationError("Microsoft refused this read. The Mail.Read consent is missing.")
        if status != 200 or not isinstance(payload, dict):
            raise AuthenticationError("Microsoft Graph did not return the mailbox data.")
        return payload

    def disconnect(self) -> None:
        self.bundle = None
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

    def _token(self, fields: dict[str, str]) -> dict[str, Any]:
        body = urllib.parse.urlencode(fields).encode("utf-8")
        status, payload = self._transport(
            "POST",
            f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/token",
            {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            body,
        )
        if status != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
            raise AuthenticationError("Microsoft did not issue an access token.")
        if "client_secret" in fields:
            raise AuthenticationError("This sign-in flow does not use a client secret.")
        return payload

    def _save(self) -> None:
        if self.token_file is None or self.bundle is None:
            return
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.token_file.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "access_token": self.bundle.access_token,
            "refresh_token": self.bundle.refresh_token,
            "expires_at": self.bundle.expires_at,
            "account": self.bundle.account,
            "scope": self.bundle.scope,
        }), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.token_file)
        os.chmod(self.token_file, 0o600)

    def _load(self) -> None:
        if self.token_file is None:
            return
        try:
            data = json.loads(self.token_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict) or not data.get("access_token"):
            return
        self.bundle = TokenBundle(
            access_token=str(data.get("access_token", "")),
            refresh_token=str(data.get("refresh_token", "")),
            expires_at=float(data.get("expires_at", 0)),
            account=str(data.get("account", "")),
            scope=str(data.get("scope", "")),
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
        raise AuthenticationError("Microsoft could not be reached.") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}
    return status, payload if isinstance(payload, dict) else {}
