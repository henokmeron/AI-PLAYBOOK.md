"""Microsoft 365 document tools that call the connector catalog only.

Write operations that are not in the catalog return a not-approved result.
This module does not start a shell, write a local file, or call Graph itself.
"""
from __future__ import annotations

from typing import Any

from agents.redaction import redact_text
from agents.tools import Tool, ToolError, ToolInputError, ToolPermissionError
from integrations.catalog import Catalog, Effect
from integrations.errors import ApprovalRequired, AuthenticationError, IntegrationError, InvalidRequest, PermissionDenied
from integrations.tenancy import TenantContext

_WRITE_EFFECTS = {Effect.DRAFT, Effect.REVERSIBLE, Effect.CONSEQUENTIAL}
_DROPPED = frozenset({
    "body", "content", "text", "data", "file", "bytes", "token", "access_token",
    "refresh_token", "password", "secret", "preview",
})

_OUTPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "executed", "detail"],
    "properties": {
        "status": {"type": "string", "enum": ["not-approved", "catalog"]},
        "executed": {"type": "boolean"},
        "detail": {"type": "string", "maxLength": 300},
    },
}

_NAME = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name"],
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 200},
    },
}
_UPDATE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["item_id", "name"],
    "properties": {
        "item_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "name": {"type": "string", "minLength": 1, "maxLength": 200},
    },
}

WRITES: tuple[tuple[str, str, dict[str, Any]], ...] = (
    (
        "create_document",
        "Create a Microsoft 365 document through the catalog. Refused when the catalog has no approved write.",
        _NAME,
    ),
    (
        "update_document",
        "Update a Microsoft 365 document through the catalog. Refused when the catalog has no approved write.",
        _UPDATE,
    ),
)


def _plain(value: Any, limit: int) -> str:
    return redact_text(" ".join(str(value).replace("\r", " ").replace("\n", " ").split()))[:limit]


def _lookup(catalog: Catalog, name: str) -> Any | None:
    try:
        return catalog.spec("microsoft365").operation(name)
    except InvalidRequest:
        return None


def _approved_write(operation: Any | None) -> bool:
    if operation is None:
        return False
    if getattr(operation, "evidence", "unavailable") == "unavailable":
        return False
    return getattr(operation, "effect", None) in _WRITE_EFFECTS


def _refused(name: str) -> dict[str, Any]:
    return {
        "status": "not-approved",
        "executed": False,
        "detail": _plain(
            f"not-approved: microsoft365.{name} is not an approved catalog write. No request was sent.",
            300,
        ),
    }


def _from_catalog(result: Any) -> dict[str, Any]:
    status = "catalog returned"
    if isinstance(result, dict):
        kept = {
            key: value
            for key, value in result.items()
            if key not in _DROPPED and not str(key).casefold().endswith("token")
        }
        status = kept.get("status") or kept.get("detail") or "catalog returned"
    return {
        "status": "catalog",
        "executed": True,
        "detail": _plain(status, 300),
    }


def microsoft_document_tools(catalog: Catalog, ctx: TenantContext) -> list[Tool]:
    tools: list[Tool] = []
    for name, summary, schema in WRITES:
        operation = _lookup(catalog, name)
        approved = _approved_write(operation)
        requires = bool(approved and getattr(operation, "requires_approval", False))
        grant: dict[str, Any] = {"call_id": None, "arguments": None}

        def handler(
            arguments: dict[str, Any],
            name: str = name,
            requires: bool = requires,
            grant: dict[str, Any] = grant,
        ) -> dict[str, Any]:
            current = _lookup(catalog, name)
            if not _approved_write(current):
                return _refused(name)
            authorised = False
            if requires:
                from integrations.approvals import payload_hash

                expected = grant.get("arguments")
                authorised = (
                    isinstance(grant.get("call_id"), str)
                    and isinstance(expected, dict)
                    and payload_hash(expected) == payload_hash(arguments)
                )
                grant["call_id"] = None
                grant["arguments"] = None
                if not authorised:
                    return _refused(name)
            try:
                result = catalog.execute(
                    ctx, "microsoft365", name, arguments, authorised=authorised,
                )
            except ApprovalRequired as exc:
                return {
                    "status": "not-approved",
                    "executed": False,
                    "detail": _plain("not-approved: " + exc.message, 300),
                }
            except (PermissionDenied, AuthenticationError) as exc:
                raise ToolPermissionError(exc.message) from exc
            except InvalidRequest as exc:
                raise ToolInputError(exc.message) from exc
            except IntegrationError as exc:
                raise ToolError(exc.message) from exc
            return _from_catalog(result)

        tool = Tool(
            name="m365_" + name,
            description=summary + " The catalog is the only caller. File contents are not stored in the audit log.",
            input_schema=schema,
            output_schema=_OUTPUT,
            handler=handler,
            idempotent=not requires,
            requires_approval=requires,
            timeout_seconds=15,
            tags=("microsoft", "documents"),
        )
        if requires:
            tool.approval_grant = grant  # type: ignore[attr-defined]
        tools.append(tool)
    return tools


__all__ = [
    "WRITES",
    "microsoft_document_tools",
]
