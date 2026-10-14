"""Explicit agent task state machine with resumable JSON serialization."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

STATE_FORMAT_VERSION = 1


class TaskState(str, Enum):
    PLANNING = "planning"
    TOOL_CALL = "tool_call"
    OBSERVATION = "observation"
    AWAITING_APPROVAL = "awaiting_approval"
    FINAL = "final"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES = frozenset({TaskState.FINAL, TaskState.FAILED, TaskState.CANCELLED})

ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PLANNING: frozenset({
        TaskState.TOOL_CALL, TaskState.FINAL, TaskState.FAILED,
        TaskState.CANCELLED, TaskState.PLANNING,
    }),
    TaskState.TOOL_CALL: frozenset({
        TaskState.OBSERVATION, TaskState.AWAITING_APPROVAL,
        TaskState.FAILED, TaskState.CANCELLED,
    }),
    TaskState.AWAITING_APPROVAL: frozenset({
        TaskState.TOOL_CALL, TaskState.OBSERVATION, TaskState.FAILED, TaskState.CANCELLED,
    }),
    TaskState.OBSERVATION: frozenset({TaskState.PLANNING, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.FINAL: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


class InvalidTransition(RuntimeError):
    pass


@dataclass
class Budget:
    max_iterations: int = 8
    max_tool_calls: int = 12
    max_total_tokens: int = 24_000
    max_wall_seconds: float = 300.0
    max_repeated_calls: int = 2
    max_consecutive_errors: int = 3
    max_parse_failures: int = 2
    max_output_validation_failures: int = 2

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"budget {name} must be a positive number")


@dataclass
class Usage:
    iterations: int = 0
    tool_calls: int = 0
    total_tokens: int = 0
    elapsed_seconds: float = 0.0
    consecutive_errors: int = 0
    parse_failures: int = 0
    output_validation_failures: int = 0


@dataclass
class PendingApproval:
    call_id: str
    tool: str
    arguments: dict[str, Any]
    reason: str


@dataclass
class AgentTask:
    goal: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: TaskState = TaskState.PLANNING
    budget: Budget = field(default_factory=Budget)
    usage: Usage = field(default_factory=Usage)
    messages: list[dict[str, str]] = field(default_factory=list)
    call_history: list[str] = field(default_factory=list)
    pending_approval: PendingApproval | None = None
    output_schema: dict[str, Any] | None = None
    final_answer: str | None = None
    final_output: Any = None
    failure_reason: str | None = None
    refused: bool = False
    allowed_tools: list[str] | None = None

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def transition(self, new_state: TaskState) -> None:
        if new_state not in ALLOWED_TRANSITIONS[self.state]:
            raise InvalidTransition(f"{self.state.value} -> {new_state.value} is not allowed")
        self.state = new_state

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["format_version"] = STATE_FORMAT_VERSION
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentTask":
        if data.get("format_version") != STATE_FORMAT_VERSION:
            raise ValueError("unsupported agent task state format")
        pending = data.get("pending_approval")
        return cls(
            goal=data["goal"],
            task_id=data["task_id"],
            state=TaskState(data["state"]),
            budget=Budget(**data["budget"]),
            usage=Usage(**data["usage"]),
            messages=list(data["messages"]),
            call_history=list(data["call_history"]),
            pending_approval=PendingApproval(**pending) if pending else None,
            output_schema=data.get("output_schema"),
            final_answer=data.get("final_answer"),
            final_output=data.get("final_output"),
            failure_reason=data.get("failure_reason"),
            refused=bool(data.get("refused", False)),
            allowed_tools=data.get("allowed_tools"),
        )

    @classmethod
    def from_json(cls, text: str) -> "AgentTask":
        return cls.from_dict(json.loads(text))
