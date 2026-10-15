"""Console-facing agent sessions.

The browser receives task state, tool activity and approval requests. It does
not receive the system prompt, model transcripts, or hidden reasoning.
"""
from __future__ import annotations

import threading
from typing import Any

from integrations.approvals import payload_hash
from integrations.catalog import Catalog
from integrations.errors import IntegrationError
from integrations.microsoft365 import platform_catalog
from integrations.tenancy import TenantContext

from .builtin.calculator import calculator_tool
from .builtin.search import search_documents_tool
from .model import ModelClient
from .redaction import redact
from .runtime import AgentRunner
from .state import AgentTask, Budget
from .tools import Tool, ToolError, ToolRegistry
from .trace import ExecutionTrace

_OBSERVABLE = {
    "tool_requested", "tool_result", "tool_error",
    "approval_required", "approval_decision", "information_requested",
    "task_final", "task_failed", "task_cancelled",
}
CONSOLE_TENANT = "local-console"
_CONSOLE_TENANT = CONSOLE_TENANT
_CONSOLE_PRINCIPAL = "console-user"


def _tool(catalog: Catalog, ctx: TenantContext, connector_id: str, operation: str, spec_tool: str,
          summary: str, input_schema: dict[str, Any], output_schema: dict[str, Any],
          approval: bool) -> Tool:
    grant: dict[str, Any] = {"call_id": None, "arguments": None}

    def handler(arguments: dict[str, Any]) -> Any:
        authorised = False
        if approval:
            expected = grant.get("arguments")
            authorised = (
                isinstance(grant.get("call_id"), str)
                and isinstance(expected, dict)
                and payload_hash(expected) == payload_hash(arguments)
            )
            grant["call_id"] = None
            grant["arguments"] = None
            if not authorised:
                raise ToolError(
                    "This action needs approval of these exact arguments. No request was sent."
                )
        try:
            return catalog.execute(
                ctx, connector_id, operation, arguments, authorised=authorised,
            )
        except IntegrationError as exc:
            raise ToolError(exc.message) from exc

    tool = Tool(
        name=spec_tool,
        description=summary,
        input_schema=input_schema,
        output_schema=output_schema,
        handler=handler,
        idempotent=not approval,
        requires_approval=approval,
    )
    tool.approval_grant = grant  # type: ignore[attr-defined]
    return tool


def tools_for(catalog: Catalog, ctx: TenantContext, documents: Any = None) -> list[Tool]:
    tools = [calculator_tool()]
    if documents is not None:
        tools.append(search_documents_tool(documents))
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
            "arguments": redact(item.arguments),
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
        "execution": task.execution.value,
        "states": list(task.status_log),
        "goal": task.goal,
        "answer": task.final_answer,
        "failure": task.failure_reason,
        "pending_question": task.pending_question,
        "pending_approval": pending,
        "activity": activity,
        "record": redact(task.record.to_dict()),
    }


class AgentDesk:
    """In-memory tasks for one loopback console. Not a customer tenant store."""

    def __init__(
        self,
        catalog: Catalog | None = None,
        ctx: TenantContext | None = None,
        documents: Any = None,
    ) -> None:
        self.catalog = catalog if catalog is not None else platform_catalog()[0]
        self.ctx = ctx or TenantContext.create(_CONSOLE_TENANT, _CONSOLE_PRINCIPAL, [])
        self.documents = documents
        self._lock = threading.Lock()
        self._sessions: dict[str, tuple[AgentRunner, AgentTask, ExecutionTrace]] = {}

    def connectors(self) -> list[dict[str, Any]]:
        rows = self.catalog.describe(self.ctx.tenant_id)
        documents_ready = self.documents is not None
        rows.append({
            "connector_id": "documents",
            "version": "local",
            "service": "Document library",
            "summary": "The same on-disk library as Document Q&A.",
            "auth": "local",
            "connected": documents_ready,
            "account": None,
            "readiness": "mock-tested" if documents_ready else "unavailable",
            "detail": (
                "Unit-tested with a fake model. Not a live test of this console. "
                "File attachments on the Agent page are not indexed."
            ),
            "operations": [{
                "name": "search_documents",
                "tool_name": "search_documents",
                "summary": "Search the local document library.",
                "effect": "read",
                "scope": "documents:read",
                "requires_approval": False,
                "available": documents_ready,
                "evidence": "mock-tested" if documents_ready else "unavailable",
                "status": "mock-tested" if documents_ready else "unavailable",
                "provider_permissions": [],
            }],
        })
        rows.append({
            "connector_id": "calculator",
            "version": "local",
            "service": "Calculator",
            "summary": "Exact decimal arithmetic.",
            "auth": "none",
            "connected": True,
            "account": None,
            "readiness": "mock-tested",
            "detail": (
                "Unit-tested. A live calculator check ran on an older console commit "
                "and was not repeated for this build."
            ),
            "operations": [{
                "name": "calculate",
                "tool_name": "calculator",
                "summary": "Evaluate one arithmetic expression.",
                "effect": "read",
                "scope": "local:read",
                "requires_approval": False,
                "available": True,
                "evidence": "mock-tested",
                "status": "mock-tested",
                "provider_permissions": [],
            }],
        })
        return rows

    def start(self, goal: str, model: ModelClient, *, wall_seconds: float = 60.0) -> dict[str, Any]:
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 2000:
            raise ValueError("task must be 1 to 2000 characters")
        trace = ExecutionTrace()
        registry = ToolRegistry(tools_for(self.catalog, self.ctx, self.documents))
        runner = AgentRunner(model, registry, trace=trace, model_timeout=wall_seconds)
        task = runner.new_task(goal, budget=Budget(
            max_iterations=6, max_tool_calls=4, max_total_tokens=12000, max_wall_seconds=wall_seconds,
        ))
        runner.run(task)
        with self._lock:
            self._sessions[task.task_id] = (runner, task, trace)
        return public_view(task, trace)

    def decide(
        self, task_id: str, approved: bool, approver: str, call_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("call_id is required")
        with self._lock:
            session = self._sessions.get(task_id)
        if session is None:
            raise KeyError(task_id)
        runner, task, trace = session
        pending = task.pending_approval
        if pending is None or pending.call_id != call_id:
            raise ValueError("approval does not match the pending action")
        if arguments is not None and arguments != pending.arguments:
            raise ValueError("approval arguments do not match the pending action")
        runner.resolve_approval(task, approved=approved, approver=approver, call_id=call_id)
        return public_view(task, trace)

    def inform(self, task_id: str, text: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(task_id)
        if session is None:
            raise KeyError(task_id)
        runner, task, trace = session
        runner.provide_information(task, text)
        return public_view(task, trace)

    def cancel(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(task_id)
        if session is None:
            raise KeyError(task_id)
        runner, task, trace = session
        runner.cancel(task, "cancelled by the operator")
        return public_view(task, trace)
