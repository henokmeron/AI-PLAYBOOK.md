"""Rate limiting, retry with backoff, and bounded pagination."""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator, TypeVar

from .errors import IntegrationError, RateLimited

T = TypeVar("T")


class TokenBucket:
    """Per-key token bucket (key = tenant + connector) with an injectable clock."""

    def __init__(self, rate_per_second: float, burst: int, clock: Callable[[], float] = time.monotonic) -> None:
        if rate_per_second <= 0 or burst < 1:
            raise ValueError("rate and burst must be positive")
        self.rate = rate_per_second
        self.burst = burst
        self._clock = clock
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            tokens, last = self._state.get(key, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens < 1:
                wait = (1 - tokens) / self.rate
                self._state[key] = (tokens, now)
                raise RateLimited("local rate limit reached", retry_after=wait)
            self._state[key] = (tokens - 1, now)


@dataclass
class RetryPolicy:
    max_attempts: int = 4
    base_delay: float = 0.5
    max_delay: float = 20.0
    jitter: float = 0.2

    def delay(self, attempt: int, retry_after: float | None, rng: random.Random) -> float:
        if retry_after is not None:
            return min(self.max_delay, max(0.0, retry_after))
        raw = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        return raw * (1 + rng.uniform(-self.jitter, self.jitter))


def call_with_retry(
    fn: Callable[[], T],
    *,
    idempotent: bool,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    on_retry: Callable[[int, IntegrationError, float], None] | None = None,
) -> T:
    """Retry only retryable errors, and only when the operation is idempotent."""
    policy = policy or RetryPolicy()
    rng = rng or random.Random()
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except IntegrationError as exc:
            if not (idempotent and exc.retryable) or attempt >= policy.max_attempts:
                raise
            wait = policy.delay(attempt, exc.retry_after, rng)
            if on_retry is not None:
                on_retry(attempt, exc, wait)
            sleep(wait)


@dataclass
class Page:
    items: list[Any]
    next_cursor: str | None = None


def iterate_pages(
    fetch: Callable[[str | None], Page],
    *,
    max_pages: int = 20,
    max_items: int = 1000,
) -> Iterator[Any]:
    """Follow cursors with hard bounds and cycle detection."""
    cursor: str | None = None
    seen: set[str] = set()
    yielded = 0
    for _ in range(max_pages):
        page = fetch(cursor)
        for item in page.items:
            if yielded >= max_items:
                return
            yielded += 1
            yield item
        if not page.next_cursor:
            return
        if page.next_cursor in seen:
            raise IntegrationError("pagination cursor repeated (provider loop)")
        seen.add(page.next_cursor)
        cursor = page.next_cursor
