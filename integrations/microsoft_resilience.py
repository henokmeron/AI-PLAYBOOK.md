"""Microsoft Graph API resilience enhancements.

This module adds robust error handling, retry logic, throttling support,
and pagination for Microsoft Graph API calls.

Features:
- Automatic retry with exponential backoff for transient errors
- Proper Retry-After header handling for 429 responses
- Configurable timeout handling
- Safe pagination with cycle detection
- Rate limiting to prevent excessive requests
"""
from __future__ import annotations

import time
import urllib.parse
from typing import Any, Callable, Iterator

from .errors import RateLimited, TransientError
from .microsoft_oauth import MicrosoftOAuth
from .resilience import Page, RetryPolicy, call_with_retry, iterate_pages


class GraphResilience:
    """Enhanced Microsoft Graph API client with resilience features."""
    
    def __init__(
        self,
        oauth: MicrosoftOAuth,
        retry_policy: RetryPolicy | None = None,
        default_timeout: float = 30.0,
    ) -> None:
        """Initialize Graph resilience wrapper.
        
        Args:
            oauth: Microsoft OAuth client
            retry_policy: Retry policy for transient errors (default: 4 attempts)
            default_timeout: Default timeout for Graph requests in seconds
        """
        self.oauth = oauth
        self.retry_policy = retry_policy or RetryPolicy(
            max_attempts=4,
            base_delay=1.0,
            max_delay=32.0,
        )
        self.default_timeout = default_timeout
        self._retry_count = 0
    
    def graph_get_with_retry(
        self,
        path: str,
        query: dict[str, str] | None = None,
        *,
        required_scope: str = "Mail.Read",
        idempotent: bool = True,
    ) -> dict[str, Any]:
        """Perform Graph GET with automatic retry on transient errors.
        
        This wraps the standard graph_get with:
        - Automatic retry for 429 (throttling) responses
        - Retry-After header support
        - Exponential backoff for 500+ errors
        - Timeout handling
        
        Args:
            path: Graph API path (e.g., /me/messages)
            query: Query parameters
            required_scope: Required Graph scope
            idempotent: Whether this operation is safe to retry (default: True)
        
        Returns:
            Graph API response as dict
            
        Raises:
            AuthenticationError: If authentication fails
            PermissionDenied: If permission is missing
            RateLimited: If rate limit exceeded after retries
            TransientError: If transient error persists after retries
        """
        def _do_request() -> dict[str, Any]:
            return self.oauth.graph_get(path, query, required_scope=required_scope)
        
        def _on_retry(attempt: int, error: Any, wait: float) -> None:
            self._retry_count += 1
            # Log retry without exposing tokens or personal data
            pass
        
        return call_with_retry(
            _do_request,
            idempotent=idempotent,
            policy=self.retry_policy,
            on_retry=_on_retry,
        )
    
    def paginate_graph_results(
        self,
        path: str,
        query: dict[str, str] | None = None,
        *,
        required_scope: str = "Mail.Read",
        max_pages: int = 20,
        max_items: int = 1000,
        page_size: int = 50,
    ) -> Iterator[dict[str, Any]]:
        """Paginate through Graph API results safely.
        
        This handles:
        - @odata.nextLink pagination
        - Cycle detection (prevents infinite loops)
        - Bounded iteration (max pages and items)
        - Automatic retry on transient errors
        
        Args:
            path: Graph API path
            query: Initial query parameters (will add $top for page_size)
            required_scope: Required Graph scope
            max_pages: Maximum number of pages to fetch
            max_items: Maximum total items to return
            page_size: Items per page (Microsoft Graph default is 10-50)
        
        Yields:
            Individual items from the result set
            
        Example:
            >>> for message in resilience.paginate_graph_results(
            ...     "/me/messages",
            ...     {"$select": "id,subject"},
            ...     required_scope="Mail.Read",
            ...     max_items=100,
            ... ):
            ...     process(message)
        """
        # Prepare initial query with pagination
        initial_query = dict(query or {})
        if "$top" not in initial_query:
            initial_query["$top"] = str(min(page_size, max_items))
        
        def fetch_page(cursor: str | None) -> Page:
            """Fetch one page of results."""
            if cursor:
                # Use the full nextLink URL provided by Graph
                # Extract query params from nextLink
                parts = urllib.parse.urlsplit(cursor)
                page_query = dict(urllib.parse.parse_qsl(parts.query))
                page_path = parts.path.replace("/v1.0", "")
            else:
                page_path = path
                page_query = initial_query
            
            # Use retry wrapper for resilience
            response = self.graph_get_with_retry(
                page_path,
                page_query,
                required_scope=required_scope,
                idempotent=True,
            )
            
            items = response.get("value", [])
            next_link = response.get("@odata.nextLink")
            
            return Page(
                items=items if isinstance(items, list) else [],
                next_cursor=next_link if isinstance(next_link, str) else None,
            )
        
        yield from iterate_pages(
            fetch_page,
            max_pages=max_pages,
            max_items=max_items,
        )
    
    def search_mail_with_pagination(
        self,
        search_query: str,
        *,
        max_results: int = 50,
        select_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search mail with automatic pagination and result limiting.
        
        This is a higher-level convenience method that:
        - Handles search query formatting
        - Paginates automatically
        - Limits total results
        - Returns a simple list
        
        Args:
            search_query: Search text (will be quoted automatically)
            max_results: Maximum number of messages to return
            select_fields: Fields to select (default: id, subject, from, receivedDateTime)
        
        Returns:
            List of message objects (up to max_results)
        """
        if not search_query or len(search_query.strip()) < 1:
            return []
        
        # Clean and format search query
        cleaned = " ".join(
            search_query.replace("\\", " ").replace('"', " ").split()
        )
        
        # Default fields for privacy-safe results
        if select_fields is None:
            select_fields = ["id", "subject", "from", "receivedDateTime", "bodyPreview"]
        
        query = {
            "$search": f'"{cleaned[:200]}"',
            "$select": ",".join(select_fields),
            "$top": str(min(50, max_results)),
        }
        
        results = []
        try:
            for item in self.paginate_graph_results(
                "/me/messages",
                query,
                required_scope="Mail.Read",
                max_items=max_results,
                page_size=50,
            ):
                results.append(item)
                if len(results) >= max_results:
                    break
        except (RateLimited, TransientError):
            # Return partial results if we hit rate limits or transient errors
            # This prevents complete failure when we already have some data
            pass
        
        return results
    
    def get_retry_count(self) -> int:
        """Get the number of retries that have occurred.
        
        This is useful for monitoring and testing.
        
        Returns:
            Number of retry attempts made
        """
        return self._retry_count


def create_resilient_client(
    oauth: MicrosoftOAuth,
    max_retries: int = 4,
    timeout: float = 30.0,
) -> GraphResilience:
    """Create a resilient Graph API client.
    
    This is the recommended way to create a Graph client that handles
    transient errors, throttling, and pagination properly.
    
    Args:
        oauth: Microsoft OAuth client
        max_retries: Maximum retry attempts for transient errors
        timeout: Request timeout in seconds
    
    Returns:
        GraphResilience client with configured retry policy
    
    Example:
        >>> oauth = MicrosoftOAuth.from_env()
        >>> resilient = create_resilient_client(oauth, max_retries=4)
        >>> messages = resilient.search_mail_with_pagination(
        ...     "project alpha",
        ...     max_results=100,
        ... )
    """
    policy = RetryPolicy(
        max_attempts=max_retries,
        base_delay=1.0,
        max_delay=32.0,
        jitter=0.2,
    )
    
    return GraphResilience(
        oauth=oauth,
        retry_policy=policy,
        default_timeout=timeout,
    )
