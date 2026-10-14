"""Redaction helpers for execution records, audit trails and error messages.

Redaction is defence in depth: callers must still avoid putting secrets into
prompts or tool arguments. Values are redacted by key name and by pattern.
"""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"
# Whole-segment match so "access_token" is redacted but "max_tokens" is not.
SENSITIVE_KEY_RE = re.compile(
    r"(^|[_\-.])(pass(word|wd)?|secret|token|api[_-]?key|apikey|authori[sz]ation|bearer|"
    r"cookie|credentials?|private[_-]?key|signature)($|[_\-.])",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\brpa_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[=:]\s*[^\s,;\"']{6,}"),
)
JSON_SECRET_FIELD_RE = re.compile(
    r'(?i)("[a-z0-9_\-]*(?:pass(?:word|wd)?|secret|token|api[_-]?key|apikey|authori[sz]ation|'
    r'credentials?|private[_-]?key|signature)"\s*:\s*)"(?:[^"\\]|\\.)*"'
)
MAX_DEPTH = 20


class SecretRegistry:
    """Exact secret values to scrub (for example the gateway key once loaded)."""

    def __init__(self) -> None:
        self._values: set[str] = set()

    def add(self, value: str) -> None:
        if isinstance(value, str) and len(value) >= 8:
            self._values.add(value)

    def values(self) -> frozenset[str]:
        return frozenset(self._values)


def redact_text(text: str, known_secrets: frozenset[str] | set[str] = frozenset()) -> str:
    for secret in sorted(known_secrets, key=len, reverse=True):
        if secret and secret in text:
            text = text.replace(secret, REDACTED)
    text = JSON_SECRET_FIELD_RE.sub(lambda m: m.group(1) + f'"{REDACTED}"', text)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact(value: Any, known_secrets: frozenset[str] | set[str] = frozenset(), _depth: int = 0) -> Any:
    """Return a redacted deep copy of JSON-like data."""
    if _depth > MAX_DEPTH:
        return REDACTED
    if isinstance(value, str):
        return redact_text(value, known_secrets)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if SENSITIVE_KEY_RE.search(key_text):
                out[key_text] = REDACTED
            else:
                out[key_text] = redact(item, known_secrets, _depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(item, known_secrets, _depth + 1) for item in value]
    return value
