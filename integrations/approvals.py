"""Approval gate for write actions.

An approval is bound to tenant, connector, operation and a hash of the exact
parameters, expires, and can be consumed once. By default the approver must be
a different principal from the requester (four-eyes).
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from .errors import ApprovalRequired, PermissionDenied
from .tenancy import TenantContext


def payload_hash(params: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class ApprovalRequest:
    approval_id: str
    tenant_id: str
    requester: str
    connector: str
    operation: str
    params_hash: str
    summary: str
    created_at: float
    expires_at: float
    status: str = "pending"
    approver: str | None = None


class ApprovalService:
    def __init__(
        self, *, ttl_seconds: float = 900, require_distinct_approver: bool = True,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._requests: dict[str, ApprovalRequest] = {}
        self._ttl = ttl_seconds
        self._distinct = require_distinct_approver
        self._clock = clock
        self._lock = threading.Lock()

    def request(self, ctx: TenantContext, connector: str, operation: str, params: dict[str, Any], summary: str) -> ApprovalRequest:
        now = self._clock()
        item = ApprovalRequest(
            approval_id=secrets.token_urlsafe(16), tenant_id=ctx.tenant_id, requester=ctx.principal,
            connector=connector, operation=operation, params_hash=payload_hash(params),
            summary=summary[:500], created_at=now, expires_at=now + self._ttl,
        )
        with self._lock:
            self._requests[item.approval_id] = item
        return item

    def decide(self, approval_id: str, approver_ctx: TenantContext, approve: bool) -> ApprovalRequest:
        with self._lock:
            item = self._requests.get(approval_id)
            if item is None or item.status != "pending":
                raise ApprovalRequired("approval request not found or already decided")
            if approver_ctx.tenant_id != item.tenant_id:
                raise PermissionDenied("approver belongs to a different tenant")
            if self._distinct and approver_ctx.principal == item.requester:
                raise PermissionDenied("requester cannot approve their own write action")
            if self._clock() > item.expires_at:
                item.status = "expired"
                raise ApprovalRequired("approval request expired")
            item.status = "approved" if approve else "denied"
            item.approver = approver_ctx.principal
            return item

    def consume(self, approval_id: str | None, ctx: TenantContext, connector: str, operation: str, params: dict[str, Any]) -> ApprovalRequest:
        if not approval_id:
            raise ApprovalRequired(f"{connector}.{operation} requires an approved request")
        with self._lock:
            item = self._requests.get(approval_id)
            if item is None:
                raise ApprovalRequired("unknown approval")
            if item.tenant_id != ctx.tenant_id or item.connector != connector or item.operation != operation:
                raise ApprovalRequired("approval does not match this action")
            if item.params_hash != payload_hash(params):
                raise ApprovalRequired("parameters changed after approval")
            if self._clock() > item.expires_at:
                item.status = "expired"
                raise ApprovalRequired("approval expired")
            if item.status != "approved":
                raise ApprovalRequired(f"approval is {item.status}")
            item.status = "consumed"
            return item
