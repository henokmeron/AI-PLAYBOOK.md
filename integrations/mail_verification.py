"""Privacy-safe mailbox verification harness.

This module provides a verification harness that can confirm mailbox access
without storing or logging sensitive data (subject lines, bodies, senders).

The harness records ONLY:
- HTTP status codes
- Result counts
- Whether an expected match was present (boolean)
- Success/failure indicators

It distinguishes between:
- Successful search with results
- Successful empty search (no matches)
- Failed request (error/unavailable)

Live mailbox evidence requires owner-supplied distinctive phrases and proper
credentials. Synthetic fixtures are used for automated tests.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .errors import AuthenticationError
from .microsoft_oauth import MicrosoftOAuth

# Configure privacy-safe logging - never log message content
logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Privacy-safe verification result - NO personal data stored."""
    success: bool
    http_status: int | None
    result_count: int
    expected_match_found: bool | None
    error_type: str | None
    test_type: str  # "positive_match", "negative_match", or "synthetic_fixture"
    
    def to_dict(self) -> dict[str, Any]:
        """Export result without exposing personal data."""
        return {
            "success": self.success,
            "http_status": self.http_status,
            "result_count": self.result_count,
            "expected_match_found": self.expected_match_found,
            "error_type": self.error_type,
            "test_type": self.test_type,
        }


class MailboxVerificationHarness:
    """Privacy-safe mailbox verification.
    
    This harness verifies mailbox access WITHOUT storing or logging:
    - Subject lines
    - Message bodies
    - Sender addresses
    - Recipient addresses
    - Any other personal data
    
    It records ONLY:
    - HTTP response codes
    - Result counts
    - Boolean match indicators
    - Error types
    """
    
    def __init__(
        self,
        oauth: MicrosoftOAuth | None = None,
        result_path: Path | None = None,
    ) -> None:
        """Initialize verification harness.
        
        Args:
            oauth: Microsoft OAuth client (optional, for live testing)
            result_path: Path to store privacy-safe results (optional)
        """
        self.oauth = oauth
        self.result_path = result_path
        self.results: list[VerificationResult] = []
    
    def verify_positive_match(self, search_phrase: str) -> VerificationResult:
        """Verify that a distinctive phrase can be found.
        
        This performs a live mailbox search with an owner-supplied distinctive
        phrase and verifies that at least one result is returned.
        
        Args:
            search_phrase: Owner-supplied distinctive phrase (NOT generic words
                          like "the"). Should be unique enough to match specific
                          messages.
        
        Returns:
            VerificationResult with:
            - success: True if search executed successfully
            - http_status: HTTP response code
            - result_count: Number of messages found
            - expected_match_found: True if result_count > 0
            - error_type: None if successful, error class name otherwise
            
        Raises:
            AuthenticationError: If mailbox is not connected
            ValueError: If search_phrase is too generic or empty
        """
        if not search_phrase or len(search_phrase.strip()) < 3:
            raise ValueError("Search phrase must be at least 3 characters")
        
        # Refuse generic phrases that would match too broadly
        generic_words = {"the", "a", "an", "is", "was", "are", "be", "to", "of"}
        if search_phrase.strip().lower() in generic_words:
            raise ValueError(
                "Search phrase is too generic. Use a distinctive phrase "
                "specific to your mailbox (e.g., a unique project name or identifier)."
            )
        
        if self.oauth is None or self.oauth.bundle is None:
            result = VerificationResult(
                success=False,
                http_status=None,
                result_count=0,
                expected_match_found=None,
                error_type="NOT_CONNECTED",
                test_type="positive_match",
            )
            self.results.append(result)
            logger.warning("Mailbox verification blocked: OAuth not connected")
            return result
        
        try:
            # Perform search - microsoft_oauth handles the actual Graph call
            # We only extract count, never content
            cleaned = " ".join(search_phrase.replace("\\", " ").replace('"', " ").split())
            payload = self.oauth.graph_get(
                "/me/messages",
                {
                    "$search": f'"{cleaned[:200]}"',
                    "$top": "5",
                    "$select": "id",  # Only id field - no subjects or bodies
                },
                required_scope="Mail.Read",
            )
            
            # Count results without accessing content
            raw = payload.get("value", [])
            count = len(raw) if isinstance(raw, list) else 0
            
            result = VerificationResult(
                success=True,
                http_status=200,
                result_count=count,
                expected_match_found=count > 0,
                error_type=None,
                test_type="positive_match",
            )
            
            logger.info(
                "Positive match verification completed: found=%s, count=%d",
                count > 0,
                count,
            )
            
        except AuthenticationError:
            result = VerificationResult(
                success=False,
                http_status=401,
                result_count=0,
                expected_match_found=None,
                error_type="AuthenticationError",
                test_type="positive_match",
            )
            logger.warning("Positive match verification failed: authentication error")
            
        except Exception as exc:
            # Catch all other errors (TransientError, PermissionDenied, etc.)
            result = VerificationResult(
                success=False,
                http_status=None,
                result_count=0,
                expected_match_found=None,
                error_type=type(exc).__name__,
                test_type="positive_match",
            )
            logger.warning(
                "Positive match verification failed: %s",
                type(exc).__name__,
            )
        
        self.results.append(result)
        self._save_results()
        return result
    
    def verify_negative_match(self, unmatched_phrase: str) -> VerificationResult:
        """Verify that an intentionally unmatched phrase returns empty results.
        
        This confirms that the search correctly returns zero results for a
        phrase that should not match any messages.
        
        Args:
            unmatched_phrase: Phrase that should NOT match any messages
                            (e.g., random UUID, nonsense string)
        
        Returns:
            VerificationResult with:
            - success: True if search executed successfully
            - http_status: HTTP response code
            - result_count: Should be 0 for correct behavior
            - expected_match_found: False if result_count == 0 (correct)
            - error_type: None if successful
        """
        if not unmatched_phrase or len(unmatched_phrase.strip()) < 3:
            raise ValueError("Unmatched phrase must be at least 3 characters")
        
        if self.oauth is None or self.oauth.bundle is None:
            result = VerificationResult(
                success=False,
                http_status=None,
                result_count=0,
                expected_match_found=None,
                error_type="NOT_CONNECTED",
                test_type="negative_match",
            )
            self.results.append(result)
            logger.warning("Mailbox verification blocked: OAuth not connected")
            return result
        
        try:
            cleaned = " ".join(unmatched_phrase.replace("\\", " ").replace('"', " ").split())
            payload = self.oauth.graph_get(
                "/me/messages",
                {
                    "$search": f'"{cleaned[:200]}"',
                    "$top": "5",
                    "$select": "id",  # Only id field - no content
                },
                required_scope="Mail.Read",
            )
            
            raw = payload.get("value", [])
            count = len(raw) if isinstance(raw, list) else 0
            
            result = VerificationResult(
                success=True,
                http_status=200,
                result_count=count,
                expected_match_found=count == 0,  # Expect zero results
                error_type=None,
                test_type="negative_match",
            )
            
            logger.info(
                "Negative match verification completed: empty=%s, count=%d",
                count == 0,
                count,
            )
            
        except AuthenticationError:
            result = VerificationResult(
                success=False,
                http_status=401,
                result_count=0,
                expected_match_found=None,
                error_type="AuthenticationError",
                test_type="negative_match",
            )
            logger.warning("Negative match verification failed: authentication error")
            
        except Exception:
            # Catch all other errors (TransientError, PermissionDenied, etc.)
            result = VerificationResult(
                success=False,
                http_status=None,
                result_count=0,
                expected_match_found=None,
                error_type=type(exc).__name__,
                test_type="negative_match",
            )
            logger.warning(
                "Negative match verification failed: %s",
                type(exc).__name__,
            )
        
        self.results.append(result)
        self._save_results()
        return result
    
    def verify_with_synthetic_fixture(self, fixture_data: dict[str, Any]) -> VerificationResult:
        """Verify behavior using synthetic test fixtures.
        
        This is for automated tests that don't require live credentials.
        The fixture provides a mock Graph response.
        
        Args:
            fixture_data: Dict with keys:
                - http_status: Simulated HTTP status code
                - value: List of mock message objects (can be empty)
                - error: Optional error response
        
        Returns:
            VerificationResult marked as synthetic_fixture
        """
        http_status = fixture_data.get("http_status", 200)
        messages = fixture_data.get("value", [])
        error = fixture_data.get("error")
        
        if error:
            result = VerificationResult(
                success=False,
                http_status=http_status,
                result_count=0,
                expected_match_found=None,
                error_type="SYNTHETIC_ERROR",
                test_type="synthetic_fixture",
            )
        else:
            count = len(messages) if isinstance(messages, list) else 0
            result = VerificationResult(
                success=True,
                http_status=http_status,
                result_count=count,
                expected_match_found=count > 0,
                error_type=None,
                test_type="synthetic_fixture",
            )
        
        self.results.append(result)
        logger.info(
            "Synthetic fixture verification: status=%d, count=%d",
            http_status,
            result.result_count,
        )
        return result
    
    def _save_results(self) -> None:
        """Save privacy-safe results to file if path is configured."""
        if self.result_path is None:
            return
        
        try:
            self.result_path.parent.mkdir(parents=True, exist_ok=True)
            with self.result_path.open("w") as f:
                json.dump(
                    {
                        "results": [r.to_dict() for r in self.results],
                        "total_tests": len(self.results),
                    },
                    f,
                    indent=2,
                )
            logger.info("Verification results saved to %s", self.result_path)
        except OSError as exc:
            logger.warning("Could not save verification results: %s", exc)
    
    def summary(self) -> dict[str, Any]:
        """Generate summary statistics without exposing personal data.
        
        Returns:
            Dict with aggregate statistics:
            - total_tests: Total number of verification tests
            - successful_tests: Number that completed without errors
            - positive_matches_verified: Number of successful positive matches
            - negative_matches_verified: Number of successful negative matches
            - synthetic_fixtures: Number of synthetic fixture tests
            - live_mailbox_verified: Boolean - true if any live test succeeded
        """
        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        positive = sum(
            1 for r in self.results
            if r.test_type == "positive_match" and r.success and r.expected_match_found
        )
        negative = sum(
            1 for r in self.results
            if r.test_type == "negative_match" and r.success and r.expected_match_found
        )
        synthetic = sum(1 for r in self.results if r.test_type == "synthetic_fixture")
        
        # Live mailbox is verified if ANY live test (positive or negative) succeeded
        live_verified = any(
            r.success and r.test_type in {"positive_match", "negative_match"}
            for r in self.results
        )
        
        return {
            "total_tests": total,
            "successful_tests": successful,
            "positive_matches_verified": positive,
            "negative_matches_verified": negative,
            "synthetic_fixtures": synthetic,
            "live_mailbox_verified": live_verified,
        }
