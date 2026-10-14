"""Tool definitions, error taxonomy and a registry with schema-checked I/O."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .schema import ValidationError, check_schema, validate

TOOL_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")
MAX_OBSERVATION_CHARS = 6000


class ToolError(Exception):
    """Base tool failure. ``retryable`` marks transient errors only."""

    retryable = False
    category = "tool_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ToolInputError(ToolError):
    category = "invalid_arguments"


class ToolOutputError(ToolError):
    category = "invalid_output"


class ToolPermissionError(ToolError):
    category = "permission_denied"


class ToolNotFoundError(ToolError):
    category = "unknown_tool"


class ToolTimeoutError(ToolError):
    category = "timeout"
    retryable = True


class ToolTransientError(ToolError):
    category = "transient"
    retryable = True


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    idempotent: bool = True
    requires_approval: bool = False
    timeout_seconds: float = 20.0
    max_retries: int = 1
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not TOOL_NAME_RE.fullmatch(self.name):
            raise ValueError(f"invalid tool name {self.name!r}")
        check_schema(self.input_schema)
        check_schema(self.output_schema)
        if self.input_schema.get("type") != "object":
            raise ValueError("tool input schema must describe an object")
        if self.requires_approval and self.max_retries:
            # Consequential actions are never retried automatically.
            self.max_retries = 0
        if not self.idempotent:
            self.max_retries = 0

    def validate_input(self, arguments: Any) -> dict[str, Any]:
        try:
            validate(arguments, self.input_schema)
        except ValidationError as exc:
            raise ToolInputError(f"invalid arguments for {self.name}: {exc}") from exc
        return arguments

    def validate_output(self, result: Any) -> Any:
        try:
            validate(result, self.output_schema)
        except ValidationError as exc:
            raise ToolOutputError(f"{self.name} produced invalid output: {exc}") from exc
        return result

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "requires_approval": self.requires_approval,
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name} is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str, allowed: list[str] | None = None) -> Tool:
        if allowed is not None and name not in allowed:
            raise ToolPermissionError(f"tool {name!r} is not permitted for this task")
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(f"unknown tool {name!r}")
        return tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def catalog(self, allowed: list[str] | None = None) -> list[dict[str, Any]]:
        return [
            self._tools[name].describe()
            for name in self.names()
            if allowed is None or name in allowed
        ]


def render_observation(value: Any, limit: int = MAX_OBSERVATION_CHARS) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) > limit:
        return text[:limit] + f"... [truncated {len(text) - limit} characters]"
    return text
