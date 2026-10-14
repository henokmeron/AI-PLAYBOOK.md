"""Integration framework (prototype). No real provider connector is implemented.

See docs/integrations/assessment.md for the provider evaluation.
"""
from __future__ import annotations

from .approvals import ApprovalService
from .audit import AuditLog
from .connector import Connector, Operation
from .errors import IntegrationError
from .resilience import Page, RetryPolicy, TokenBucket, call_with_retry, iterate_pages
from .secrets import EnvSecretProvider, FileSecretProvider, Secret
from .tenancy import Access, Scope, TenantContext
from .webhooks import WebhookVerifier

__all__ = [
    "Access", "ApprovalService", "AuditLog", "Connector", "EnvSecretProvider", "FileSecretProvider",
    "IntegrationError", "Operation", "Page", "RetryPolicy", "Scope", "Secret", "TenantContext",
    "TokenBucket", "WebhookVerifier", "call_with_retry", "iterate_pages",
]
