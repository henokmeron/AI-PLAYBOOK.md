"""Console-facing agent sessions.

The browser receives task state, tool activity and approval requests. It does
not receive the system prompt, model transcripts, or hidden reasoning.
"""
from __future__ import annotations

import threading
from typing import Any

from integrations.catalog import Catalog
from integrations.errors import IntegrationError
from integrations.microsoft365 import platform_catalog
from integrations.tenancy import TenantContext

from .builtin.calculator import calculator_tool
from .model import ModelClient
from .runtime import AgentRunner
from .state import AgentTask, Budget
from .tools import Tool, ToolError, ToolRegistry
from .trace import ExecutionTrace

_OBSERVABLE = {
    "tool_requested", "tool_result", "tool_error",
    "approval_required", "approval_decision",
    "task_final", "task_failed", "task_cancelled",
}
_CONSOLE_TENANT = "local-console"
_CONSOLE_PRINCIPAL = "console-user"


def _tool(catalog: Catalog, ctx: TenantContext, connector_id: str, operation: str, spec_tool: str,
          summary: str, input_schema: dict[str, Any], output_schema: dict[str, Any],
          approval: bool) -> Tool:
    def handler(arguments: dict[str, Any]) -> Any:
        try:
            return catalog.execute(
                ctx, connector_id, operation, arguments, authorised=approval,
            )
        except IntegrationError as exc:
            raise ToolError(exc.message) from exc

    return Tool(
        name=spec_tool,
        description=summary,
        input_schema=input_schema,
        output_schema=output_schema,
        handler=handler,
        idempotent=not approval,
        requires_approval=approval,
    )


def tools_for(catalog: Catalog, ctx: TenantContext) -> list[Tool]:
    tools = [calculator_tool()]
    for spec, operation in catalog.visible_operations(ctx):
        tools.append(_tool(
            catalog, ctx, spec.connector_id, operation.name, operation.tool_name,
            operation.summary, operation.input_schema, operation.output_schema,
            operation.requires_approval,
        ))
    return tools


def public_view(task: AgentTask, trace: ExecutionTrace) -> dict[str, Any]:
    pending = None
    if task.pending_approval is not None:
        item = task.pending_approval
        pending = {
            "call_id": item.call_id,
            "tool": item.tool,
            "arguments": item.arguments,
            "reason": item.reason,
        }
    activity = []
    for event in trace.events:
        if event.task_id != task.task_id or event.kind not in _OBSERVABLE:
            continue
        activity.append({
            "kind": event.kind,
            "tool": event.data.get("tool"),
            "arguments": event.data.get("arguments"),
            "detail": event.data.get("error") or event.data.get("preview") or event.data.get("reason"),
            "approved": event.data.get("approved"),
        })
    return {
        "task_id": task.task_id,
        "state": task.state.value,
        "goal": task.goal,
        "answer": task.final_answer,
        "failure": task.failure_reason,
        "pending_approval": pending,
        "activity": activity,
    }


class AgentDesk:
    """In-memory tasks for one loopback console. Not a customer tenant store."""

    def __init__(self, catalog: Catalog | None = None, ctx: TenantContext | None = None) -> None:
        self.catalog = catalog if catalog is not None else platform_catalog()[0]
        self.ctx = ctx or TenantContext.create(_CONSOLE_TENANT, _CONSOLE_PRINCIPAL, [])
        self._lock = threading.Lock()
        self._sessions: dict[str, tuple[AgentRunner, AgentTask, ExecutionTrace]] = {}

    def connectors(self) -> list[dict[str, Any]]:
        return self.catalog.describe(self.ctx.tenant_id)

    def start(self, goal: str, model: ModelClient, *, wall_seconds: float = 60.0) -> dict[str, Any]:
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 2000:
            raise ValueError("task must be 1 to 2000 characters")
        trace = ExecutionTrace()
        registry = ToolRegistry(tools_for(self.catalog, self.ctx))
        runner = AgentRunner(model, registry, trace=trace, model_timeout=wall_seconds)
        task = runner.new_task(goal, budget=Budget(
            max_iterations=6, max_tool_calls=4, max_total_tokens=12000, max_wall_seconds=wall_seconds,
        ))
        runner.run(task)
        with self._lock:
            self._sessions[task.task_id] = (runner, task, trace)
        return public_view(task, trace)

    def decide(self, task_id: str, approved: bool, approver: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(task_id)
        if session is None:
            raise KeyError(task_id)
        runner, task, trace = session
        runner.resolve_approval(task, approved=approved, approver=approver)
        return public_view(task, trace)
