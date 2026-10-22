"""Google Workspace read-only skeleton. The transport is in-memory, not Google."""
from __future__ import annotations

import json
import unittest
import urllib.parse

from integrations.catalog import Catalog
from integrations.errors import AuthenticationError, PermissionDenied
from integrations.google_workspace import (
    CALENDAR_READONLY,
    DOCS_READONLY,
    DRIVE_READONLY,
    FORBIDDEN_SCOPES,
    GMAIL_READONLY,
    GOOGLE_WORKSPACE,
    READ_SCOPES,
    GoogleWorkspace,
    google_configuration,
)

CLIENT = "local-test-client.apps.googleusercontent.com"
TOKEN = "google-access-token-not-for-the-browser"
SECRET = "google-client-secret-not-used"


class Transport:
    def __init__(self, scope: str | None = None) -> None:
        self.calls: list[tuple[str, str, dict, bytes | None]] = []
        self.scope = scope or " ".join(READ_SCOPES)

    def __call__(self, method: str, url: str, headers: dict, body: bytes | None):
        self.calls.append((method, url, dict(headers), body))
        if url.endswith("/token"):
            return 200, {
                "access_token": TOKEN,
                "expires_in": 3600,
                "scope": self.scope,
            }
        if url.endswith("/users/me/profile"):
            return 200, {"emailAddress": "owner@example.com"}
        if "gmail.googleapis.com" in url and "/messages" in url:
            return 200, {"messages": [{"id": "msg-1", "threadId": "thread-1"}]}
        if "docs.googleapis.com" in url:
            return 200, {"documentId": "docid1234", "title": "Plan"}
        if "mimeType" in url:
            return 200, {"files": [{"id": "doc-1", "name": "Plan"}]}
        if "/drive/v3/files" in url:
            return 200, {"files": [{"id": "file-1", "name": "Notes"}]}
        if "/calendar/" in url:
            return 200, {"items": [{"id": "event-1", "summary": "Standup"}]}
        return 500, {"error": TOKEN}


def _signed_in(scope: str | None = None) -> tuple[GoogleWorkspace, Transport]:
    transport = Transport(scope)
    google = GoogleWorkspace(client_id=CLIENT, transport=transport, clock=lambda: 1_000.0)
    url = google.authorization_url()
    state = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["state"][0]
    google.complete("code-1", state)
    return google, transport


class GoogleWorkspaceTests(unittest.TestCase):
    def test_missing_client_id_stays_not_configured(self) -> None:
        google = GoogleWorkspace()
        self.assertFalse(google.configured())
        status = google.public_status()
        self.assertEqual(status["status"], "NOT CONFIGURED")
        self.assertFalse(status["connected"])
        self.assertIsNone(status["account"])
        report = google_configuration({})
        self.assertEqual(report["status"], "NOT CONFIGURED")
        self.assertEqual(report["client_id"], "absent")
        self.assertFalse(report["connected"])
        with self.assertRaises(AuthenticationError):
            google.authorization_url()
        with self.assertRaises(AuthenticationError) as caught:
            google.list_gmail()
        self.assertIn("NOT CONFIGURED", str(caught.exception))
        self.assertEqual(google.calls, 0)

    def test_client_id_alone_does_not_connect(self) -> None:
        google = GoogleWorkspace(client_id=CLIENT)
        report = google_configuration({"GOOGLE_CLIENT_ID": CLIENT, "GOOGLE_CLIENT_SECRET": SECRET})
        self.assertEqual(report["status"], "NOT CONFIGURED")
        self.assertEqual(report["client_id"], "present")
        self.assertFalse(report["connected"])
        self.assertNotIn(CLIENT, json.dumps(report))
        self.assertNotIn(SECRET, json.dumps(report))
        self.assertEqual(google.public_status()["status"], "NOT CONFIGURED")
        self.assertFalse(google.public_status()["connected"])
        loaded = GoogleWorkspace.from_env({
            "GOOGLE_CLIENT_ID": CLIENT,
            "GOOGLE_CLIENT_SECRET": SECRET,
        })
        self.assertTrue(loaded.configured())
        self.assertNotIn(SECRET, json.dumps(loaded.public_status()))
        self.assertNotIn(CLIENT, json.dumps(loaded.public_status()))
        with self.assertRaises(AuthenticationError):
            loaded.list_drive()

    def test_authorize_uses_readonly_scopes_and_no_secret(self) -> None:
        google = GoogleWorkspace(client_id=CLIENT, transport=Transport(), clock=lambda: 1_000.0)
        url = google.authorization_url()
        self.assertTrue(url.startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(set(query["scope"][0].split()), set(READ_SCOPES))
        self.assertIn(GMAIL_READONLY, query["scope"][0])
        self.assertIn(DRIVE_READONLY, query["scope"][0])
        self.assertIn(CALENDAR_READONLY, query["scope"][0])
        self.assertIn(DOCS_READONLY, query["scope"][0])
        self.assertTrue(FORBIDDEN_SCOPES.isdisjoint(query["scope"][0].split()))
        self.assertNotIn("client_secret", url)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn(TOKEN, url)
        permissions = {item.name: item.provider_permissions for item in GOOGLE_WORKSPACE.operations}
        self.assertEqual(permissions["list_gmail"], (GMAIL_READONLY,))
        self.assertEqual(permissions["list_drive"], (DRIVE_READONLY,))
        self.assertEqual(permissions["list_calendar"], (CALENDAR_READONLY,))
        self.assertEqual(permissions["list_docs"], (DOCS_READONLY, DRIVE_READONLY))
        self.assertEqual(permissions["read_doc"], (DOCS_READONLY,))
        self.assertTrue(all(item.evidence == "mock-tested" for item in GOOGLE_WORKSPACE.operations))

    def test_mock_reads_do_not_become_a_connected_status(self) -> None:
        google, transport = _signed_in()
        self.assertEqual(google.public_status()["status"], "NOT CONFIGURED")
        self.assertFalse(google.public_status()["connected"])
        self.assertIsNone(google.public_status()["account"])
        self.assertNotIn(TOKEN, repr(google))
        mail = google.perform("list_gmail")
        drive = google.perform("list_drive")
        calendar = google.perform("list_calendar")
        docs = google.perform("list_docs")
        document = google.perform("read_doc", {"document_id": "docid1234"})
        self.assertEqual(mail["items"][0]["id"], "msg-1")
        self.assertEqual(drive["items"][0]["name"], "Notes")
        self.assertEqual(calendar["items"][0]["name"], "Standup")
        self.assertEqual(docs["items"][0]["name"], "Plan")
        self.assertIn("mimeType", transport.calls[-2][1])
        self.assertEqual(document["items"][0]["name"], "Plan")
        self.assertTrue(transport.calls[-1][1].startswith("https://docs.googleapis.com/v1/documents/"))
        self.assertEqual(google.public_status()["status"], "NOT CONFIGURED")
        self.assertFalse(google.public_status()["connected"])
        self.assertNotIn(TOKEN, json.dumps(mail))
        self.assertNotIn(CLIENT, json.dumps(google.public_status()))
        catalog = Catalog([GOOGLE_WORKSPACE], lambda connector, operation, params: google.perform(operation, params))
        google.apply(catalog, "local-console")
        described = catalog.describe("local-console")[0]
        self.assertEqual(described["connector_id"], "google_workspace")
        self.assertFalse(described["connected"])
        self.assertIsNone(described["account"])
        self.assertNotIn("live-tested", json.dumps(described))

    def test_write_scope_and_send_are_refused_without_a_request(self) -> None:
        google, transport = _signed_in()
        before = len(transport.calls)
        with self.assertRaises(PermissionDenied) as caught:
            google.perform("send_gmail", {"to": "a@example.com"})
        self.assertIn("No request was sent", str(caught.exception))
        self.assertEqual(len(transport.calls), before)
        self.assertEqual(google.public_status()["status"], "NOT CONFIGURED")

        def writes(method, url, headers, body):
            transport.calls.append((method, url, dict(headers), body))
            if url.endswith("/token"):
                return 200, {
                    "access_token": TOKEN,
                    "expires_in": 3600,
                    "scope": GMAIL_READONLY + " https://www.googleapis.com/auth/gmail.send",
                }
            return 500, {}

        refused = GoogleWorkspace(client_id=CLIENT, transport=writes, clock=lambda: 1_000.0)
        url = refused.authorization_url()
        state = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["state"][0]
        with self.assertRaises(PermissionDenied):
            refused.complete("code-1", state)
        self.assertIsNone(refused.bundle)
        self.assertFalse(refused.public_status()["connected"])
        self.assertNotIn(TOKEN, json.dumps(refused.public_status()))
