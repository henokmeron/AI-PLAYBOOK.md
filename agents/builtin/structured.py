"""Validate a JSON value against a named, pre-registered schema."""
from __future__ import annotations

from typing import Any

from ..schema import ValidationError, check_schema, validate
from ..tools import Tool, ToolInputError


def structured_output_tool(schemas: dict[str, dict[str, Any]]) -> Tool:
    if not schemas:
        raise ValueError("at least one named schema is required")
    for schema in schemas.values():
        check_schema(schema)
    names = sorted(schemas)

    def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        schema = schemas.get(arguments["schema"])
        if schema is None:
            raise ToolInputError(f"unknown schema; available: {names}")
        try:
            validate(arguments["value"], schema)
        except ValidationError as exc:
            return {"schema": arguments["schema"], "valid": False, "error": str(exc)}
        return {"schema": arguments["schema"], "valid": True, "error": None}

    return Tool(
        name="validate_structured_output",
        description=f"Check a JSON value against a named schema before finishing. Schemas: {names}",
        input_schema={
            "type": "object",
            "properties": {"schema": {"enum": names}, "value": {}},
            "required": ["schema", "value"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"schema": {"type": "string"}, "valid": {"type": "boolean"},
                           "error": {"type": ["string", "null"]}},
            "required": ["schema", "valid", "error"],
            "additionalProperties": False,
        },
        handler=handler,
        timeout_seconds=2.0,
        tags=("compute",),
    )
