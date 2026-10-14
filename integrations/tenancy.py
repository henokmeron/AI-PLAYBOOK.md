"""Tenant boundary and least-privilege scope model."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .errors import PermissionDenied, TenantBoundaryViolation

TENANT_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,62}\Z")
SCOPE_RE = re.compile(r"[a-z][a-z0-9_.]{1,63}:(read|write)\Z")


class Access(str, Enum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class Scope:
    """``<resource>:<read|write>``, e.g. ``documents:read``. Write never implies read."""
    resource: str
    access: Access

    @classmethod
    def parse(cls, text: str) -> "Scope":
        if not isinstance(text, str) or not SCOPE_RE.fullmatch(text):
            raise ValueError(f"invalid scope {text!r}")
        resource, access = text.split(":")
        return cls(resource, Access(access))

    def __str__(self) -> str:
        return f"{self.resource}:{self.access.value}"


@dataclass(frozen=True)
class TenantContext:
    """Who is acting, for which tenant, with which granted scopes."""
    tenant_id: str
    principal: str
    scopes: frozenset[Scope] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not TENANT_RE.fullmatch(self.tenant_id):
            raise ValueError("tenant_id must be a lowercase slug")
        if not self.principal or len(self.principal) > 128:
            raise ValueError("principal is required")

    @classmethod
    def create(cls, tenant_id: str, principal: str, scopes: list[str]) -> "TenantContext":
        return cls(tenant_id, principal, frozenset(Scope.parse(s) for s in scopes))

    def require(self, scope: Scope) -> None:
        if scope not in self.scopes:
            raise PermissionDenied(f"missing scope {scope}")

    def require_tenant(self, resource_tenant: str) -> None:
        if resource_tenant != self.tenant_id:
            raise TenantBoundaryViolation("resource belongs to a different tenant")
