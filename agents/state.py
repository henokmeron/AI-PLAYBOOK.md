"""Explicit agent task state machine with resumable JSON serialization."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

STATE_FORMAT_VERSION = 2
ACCEPTED_STATE_VERSIONS = frozenset({1, 2})


class TaskState(str, Enum):
    PLANNING = "planning"
    TOOL_CALL = "tool_call"
    OBSERVATION = "observation"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_INFORMATION = "awaiting_information"
    FINAL = "final"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionStatus(str, Enum):
    """Operator-facing status. The runner writes these; the UI does not invent them."""

    RECEIVED = "received"
    INVESTIGATING = "investigating"
    AWAITING_INFORMATION = "awaiting_information"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


TERMINAL_STATES = frozenset({TaskState.FINAL, TaskState.FAILED, TaskState.CANCELLED})
EXECUTION_TERMINAL = frozenset({
    ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
    ExecutionStatus.ESCALATED, ExecutionStatus.CANCELLED,
})

ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PLANNING: frozenset({
        TaskState.TOOL_CALL, TaskState.AWAITING_INFORMATION, TaskState.FINAL,
        TaskState.FAILED, TaskState.CANCELLED, TaskState.PLANNING,
    }),
    TaskState.TOOL_CALL: frozenset({
        TaskState.OBSERVATION, TaskState.AWAITING_APPROVAL,
        TaskState.FAILED, TaskState.CANCELLED,
    }),
    TaskState.AWAITING_APPROVAL: frozenset({
        TaskState.TOOL_CALL, TaskState.OBSERVATION, TaskState.FAILED, TaskState.CANCELLED,
    }),
    TaskState.AWAITING_INFORMATION: frozenset({
        TaskState.PLANNING, TaskState.FAILED, TaskState.CANCELLED,
    }),
    TaskState.OBSERVATION: frozenset({TaskState.PLANNING, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.FINAL: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}

ALLOWED_EXECUTION: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    ExecutionStatus.RECEIVED: frozenset({
        ExecutionStatus.INVESTIGATING, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED,
    }),
    ExecutionStatus.INVESTIGATING: frozenset({
        ExecutionStatus.INVESTIGATING, ExecutionStatus.AWAITING_INFORMATION,
        ExecutionStatus.AWAITING_APPROVAL, ExecutionStatus.EXECUTING,
        ExecutionStatus.VERIFYING, ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
        ExecutionStatus.ESCALATED, ExecutionStatus.CANCELLED,
    }),
    ExecutionStatus.AWAITING_INFORMATION: frozenset({
        ExecutionStatus.INVESTIGATING, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED,
    }),
    ExecutionStatus.AWAITING_APPROVAL: frozenset({
        ExecutionStatus.EXECUTING, ExecutionStatus.INVESTIGATING,
        ExecutionStatus.FAILED, ExecutionStatus.CANCELLED,
    }),
    ExecutionStatus.EXECUTING: frozenset({
        ExecutionStatus.VERIFYING, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED,
    }),
    ExecutionStatus.VERIFYING: frozenset({
        ExecutionStatus.INVESTIGATING, ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
        ExecutionStatus.ESCALATED, ExecutionStatus.CANCELLED,
    }),
    ExecutionStatus.COMPLETED: frozenset(),
    ExecutionStatus.FAILED: frozenset(),
    ExecutionStatus.ESCALATED: frozenset(),
    ExecutionStatus.CANCELLED: frozenset(),
}


class InvalidTransition(RuntimeError):
    pass


def _execution_for_legacy_state(state: TaskState, refused: bool) -> ExecutionStatus:
    """Older saved tasks had no operator status. Map the control state, do not invent progress."""
    if state is TaskState.FINAL:
        return ExecutionStatus.ESCALATED if refused else ExecutionStatus.COMPLETED
    if state is TaskState.FAILED:
        return ExecutionStatus.FAILED
    if state is TaskState.CANCELLED:
        return ExecutionStatus.CANCELLED
    if state is TaskState.AWAITING_APPROVAL:
        return ExecutionStatus.AWAITING_APPROVAL
    if state is TaskState.AWAITING_INFORMATION:
        return ExecutionStatus.AWAITING_INFORMATION
    if state is TaskState.TOOL_CALL:
        return ExecutionStatus.EXECUTING
    if state is TaskState.OBSERVATION:
        return ExecutionStatus.VERIFYING
    return ExecutionStatus.INVESTIGATING


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
class TaskRecord:
    """What the runner actually did. This is not the model's hidden reasoning."""

    objective: str = ""
    plan: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    verification: list[dict[str, Any]] = field(default_factory=list)
    outcome: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TaskRecord":
        if not isinstance(data, dict):
            return cls()
        return cls(
            objective=str(data.get("objective") or ""),
            plan=[str(item) for item in data.get("plan") or []],
            tool_calls=[item for item in data.get("tool_calls") or [] if isinstance(item, dict)],
            results=[item for item in data.get("results") or [] if isinstance(item, dict)],
            approvals=[item for item in data.get("approvals") or [] if isinstance(item, dict)],
            errors=[item for item in data.get("errors") or [] if isinstance(item, dict)],
            verification=[item for item in data.get("verification") or [] if isinstance(item, dict)],
            outcome=data.get("outcome") if isinstance(data.get("outcome"), str) else None,
        )


@dataclass
class AgentTask:
    goal: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: TaskState = TaskState.PLANNING
    execution: ExecutionStatus = ExecutionStatus.RECEIVED
    status_log: list[str] = field(default_factory=lambda: [ExecutionStatus.RECEIVED.value])
    record: TaskRecord = field(default_factory=TaskRecord)
    budget: Budget = field(default_factory=Budget)
    usage: Usage = field(default_factory=Usage)
    messages: list[dict[str, str]] = field(default_factory=list)
    call_history: list[str] = field(default_factory=list)
    pending_approval: PendingApproval | None = None
    pending_question: str | None = None
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

    def set_execution(self, new_status: ExecutionStatus) -> None:
        if new_status not in ALLOWED_EXECUTION[self.execution]:
            raise InvalidTransition(f"{self.execution.value} -> {new_status.value} is not allowed")
        self.execution = new_status
        self.status_log.append(new_status.value)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["execution"] = self.execution.value
        data["format_version"] = STATE_FORMAT_VERSION
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentTask":
        if data.get("format_version") not in ACCEPTED_STATE_VERSIONS:
            raise ValueError("unsupported agent task state format")
        pending = data.get("pending_approval")
        state = TaskState(data["state"])
        if data.get("execution"):
            execution = ExecutionStatus(data["execution"])
        else:
            execution = _execution_for_legacy_state(state, bool(data.get("refused", False)))
        status_log = [str(item) for item in data.get("status_log") or [execution.value]]
        raw_record = data.get("record") if isinstance(data.get("record"), dict) else None
        record = TaskRecord.from_dict(raw_record)
        if raw_record is None:
            record.objective = str(data.get("goal") or "")
        return cls(
            goal=data["goal"],
            task_id=data["task_id"],
            state=state,
            execution=execution,
            status_log=status_log,
            record=record,
            budget=Budget(**data["budget"]),
            usage=Usage(**data["usage"]),
            messages=list(data["messages"]),
            call_history=list(data["call_history"]),
            pending_approval=PendingApproval(**pending) if pending else None,
            pending_question=data.get("pending_question"),
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
