"""Connector error taxonomy. ``retryable`` is the only signal retry logic trusts."""
from __future__ import annotations


class IntegrationError(Exception):
    category = "integration_error"
    retryable = False

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class AuthenticationError(IntegrationError):
    """Credentials missing, expired or rejected. Re-authorise; do not retry blindly."""
    category = "authentication"


class PermissionDenied(IntegrationError):
    """The caller lacks a scope or the provider refused access."""
    category = "permission_denied"


class TenantBoundaryViolation(PermissionDenied):
    category = "tenant_boundary"


class ApprovalRequired(IntegrationError):
    category = "approval_required"


class NotFound(IntegrationError):
    category = "not_found"


class Conflict(IntegrationError):
    category = "conflict"


class InvalidRequest(IntegrationError):
    category = "invalid_request"


class RateLimited(IntegrationError):
    category = "rate_limited"
    retryable = True


class TransientError(IntegrationError):
    """Timeouts, 5xx, connection resets."""
    category = "transient"
    retryable = True


class WebhookVerificationError(IntegrationError):
    category = "webhook_verification"


class ProviderError(IntegrationError):
    """Unexpected provider response; not retried."""
    category = "provider_error"


def classify_http_status(status: int, retry_after: float | None = None) -> IntegrationError:
    """Map an HTTP status from a provider API to the taxonomy."""
    if status == 401:
        return AuthenticationError("provider rejected credentials (401)")
    if status == 403:
        return PermissionDenied("provider denied access (403)")
    if status == 404:
        return NotFound("resource not found (404)")
    if status in (409, 412):
        return Conflict(f"conflict ({status})")
    if status == 429:
        return RateLimited("provider rate limit (429)", retry_after=retry_after)
    if status in (408, 500, 502, 503, 504):
        return TransientError(f"provider temporarily unavailable ({status})", retry_after=retry_after)
    if 400 <= status < 500:
        return InvalidRequest(f"provider rejected request ({status})")
    return ProviderError(f"unexpected provider status ({status})")
