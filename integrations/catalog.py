"""Connector catalog the agent can discover without hard-coding each service.

Operations declare an effect, a scope, and schemas. Consequential and
reversible changes require an exact approval before any provider call.
Missing permission removes the operation from the tool list; it is not offered
and then denied later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from agents.schema import ValidationError, check_schema, validate

from .errors import ApprovalRequired, AuthenticationError, InvalidRequest, PermissionDenied
from .tenancy import TenantContext


class Effect(str, Enum):
    READ = "read"
    DRAFT = "draft"
    REVERSIBLE = "reversible"
    CONSEQUENTIAL = "consequential"


_APPROVED_EFFECTS = {Effect.REVERSIBLE, Effect.CONSEQUENTIAL}


@dataclass(frozen=True)
class OperationSpec:
    name: str
    summary: str
    effect: Effect
    scope: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    provider_permissions: tuple[str, ...]
    tool_name: str
    requires_approval: bool = False
    idempotent: bool = True

    def __post_init__(self) -> None:
        check_schema(self.input_schema)
        check_schema(self.output_schema)
        if self.input_schema.get("type") != "object":
            raise ValueError(f"{self.name} input schema must be an object")
        if self.effect in _APPROVED_EFFECTS and not self.requires_approval:
            raise ValueError(f"{self.name} changes external state and must require approval")
        if self.effect in {Effect.READ, Effect.DRAFT} and self.requires_approval:
            raise ValueError(f"{self.name} is not an external change and must not require approval")


@dataclass(frozen=True)
class ConnectorSpec:
    connector_id: str
    version: str
    service: str
    summary: str
    auth: str
    operations: tuple[OperationSpec, ...]

    def operation(self, name: str) -> OperationSpec:
        for item in self.operations:
            if item.name == name or item.tool_name == name:
                return item
        raise InvalidRequest(f"unknown operation {self.connector_id}.{name}")


@dataclass
class ConnectionRecord:
    tenant_id: str
    connector_id: str
    connected: bool = False
    account: str | None = None
    granted_scopes: frozenset[str] = field(default_factory=frozenset)
    detail: str = "Connect a work or school account before mail, files, Teams, or calendar can be used."


class Catalog:
    def __init__(self, specs: list[ConnectorSpec], performer: Callable[[str, str, dict[str, Any]], Any]) -> None:
        self._specs = {item.connector_id: item for item in specs}
        self._performer = performer
        self.connections: dict[tuple[str, str], ConnectionRecord] = {}

    def spec(self, connector_id: str) -> ConnectorSpec:
        try:
            return self._specs[connector_id]
        except KeyError as exc:
            raise InvalidRequest(f"unknown connector {connector_id}") from exc

    def connection(self, tenant_id: str, connector_id: str) -> ConnectionRecord:
        self.spec(connector_id)
        key = (tenant_id, connector_id)
        record = self.connections.get(key)
        if record is None:
            record = ConnectionRecord(tenant_id, connector_id)
            self.connections[key] = record
        return record

    def granted_scopes(self, ctx: TenantContext, connector_id: str) -> frozenset[str]:
        record = self.connection(ctx.tenant_id, connector_id)
        if not record.connected:
            return frozenset()
        return record.granted_scopes

    def visible_operations(self, ctx: TenantContext) -> list[tuple[ConnectorSpec, OperationSpec]]:
        visible: list[tuple[ConnectorSpec, OperationSpec]] = []
        for spec in self._specs.values():
            granted = self.granted_scopes(ctx, spec.connector_id)
            for operation in spec.operations:
                if operation.scope in granted:
                    visible.append((spec, operation))
        return visible

    def describe(self, tenant_id: str) -> list[dict[str, Any]]:
        rows = []
        for spec in self._specs.values():
            record = self.connection(tenant_id, spec.connector_id)
            rows.append({
                "connector_id": spec.connector_id,
                "version": spec.version,
                "service": spec.service,
                "summary": spec.summary,
                "auth": spec.auth,
                "connected": record.connected,
                "account": record.account if record.connected else None,
                "detail": record.detail,
                "operations": [
                    {
                        "name": op.name,
                        "tool_name": op.tool_name,
                        "summary": op.summary,
                        "effect": op.effect.value,
                        "scope": op.scope,
                        "requires_approval": op.requires_approval,
                        "available": record.connected and op.scope in record.granted_scopes,
                        "provider_permissions": list(op.provider_permissions),
                    }
                    for op in spec.operations
                ],
            })
        return rows

    def execute(
        self,
        ctx: TenantContext,
        connector_id: str,
        operation: str,
        params: dict[str, Any],
        *,
        authorised: bool = False,
    ) -> Any:
        spec = self.spec(connector_id)
        op = spec.operation(operation)
        if not isinstance(params, dict):
            raise InvalidRequest("operation arguments must be an object")
        try:
            validate(params, op.input_schema)
        except ValidationError as exc:
            raise InvalidRequest(str(exc)) from exc
        record = self.connection(ctx.tenant_id, connector_id)
        if not record.connected:
            raise AuthenticationError(f"{spec.service} is not connected. No request was sent.")
        if op.scope not in record.granted_scopes:
            raise PermissionDenied(f"missing scope {op.scope}")
        if op.requires_approval and not authorised:
            raise ApprovalRequired(
                f"{connector_id}.{op.name} requires approval of these exact arguments"
            )
        return self._performer(connector_id, op.name, params)
