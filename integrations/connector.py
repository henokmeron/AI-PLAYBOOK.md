"""Connector base class enforcing scopes, tenant boundary, read/write separation,
rate limiting, safe retries, approval for writes and audit for every call.

Subclasses implement ``authenticate`` and ``_perform``; they never bypass the
public ``read`` / ``write`` entry points.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .approvals import ApprovalService
from .audit import AuditLog
from .errors import ApprovalRequired, IntegrationError, InvalidRequest
from .resilience import RetryPolicy, TokenBucket, call_with_retry
from .secrets import SecretProvider
from .tenancy import Access, Scope, TenantContext


@dataclass(frozen=True)
class Operation:
    name: str
    access: Access
    scope: Scope
    idempotent: bool
    requires_approval: bool = False

    def __post_init__(self) -> None:
        if self.access is Access.WRITE and not self.requires_approval:
            raise ValueError("write operations must require approval in this framework")
        if self.scope.access is not self.access:
            raise ValueError("operation scope access must match the operation access")


class Connector:
    name = "connector"
    operations: dict[str, Operation] = {}

    def __init__(
        self,
        *,
        secrets: SecretProvider,
        audit: AuditLog,
        approvals: ApprovalService,
        rate_limiter: TokenBucket | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._secrets = secrets
        self.audit = audit
        self.approvals = approvals
        self._limiter = rate_limiter or TokenBucket(rate_per_second=5, burst=10)
        self._retry = retry_policy or RetryPolicy()
        self._sleep = sleep

    # --- to implement -----------------------------------------------------
    def authenticate(self, ctx: TenantContext) -> None:
        raise NotImplementedError

    def _perform(self, ctx: TenantContext, op: Operation, params: dict[str, Any]) -> Any:
        raise NotImplementedError

    # --- public API -------------------------------------------------------
    def read(self, ctx: TenantContext, operation: str, params: dict[str, Any] | None = None) -> Any:
        op = self._operation(operation, Access.READ)
        return self._run(ctx, op, params or {}, idempotent=op.idempotent)

    def request_write(self, ctx: TenantContext, operation: str, params: dict[str, Any], summary: str):
        op = self._operation(operation, Access.WRITE)
        ctx.require(op.scope)
        item = self.approvals.request(ctx, self.name, op.name, params, summary)
        self.audit.record(tenant_id=ctx.tenant_id, principal=ctx.principal, connector=self.name,
                          operation=op.name, access="write", outcome="approval_requested",
                          detail={"approval_id": item.approval_id, "params": params})
        return item

    def write(
        self, ctx: TenantContext, operation: str, params: dict[str, Any], *,
        approval_id: str | None, idempotency_key: str | None = None,
    ) -> Any:
        op = self._operation(operation, Access.WRITE)
        try:
            ctx.require(op.scope)
            self.approvals.consume(approval_id, ctx, self.name, op.name, params)
        except IntegrationError as exc:
            self._audit(ctx, op, "denied", exc, params)
            raise
        # A key is not enough. Retry only operations that declare themselves idempotent,
        # and only when the caller also supplies a key the provider can de-duplicate.
        # Sends, deletes, and other non-idempotent writes run once.
        may_retry = op.idempotent and bool(idempotency_key)
        call_params = dict(params, _idempotency_key=idempotency_key) if idempotency_key else params
        return self._run(ctx, op, call_params, idempotent=may_retry, checked=True)

    # --- internals --------------------------------------------------------
    def _operation(self, name: str, access: Access) -> Operation:
        op = self.operations.get(name)
        if op is None:
            raise InvalidRequest(f"unknown operation {self.name}.{name}")
        if op.access is not access:
            raise InvalidRequest(f"{self.name}.{name} is a {op.access.value} operation")
        return op

    def _audit(self, ctx: TenantContext, op: Operation, outcome: str, exc: IntegrationError | None,
               params: dict[str, Any], extra: dict[str, Any] | None = None) -> None:
        detail = {"params": {k: v for k, v in params.items() if not k.startswith("_")}}
        if extra:
            detail.update(extra)
        if exc is not None:
            detail["error"] = exc.message
        self.audit.record(tenant_id=ctx.tenant_id, principal=ctx.principal, connector=self.name,
                          operation=op.name, access=op.access.value, outcome=outcome,
                          error_category=exc.category if exc else None, detail=detail)

    def _run(self, ctx: TenantContext, op: Operation, params: dict[str, Any], *, idempotent: bool,
             checked: bool = False) -> Any:
        retries: list[str] = []
        try:
            if not checked:
                ctx.require(op.scope)
            self.authenticate(ctx)

            def attempt() -> Any:
                self._limiter.acquire(f"{ctx.tenant_id}:{self.name}")
                return self._perform(ctx, op, params)

            result = call_with_retry(
                attempt, idempotent=idempotent, policy=self._retry, sleep=self._sleep,
                on_retry=lambda n, e, w: retries.append(e.category),
            )
        except IntegrationError as exc:
            self._audit(ctx, op, "denied" if exc.category in {"permission_denied", "tenant_boundary",
                                                              "approval_required"} else "error",
                        exc, params, {"retries": retries})
            raise
        self._audit(ctx, op, "ok", None, params, {"retries": retries})
        return result


__all__ = ["ApprovalRequired", "Connector", "Operation"]
