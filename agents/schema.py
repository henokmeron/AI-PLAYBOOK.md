"""Minimal JSON-schema validator (stdlib only) for tool inputs and outputs.

Supports the subset the agent runtime relies on: type (including unions),
properties, required, additionalProperties (bool or schema), enum, const,
minimum/maximum, exclusiveMinimum/exclusiveMaximum, minLength/maxLength,
pattern, items, minItems/maxItems, and anyOf. Unknown keywords are rejected at
schema-check time so a typo cannot silently disable validation.
"""
from __future__ import annotations

import re
from typing import Any

SUPPORTED_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "enum", "const",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern", "items", "minItems", "maxItems",
    "anyOf", "description", "title", "default",
}
MAX_DEPTH = 32


class SchemaError(ValueError):
    """The schema itself is malformed or uses an unsupported keyword."""


class ValidationError(ValueError):
    """A value does not satisfy a schema. ``path`` is a JSON-pointer-like path."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path or '$'}: {message}")
        self.path = path or "$"
        self.message = message


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    raise SchemaError(f"unsupported type {expected!r}")


def check_schema(schema: Any, _depth: int = 0) -> None:
    """Raise SchemaError if ``schema`` uses anything outside the supported subset."""
    if _depth > MAX_DEPTH:
        raise SchemaError("schema nesting too deep")
    if not isinstance(schema, dict):
        raise SchemaError("schema must be an object")
    unknown = set(schema) - SUPPORTED_KEYWORDS
    if unknown:
        raise SchemaError(f"unsupported schema keywords: {sorted(unknown)}")
    types = schema.get("type")
    if types is not None:
        for name in types if isinstance(types, list) else [types]:
            _type_ok(None, name)
    for child in (schema.get("properties") or {}).values():
        check_schema(child, _depth + 1)
    if isinstance(schema.get("additionalProperties"), dict):
        check_schema(schema["additionalProperties"], _depth + 1)
    if "items" in schema:
        check_schema(schema["items"], _depth + 1)
    for child in schema.get("anyOf") or []:
        check_schema(child, _depth + 1)
    if "pattern" in schema:
        try:
            re.compile(schema["pattern"])
        except re.error as exc:
            raise SchemaError(f"invalid pattern: {exc}") from exc


def validate(value: Any, schema: dict[str, Any], path: str = "$", _depth: int = 0) -> None:
    """Raise ValidationError on the first violation found."""
    if _depth > MAX_DEPTH:
        raise ValidationError(path, "value nesting too deep")
    if "anyOf" in schema:
        errors = []
        for option in schema["anyOf"]:
            try:
                validate(value, option, path, _depth + 1)
                break
            except ValidationError as exc:
                errors.append(exc.message)
        else:
            raise ValidationError(path, "does not match any allowed shape")

    types = schema.get("type")
    if types is not None:
        options = types if isinstance(types, list) else [types]
        if not any(_type_ok(value, name) for name in options):
            raise ValidationError(path, f"expected {' or '.join(options)}")
    if "const" in schema and value != schema["const"]:
        raise ValidationError(path, f"must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(path, f"must be one of {schema['enum']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(path, f"must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValidationError(path, f"must be <= {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValidationError(path, f"must be > {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise ValidationError(path, f"must be < {schema['exclusiveMaximum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValidationError(path, f"must have at least {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValidationError(path, f"must have at most {schema['maxLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise ValidationError(path, "does not match the required pattern")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ValidationError(path, f"must have at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValidationError(path, f"must have at most {schema['maxItems']} items")
        if "items" in schema:
            for index, item in enumerate(value):
                validate(item, schema["items"], f"{path}[{index}]", _depth + 1)

    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in value:
                raise ValidationError(f"{path}.{name}", "is required")
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationError(path, "object keys must be strings")
            if key in properties:
                validate(item, properties[key], f"{path}.{key}", _depth + 1)
            elif additional is False:
                raise ValidationError(f"{path}.{key}", "is not an allowed property")
            elif isinstance(additional, dict):
                validate(item, additional, f"{path}.{key}", _depth + 1)
