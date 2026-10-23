"""Redact sensitive information from diagnostic payloads.

Before a device report is uploaded, strip usernames, home paths, tokens,
IP addresses (optional), and other PII. Keep enough context for diagnosis.
Unit tests verify that common sensitive patterns are removed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


_USERNAME_PATTERNS = [
    re.compile(r"C:\\Users\\([^\\]+)", re.IGNORECASE),
    re.compile(r"/home/([^/]+)"),
    re.compile(r"/Users/([^/]+)"),
    re.compile(r"\\\\([^\\]+)\\", re.IGNORECASE),
]

_TOKEN_PATTERN = re.compile(
    r"\b[A-Za-z0-9_-]{32,}\b"
)

_GUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

_SID_PATTERN = re.compile(
    r"\bS-1-[0-9-]+\b"
)

_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
)

_IP_PATTERN = re.compile(
    r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
)


def redact_text(text: str, *, redact_ips: bool = False) -> str:
    """Redact sensitive patterns from a string.
    
    Replaces usernames, tokens, GUIDs, SIDs, emails, and optionally IP addresses
    with generic placeholders like <USERNAME>, <TOKEN>, etc.
    
    Args:
        text: Text to redact
        redact_ips: If True, also redact IP addresses (may hide useful network info)
    
    Returns:
        Redacted text with sensitive values replaced
    """
    if not isinstance(text, str):
        return text

    result = text

    home_dir = str(Path.home())
    if home_dir and len(home_dir) > 3:
        result = result.replace(home_dir, "<HOME>")

    for pattern in _USERNAME_PATTERNS:
        result = pattern.sub(lambda m: m.group(0).replace(m.group(1), "<USERNAME>"), result)

    current_user = os.environ.get("USERNAME") or os.environ.get("USER")
    if current_user and len(current_user) > 0:
        result = result.replace(current_user, "<USERNAME>")

    result = _EMAIL_PATTERN.sub("<EMAIL>", result)

    result = _SID_PATTERN.sub("<SID>", result)

    result = _GUID_PATTERN.sub("<GUID>", result)

    result = _TOKEN_PATTERN.sub(lambda m: "<TOKEN>" if len(m.group(0)) > 40 else m.group(0), result)

    if redact_ips:
        result = _IP_PATTERN.sub("<IP>", result)

    return result


def redact_check_summary(check: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive fields from a single diagnostic check summary.
    
    Args:
        check: Check dictionary with procedure_id, summary, etc.
    
    Returns:
        New check dictionary with redacted summary and detail fields
    """
    if not isinstance(check, dict):
        return check

    redacted = dict(check)

    if "summary" in redacted and isinstance(redacted["summary"], str):
        redacted["summary"] = redact_text(redacted["summary"])

    if "detail" in redacted and isinstance(redacted["detail"], str):
        redacted["detail"] = redact_text(redacted["detail"])

    return redacted


def redact_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Redact sensitive information from all checks in a report.
    
    Args:
        checks: List of check dictionaries
    
    Returns:
        New list with redacted checks
    """
    if not isinstance(checks, list):
        return checks

    return [redact_check_summary(check) for check in checks]


def redact_report_before_upload(report: dict[str, Any]) -> dict[str, Any]:
    """Redact all sensitive fields in a device report before submission.
    
    This is the main entry point. Call this before sending a report to the server.
    
    Args:
        report: Complete device report with diagnostics and checks
    
    Returns:
        New report dictionary with sensitive data redacted
    """
    if not isinstance(report, dict):
        return report

    redacted = dict(report)

    if "os_version" in redacted and isinstance(redacted["os_version"], str):
        redacted["os_version"] = redact_text(redacted["os_version"])

    if "checks" in redacted and isinstance(redacted["checks"], list):
        redacted["checks"] = redact_checks(redacted["checks"])

    return redacted


def is_sensitive_looking(text: str) -> bool:
    """Check if text appears to contain sensitive information (for testing).
    
    Returns True if any sensitive pattern is detected.
    """
    if not isinstance(text, str):
        return False

    if any(pattern.search(text) for pattern in _USERNAME_PATTERNS):
        return True

    if _EMAIL_PATTERN.search(text):
        return True

    if _SID_PATTERN.search(text):
        return True

    home_dir = str(Path.home())
    if home_dir and len(home_dir) > 3 and home_dir in text:
        return True

    current_user = os.environ.get("USERNAME") or os.environ.get("USER")
    if current_user and len(current_user) > 0 and current_user in text:
        return True

    return False
