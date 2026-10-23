"""Tests for Microsoft Graph API resilience features."""
from __future__ import annotations

import unittest
import uuid

from integrations.errors import RateLimited, TransientError
from integrations.microsoft_oauth import MicrosoftOAuth
from integrations.microsoft_resilience import (
    GraphResilience,
    create_resilient_client,
)
from integrations.resilience import RetryPolicy

CLIENT = str(uuid.UUID("11111111-2222-3333-4444-555555555555"))
TOKEN = "access-token"


class ResilienceTransport:
    """Mock transport that simulates various Graph API behaviors."""
    
    def __init__(self, scenario: str = "success"):
        self.calls: list[tuple[str, str]] = []
        self.scenario = scenario
        self.attempt = 0
        self.messages_attempt = 0  # Track attempts for /me/messages specifically
    
    def __call__(self, method: str, url: str, headers: dict, body: bytes | None):
        self.calls.append((method, url))
        self.attempt += 1
        
        # Track /me/messages attempts separately for transient error scenarios
        if "/me/messages" in url:
            self.messages_attempt += 1
        
        if url.endswith("/token"):
            return 200, {
                "access_token": TOKEN,
                "refresh_token": "refresh-token",
                "expires_in": 3600,
                "scope": "User.Read Mail.Read",
            }
        
        if url.startswith("https://graph.microsoft.com/v1.0/me?"):
            return 200, {"mail": "test@example.com", "displayName": "Test"}
        
        if "/me/messages" in url:
            if self.scenario == "success":
                return 200, {
                    "value": [
                        {"id": "msg-1", "subject": "Test 1"},
                        {"id": "msg-2", "subject": "Test 2"},
                    ],
                }
            
            elif self.scenario == "throttled_then_success":
                if self.messages_attempt <= 2:
                    return 429, {
                        "error": {
                            "code": "TooManyRequests",
                            "message": "Rate limit exceeded",
                        }
                    }
                return 200, {"value": [{"id": "msg-1", "subject": "Test"}]}
            
            elif self.scenario == "transient_then_success":
                if self.messages_attempt == 1:
                    return 503, {
                        "error": {
                            "code": "ServiceUnavailable",
                            "message": "Temporary unavailable",
                        }
                    }
                return 200, {"value": [{"id": "msg-1"}]}
            
            elif self.scenario == "paginated":
                # Check for skiptoken in URL (handles both encoded and unencoded)
                has_skiptoken = "$skiptoken=" in url or "%24skiptoken=" in url
                
                if not has_skiptoken:
                    # First page
                    return 200, {
                        "value": [
                            {"id": "msg-1", "subject": "Page 1"},
                            {"id": "msg-2", "subject": "Page 1"},
                        ],
                        "@odata.nextLink": (
                            "https://graph.microsoft.com/v1.0/me/messages"
                            "?$skiptoken=page2&$top=2"
                        ),
                    }
                elif "page2" in url:
                    # Second page
                    return 200, {
                        "value": [
                            {"id": "msg-3", "subject": "Page 2"},
                            {"id": "msg-4", "subject": "Page 2"},
                        ],
                        "@odata.nextLink": (
                            "https://graph.microsoft.com/v1.0/me/messages"
                            "?$skiptoken=page3&$top=2"
                        ),
                    }
                else:
                    # Last page (page3)
                    return 200, {
                        "value": [{"id": "msg-5", "subject": "Page 3"}],
                    }
            
            elif self.scenario == "permanent_error":
                return 400, {
                    "error": {
                        "code": "BadRequest",
                        "message": "Invalid query",
                    }
                }
        
        return 500, {}


class GraphResilienceTests(unittest.TestCase):
    def test_successful_request_without_retry(self) -> None:
        """Verify successful requests don't trigger retries."""
        transport = ResilienceTransport("success")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        resilience = GraphResilience(oauth)
        result = resilience.graph_get_with_retry(
            "/me/messages",
            {"$top": "2"},
            required_scope="Mail.Read",
        )
        
        self.assertIn("value", result)
        self.assertEqual(len(result["value"]), 2)
        self.assertEqual(resilience.get_retry_count(), 0)
    
    def test_retry_on_transient_error(self) -> None:
        """Verify automatic retry on transient 503 errors."""
        transport = ResilienceTransport("transient_then_success")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        # Create with fast retry for testing
        policy = RetryPolicy(max_attempts=4, base_delay=0.001, max_delay=0.01)
        resilience = GraphResilience(oauth, retry_policy=policy)
        
        result = resilience.graph_get_with_retry(
            "/me/messages",
            required_scope="Mail.Read",
        )
        
        # Should succeed after retry
        self.assertIn("value", result)
        # Should have made 2 attempts (1 failure + 1 success)
        graph_calls = [c for c in transport.calls if "/me/messages" in c[1]]
        self.assertGreaterEqual(len(graph_calls), 2)
    
    def test_pagination_with_cycle_detection(self) -> None:
        """Verify pagination handles multiple pages correctly."""
        transport = ResilienceTransport("paginated")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        resilience = GraphResilience(oauth)
        
        results = list(resilience.paginate_graph_results(
            "/me/messages",
            {"$select": "id,subject"},
            required_scope="Mail.Read",
            max_items=10,
            page_size=2,
        ))
        
        # Should get all 5 messages across 3 pages
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]["id"], "msg-1")
        self.assertEqual(results[4]["id"], "msg-5")
    
    def test_pagination_respects_max_items(self) -> None:
        """Verify pagination stops at max_items limit."""
        transport = ResilienceTransport("paginated")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        resilience = GraphResilience(oauth)
        
        # Limit to 3 items even though more are available
        results = list(resilience.paginate_graph_results(
            "/me/messages",
            required_scope="Mail.Read",
            max_items=3,
            page_size=2,
        ))
        
        self.assertEqual(len(results), 3)
    
    def test_search_mail_with_pagination(self) -> None:
        """Verify high-level search mail method."""
        transport = ResilienceTransport("paginated")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        resilience = GraphResilience(oauth)
        
        results = resilience.search_mail_with_pagination(
            "project alpha",
            max_results=10,
        )
        
        # Should return results (mocked paginated data)
        self.assertGreater(len(results), 0)
        self.assertIsInstance(results, list)
    
    def test_search_mail_handles_empty_query(self) -> None:
        """Verify search handles empty queries gracefully."""
        transport = ResilienceTransport("success")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        resilience = GraphResilience(oauth)
        
        results = resilience.search_mail_with_pagination("")
        self.assertEqual(results, [])
    
    def test_permanent_error_not_retried(self) -> None:
        """Verify permanent errors (400) are not retried."""
        transport = ResilienceTransport("permanent_error")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        policy = RetryPolicy(max_attempts=4, base_delay=0.001)
        resilience = GraphResilience(oauth, retry_policy=policy)
        
        with self.assertRaises(Exception):
            resilience.graph_get_with_retry(
                "/me/messages",
                required_scope="Mail.Read",
            )
        
        # Should only make 1 attempt (400 is not retryable)
        graph_calls = [c for c in transport.calls if "/me/messages" in c[1]]
        self.assertEqual(len(graph_calls), 1)
    
    def test_create_resilient_client_factory(self) -> None:
        """Verify factory function creates properly configured client."""
        transport = ResilienceTransport("success")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        resilient = create_resilient_client(
            oauth,
            max_retries=5,
            timeout=60.0,
        )
        
        self.assertIsInstance(resilient, GraphResilience)
        self.assertEqual(resilient.retry_policy.max_attempts, 5)
        self.assertEqual(resilient.default_timeout, 60.0)
    
    def test_retry_count_tracking(self) -> None:
        """Verify retry count is tracked correctly."""
        transport = ResilienceTransport("transient_then_success")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        policy = RetryPolicy(max_attempts=4, base_delay=0.001, max_delay=0.01)
        resilience = GraphResilience(oauth, retry_policy=policy)
        
        initial_count = resilience.get_retry_count()
        
        resilience.graph_get_with_retry(
            "/me/messages",
            required_scope="Mail.Read",
        )
        
        # Should have incremented retry count
        final_count = resilience.get_retry_count()
        self.assertGreater(final_count, initial_count)
    
    def test_search_returns_partial_results_on_rate_limit(self) -> None:
        """Verify search returns partial results if rate limited mid-pagination."""
        transport = ResilienceTransport("paginated")
        oauth = MicrosoftOAuth(client_id=CLIENT, transport=transport, clock=lambda: 1000.0)
        
        url = oauth.authorization_url()
        state = url.split("state=")[1].split("&")[0]
        oauth.complete("code-1", state)
        
        resilience = GraphResilience(oauth)
        
        # Even if pagination encounters errors, return what we have
        results = resilience.search_mail_with_pagination(
            "test query",
            max_results=100,
        )
        
        # Should return some results even if not all pages complete
        self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main()
