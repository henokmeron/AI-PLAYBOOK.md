"""Microsoft sign-in and read-only mail. The transport is in-memory, not Graph."""
from __future__ import annotations

import json
import unittest
import uuid

from integrations.errors import ApprovalRequired, AuthenticationError, PermissionDenied
from integrations.microsoft365 import platform_catalog
from integrations.microsoft_oauth import MicrosoftOAuth, validate_redirect
from integrations.tenancy import TenantContext

CLIENT = str(uuid.UUID("11111111-2222-3333-4444-555555555555"))
TOKEN = "access-token-not-for-the-browser"
REFRESH = "refresh-token-not-for-the-browser"


class Transport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, bytes | None]] = []
        self.access = TOKEN

    def __call__(self, method: str, url: str, headers: dict, body: bytes | None):
        self.calls.append((method, url, dict(headers), body))
        if url.endswith("/token"):
            return 200, {
                "access_token": self.access,
                "refresh_token": REFRESH,
                "expires_in": 3600,
                "scope": "Mail.Read User.Read",
            }
        if url.startswith("https://graph.microsoft.com/v1.0/me?"):
            return 200, {"mail": "owner@example.com", "displayName": "Owner"}
        if "/me/messages/" in url:
            return 200, {
                "id": "AAMkAG12345678",
                "subject": "Invoice 14",
                "from": {"emailAddress": {"address": "supplier@example.com"}},
                "bodyPreview": "Amount due 10",
                "webLink": "https://outlook.office.com/mail/id",
            }
        if "/me/messages" in url:
            return 200, {"value": [{
                "id": "AAMkAG12345678",
                "subject": "Invoice 14",
                "from": {"emailAddress": {"address": "supplier@example.com"}},
                "bodyPreview": "Amount due 10",
                "webLink": "https://outlook.office.com/mail/id",
            }]}
        return 500, {}


class OAuthTests(unittest.TestCase):
    def test_sign_in_cannot_start_without_an_application_id(self) -> None:
        oauth = MicrosoftOAuth()
        self.assertFalse(oauth.configured())
        with self.assertRaises(AuthenticationError):
            oauth.authorization_url()
        self.assertNotIn("access_token", json.dumps(oauth.public_status()))

    def test_authorization_url_uses_pkce_and_no_client_secret(self) -> None:
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=Transport())
        url = oauth.authorization_url()
        self.assertTrue(url.startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?"))
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("Mail.Read", url)
        self.assertNotIn("client_secret", url)
        self.assertNotIn("Mail.Send", url)
        with self.assertRaises(Exception):
            validate_redirect("https://evil.example/api/microsoft/callback")

    def test_callback_stores_the_account_and_search_does_not_send_mail(self) -> None:
        transport = Transport()
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1_000.0)
        url = oauth.authorization_url()
        state = url.split("state=", 1)[1].split("&", 1)[0]
        with self.assertRaises(AuthenticationError):
            oauth.complete("again", "not-the-state")
        bundle = oauth.complete("code-1", state)
        self.assertEqual(bundle.account, "owner@example.com")
        self.assertNotIn(TOKEN, repr(oauth))
        with self.assertRaises(AuthenticationError):
            oauth.complete("code-1", state)
        catalog, client = platform_catalog(oauth)
        client.apply(catalog, "local-console")
        ctx = TenantContext.create("local-console", "console-user", [])
        visible = [item.name for _spec, item in catalog.visible_operations(ctx)]
        self.assertIn("search_mail", visible)
        self.assertNotIn("send_mail", visible)
        found = catalog.execute(ctx, "microsoft365", "search_mail", {"query": "invoice"})
        self.assertEqual(found["messages"][0]["subject"], "Invoice 14")
        self.assertIn("Bearer " + TOKEN, transport.calls[-1][2]["Authorization"])
        before = len(transport.calls)
        with self.assertRaises(PermissionDenied):
            catalog.execute(ctx, "microsoft365", "send_mail", {
                "to": "a@example.com", "subject": "Hi", "body": "Send this now",
            }, authorised=True)
        record = catalog.connection("local-console", "microsoft365")
        record.granted_scopes = frozenset({"mail:read", "mail:write"})
        with self.assertRaises(ApprovalRequired):
            catalog.execute(ctx, "microsoft365", "send_mail", {
                "to": "a@example.com", "subject": "Hi", "body": "Send this now",
            })
        with self.assertRaises(AuthenticationError) as caught:
            catalog.execute(ctx, "microsoft365", "send_mail", {
                "to": "a@example.com", "subject": "Hi", "body": "Send this now",
            }, authorised=True)
        self.assertIn("No request was sent", str(caught.exception))
        self.assertEqual(len(transport.calls), before)

        def reject(method, url, headers, body):
            return 401, {"error": {"message": TOKEN}}
        oauth._transport = reject  # noqa: SLF001
        with self.assertRaises(AuthenticationError) as rejected:
            catalog.execute(ctx, "microsoft365", "search_mail", {"query": "invoice"})
        self.assertNotIn(TOKEN, str(rejected.exception))

    def test_expired_token_is_refreshed_before_graph(self) -> None:
        now = {"t": 1_000.0}
        transport = Transport()
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: now["t"])
        url = oauth.authorization_url()
        state = url.split("state=", 1)[1].split("&", 1)[0]
        oauth.complete("code-1", state)
        now["t"] = 9_000.0
        transport.access = "access-token-refreshed"
        catalog, client = platform_catalog(oauth)
        client.apply(catalog, "local-console")
        ctx = TenantContext.create("local-console", "console-user", [])
        catalog.execute(ctx, "microsoft365", "search_mail", {"query": "invoice"})
        self.assertTrue(any(call[0] == "POST" and call[1].endswith("/token") for call in transport.calls[1:]))
        self.assertIn("Bearer access-token-refreshed", transport.calls[-1][2]["Authorization"])
        self.assertNotIn(TOKEN, json.dumps(oauth.public_status()))
