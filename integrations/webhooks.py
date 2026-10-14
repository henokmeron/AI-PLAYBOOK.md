"""Generic HMAC-SHA256 webhook verification with timestamp tolerance and replay protection.

Signed message = ``f"{timestamp}.{raw_body}"``. Real providers differ (Microsoft
Graph uses validation tokens + clientState, Xero uses base64 HMAC of the body,
Google uses channel tokens / Pub/Sub JWTs); provider adapters must map onto this
or implement their scheme, but the properties below are required in every case.
"""
from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import OrderedDict
from typing import Callable

from .errors import WebhookVerificationError
from .secrets import Secret

MAX_BODY_BYTES = 1_048_576


class ReplayCache:
    def __init__(self, capacity: int = 10_000) -> None:
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._capacity = capacity
        self._lock = threading.Lock()

    def check_and_add(self, key: str) -> bool:
        with self._lock:
            if key in self._seen:
                return False
            self._seen[key] = None
            if len(self._seen) > self._capacity:
                self._seen.popitem(last=False)
            return True


def sign(secret: Secret, timestamp: int, body: bytes) -> str:
    message = str(timestamp).encode() + b"." + body
    return "sha256=" + hmac.new(secret.reveal().encode(), message, hashlib.sha256).hexdigest()


class WebhookVerifier:
    def __init__(
        self,
        secret: Secret,
        *,
        tolerance_seconds: int = 300,
        replay_cache: ReplayCache | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret = secret
        self._tolerance = tolerance_seconds
        self._replay = replay_cache or ReplayCache()
        self._clock = clock

    def verify(self, body: bytes, signature: str | None, timestamp: str | None, delivery_id: str | None) -> None:
        if len(body) > MAX_BODY_BYTES:
            raise WebhookVerificationError("webhook body too large")
        if not signature or not timestamp or not delivery_id:
            raise WebhookVerificationError("missing signature, timestamp or delivery id")
        try:
            ts = int(timestamp)
        except ValueError:
            raise WebhookVerificationError("invalid timestamp") from None
        if abs(self._clock() - ts) > self._tolerance:
            raise WebhookVerificationError("timestamp outside tolerance")
        expected = sign(self._secret, ts, body)
        if not hmac.compare_digest(expected.encode(), signature.strip().encode()):
            raise WebhookVerificationError("signature mismatch")
        if not self._replay.check_and_add(delivery_id):
            raise WebhookVerificationError("replayed delivery")
