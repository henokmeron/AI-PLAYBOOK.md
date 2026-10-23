"""Tests for privacy-safe mailbox verification harness."""
from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from integrations.errors import AuthenticationError
from integrations.mail_verification import (
    MailboxVerificationHarness,
    VerificationResult,
)
from integrations.microsoft_oauth import MicrosoftOAuth

CLIENT = str(uuid.UUID("11111111-2222-3333-4444-555555555555"))
TOKEN = "access-token-not-for-the-browser"


class MockTransport:
    """Mock transport that returns predictable Graph responses."""
    
    def __init__(self, response_type: str = "success"):
        self.calls: list[tuple[str, str]] = []
        self.response_type = response_type
    
    def __call__(self, method: str, url: str, headers: dict, body: bytes | None):
        self.calls.append((method, url))
        
        if url.endswith("/token"):
            return 200, {
                "access_token": TOKEN,
                "refresh_token": "refresh-token",
                "expires_in": 3600,
                "scope": "User.Read Mail.Read",
            }
        
        if url.startswith("https://graph.microsoft.com/v1.0/me?"):
            return 200, {"mail": "test@example.com", "displayName": "Test User"}
        
        if "/me/messages" in url and "$search=" in url:
            if self.response_type == "success_with_results":
                # Return results without exposing content
                return 200, {"value": [
                    {"id": "msg-1"},
                    {"id": "msg-2"},
                ]}
            elif self.response_type == "success_empty":
                return 200, {"value": []}
            elif self.response_type == "auth_error":
                return 401, {"error": {"code": "Unauthorized"}}
            elif self.response_type == "permission_denied":
                return 403, {"error": {"code": "AccessDenied"}}
            elif self.response_type == "throttled":
                return 429, {"error": {"code": "TooManyRequests"}}
            elif self.response_type == "server_error":
                return 500, {"error": {"code": "InternalServerError"}}
        
        return 500, {}


class MailVerificationTests(unittest.TestCase):
    def test_positive_match_verification_with_results(self) -> None:
        """Verify that a positive match correctly identifies found results."""
        transport = MockTransport("success_with_results")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        # Complete sign-in
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = Path(tmpdir) / "results.json"
            harness = MailboxVerificationHarness(oauth=oauth, result_path=result_path)
            
            result = harness.verify_positive_match("distinctive-project-alpha")
            
            # Verify result structure
            self.assertTrue(result.success)
            self.assertEqual(result.http_status, 200)
            self.assertEqual(result.result_count, 2)
            self.assertTrue(result.expected_match_found)
            self.assertIsNone(result.error_type)
            self.assertEqual(result.test_type, "positive_match")
            
            # Verify results were saved
            self.assertTrue(result_path.exists())
            with result_path.open() as f:
                saved = json.load(f)
            self.assertEqual(saved["total_tests"], 1)
            self.assertEqual(saved["results"][0]["result_count"], 2)
    
    def test_negative_match_verification_with_empty_results(self) -> None:
        """Verify that a negative match correctly identifies no results."""
        transport = MockTransport("success_empty")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        harness = MailboxVerificationHarness(oauth=oauth)
        result = harness.verify_negative_match("nonexistent-uuid-12345-67890")
        
        self.assertTrue(result.success)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.result_count, 0)
        self.assertTrue(result.expected_match_found)  # Expect zero is correct
        self.assertIsNone(result.error_type)
        self.assertEqual(result.test_type, "negative_match")
    
    def test_verification_blocks_generic_phrases(self) -> None:
        """Verify that generic phrases are rejected."""
        transport = MockTransport("success_with_results")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        harness = MailboxVerificationHarness(oauth=oauth)
        
        # Single-letter phrases should be rejected for length
        for single in ["a"]:
            with self.assertRaises(ValueError) as ctx:
                harness.verify_positive_match(single)
            self.assertIn("at least 3 characters", str(ctx.exception))
        
        # Common generic words should be rejected
        for generic in ["the", "was"]:
            with self.assertRaises(ValueError) as ctx:
                harness.verify_positive_match(generic)
            self.assertIn("too generic", str(ctx.exception))
    
    def test_verification_requires_minimum_phrase_length(self) -> None:
        """Verify that too-short phrases are rejected."""
        harness = MailboxVerificationHarness(oauth=None)
        
        with self.assertRaises(ValueError):
            harness.verify_positive_match("")
        
        with self.assertRaises(ValueError):
            harness.verify_positive_match("ab")
    
    def test_verification_without_oauth_connection(self) -> None:
        """Verify graceful handling when OAuth is not connected."""
        harness = MailboxVerificationHarness(oauth=None)
        
        result = harness.verify_positive_match("distinctive-phrase")
        
        self.assertFalse(result.success)
        self.assertIsNone(result.http_status)
        self.assertEqual(result.result_count, 0)
        self.assertIsNone(result.expected_match_found)
        self.assertEqual(result.error_type, "NOT_CONNECTED")
    
    def test_verification_handles_authentication_error(self) -> None:
        """Verify handling of authentication failures."""
        transport = MockTransport("auth_error")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        harness = MailboxVerificationHarness(oauth=oauth)
        result = harness.verify_positive_match("test-phrase")
        
        self.assertFalse(result.success)
        self.assertEqual(result.http_status, 401)
        self.assertEqual(result.error_type, "AuthenticationError")
    
    def test_synthetic_fixture_verification(self) -> None:
        """Verify synthetic fixture testing without live credentials."""
        harness = MailboxVerificationHarness()
        
        # Test with results
        fixture_with_results = {
            "http_status": 200,
            "value": [{"id": "msg-1"}, {"id": "msg-2"}],
        }
        result1 = harness.verify_with_synthetic_fixture(fixture_with_results)
        
        self.assertTrue(result1.success)
        self.assertEqual(result1.http_status, 200)
        self.assertEqual(result1.result_count, 2)
        self.assertTrue(result1.expected_match_found)
        self.assertEqual(result1.test_type, "synthetic_fixture")
        
        # Test with empty results
        fixture_empty = {
            "http_status": 200,
            "value": [],
        }
        result2 = harness.verify_with_synthetic_fixture(fixture_empty)
        
        self.assertTrue(result2.success)
        self.assertEqual(result2.result_count, 0)
        self.assertFalse(result2.expected_match_found)
        
        # Test with error
        fixture_error = {
            "http_status": 401,
            "error": {"code": "Unauthorized"},
        }
        result3 = harness.verify_with_synthetic_fixture(fixture_error)
        
        self.assertFalse(result3.success)
        self.assertEqual(result3.error_type, "SYNTHETIC_ERROR")
    
    def test_verification_summary_aggregates_correctly(self) -> None:
        """Verify that summary statistics are calculated correctly."""
        transport = MockTransport("success_with_results")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        harness = MailboxVerificationHarness(oauth=oauth)
        
        # Run multiple verifications
        harness.verify_positive_match("project-alpha")
        
        transport.response_type = "success_empty"
        harness.verify_negative_match("nonexistent-12345")
        
        harness.verify_with_synthetic_fixture({
            "http_status": 200,
            "value": [{"id": "msg-1"}],
        })
        
        summary = harness.summary()
        
        self.assertEqual(summary["total_tests"], 3)
        self.assertEqual(summary["successful_tests"], 3)
        self.assertEqual(summary["positive_matches_verified"], 1)
        self.assertEqual(summary["negative_matches_verified"], 1)
        self.assertEqual(summary["synthetic_fixtures"], 1)
        self.assertTrue(summary["live_mailbox_verified"])
    
    def test_verification_result_exports_without_personal_data(self) -> None:
        """Verify that result exports contain no personal data."""
        result = VerificationResult(
            success=True,
            http_status=200,
            result_count=5,
            expected_match_found=True,
            error_type=None,
            test_type="positive_match",
        )
        
        exported = result.to_dict()
        
        # Verify structure
        self.assertIn("success", exported)
        self.assertIn("http_status", exported)
        self.assertIn("result_count", exported)
        self.assertIn("expected_match_found", exported)
        
        # Verify no personal data fields
        self.assertNotIn("subject", exported)
        self.assertNotIn("body", exported)
        self.assertNotIn("sender", exported)
        self.assertNotIn("recipient", exported)
        self.assertNotIn("message", exported)
        
        # Convert to JSON to ensure it's serializable
        json_str = json.dumps(exported)
        self.assertIsInstance(json_str, str)
    
    def test_verification_distinguishes_empty_from_failed(self) -> None:
        """Verify distinction between successful empty search and failed request."""
        transport = MockTransport("success_empty")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        harness = MailboxVerificationHarness(oauth=oauth)
        
        # Successful empty search
        result_empty = harness.verify_negative_match("nonexistent-phrase")
        self.assertTrue(result_empty.success)
        self.assertEqual(result_empty.result_count, 0)
        self.assertIsNone(result_empty.error_type)
        
        # Failed request
        transport.response_type = "server_error"
        result_failed = harness.verify_positive_match("test-phrase")
        self.assertFalse(result_failed.success)
        self.assertIsNotNone(result_failed.error_type)
    
    def test_verification_only_requests_id_field(self) -> None:
        """Verify that search only requests id field, not content."""
        transport = MockTransport("success_with_results")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        harness = MailboxVerificationHarness(oauth=oauth)
        harness.verify_positive_match("distinctive-phrase")
        
        # Check that the Graph call included $select=id
        graph_calls = [
            call for call in transport.calls
            if "/me/messages" in call[1] and "$search=" in call[1]
        ]
        self.assertEqual(len(graph_calls), 1)
        
        # Verify $select=id is present (no subject, body, etc.)
        url = graph_calls[0][1]
        self.assertIn("$select=id", url)
        self.assertNotIn("subject", url.lower())
        self.assertNotIn("body", url.lower())


if __name__ == "__main__":
    unittest.main()
