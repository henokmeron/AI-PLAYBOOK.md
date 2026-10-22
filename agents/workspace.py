"""Console-facing agent sessions.

The browser receives task state, tool activity and approval requests. It does
not receive the system prompt, model transcripts, or hidden reasoning.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from integrations.approvals import payload_hash
from integrations.audit import AuditLog
from integrations.catalog import Catalog, Effect
from integrations.errors import AuthenticationError, IntegrationError, InvalidRequest, PermissionDenied
from integrations.microsoft365 import platform_catalog
from integrations.tenancy import TenantContext

from .builtin.calculator import calculator_tool
from .builtin.helpdesk import helpdesk_tools
from .builtin.search import search_documents_tool
from .history import TaskHistoryStore
from .it_support import approval_presentation, incident_from_output, looks_like_it_support
from .mac_catalogue import LIVE_MAC, MAC_CHECKS, mac_tools
from .microsoft_documents import microsoft_document_tools
from .task_kinds import allowlist_for, resolve_task_kind
from .model import ModelClient
from .redaction import redact
from .runtime import AgentRunner, CancellationToken
from .state import EXECUTION_TERMINAL, AgentTask, Budget, ExecutionStatus, TaskState
from .tools import Tool, ToolError, ToolInputError, ToolPermissionError, ToolRegistry
from .trace import ExecutionTrace

_OBSERVABLE = {
    "tool_requested", "tool_result", "tool_error",
    "approval_required", "approval_decision", "information_requested",
    "task_final", "task_failed", "task_cancelled",
}
CONSOLE_TENANT = "local-console"
_CONSOLE_TENANT = CONSOLE_TENANT
_CONSOLE_PRINCIPAL = "console-user"
_PAUSED = frozenset({TaskState.AWAITING_APPROVAL, TaskState.AWAITING_INFORMATION})


def _tool(catalog: Catalog, ctx: TenantContext, connector_id: str, operation: str, spec_tool: str,
          summary: str, input_schema: dict[str, Any], output_schema: dict[str, Any],
          approval: bool, timeout_seconds: float = 20.0) -> Tool:
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
        except (PermissionDenied, AuthenticationError) as exc:
            raise ToolPermissionError(exc.message) from exc
        except InvalidRequest as exc:
            raise ToolInputError(exc.message) from exc
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
        timeout_seconds=timeout_seconds,
    )
    tool.approval_grant = grant  # type: ignore[attr-defined]
    return tool


def tools_for(
    catalog: Catalog,
    ctx: TenantContext,
    documents: Any = None,
    ops_centre: Any = None,
    repair_session: Any = None,
) -> list[Tool]:
    tools = [calculator_tool()]
    tools.extend(helpdesk_tools())
    from windows_repair.agent_tools import windows_repair_tools

    tools.extend(windows_repair_tools(repair_session))
    tools.extend(mac_tools())
    if documents is not None:
        tools.append(search_documents_tool(documents))
    if ops_centre is not None:
        from ops_centre.agent_tools import ops_centre_tools

        tools.extend(ops_centre_tools(ops_centre))
    registered: set[str] = set()
    microsoft = catalog.spec("microsoft365")
    for operation in microsoft.operations:
        if operation.name == "send_mail" or operation.effect not in {Effect.READ, Effect.DRAFT}:
            continue
        if operation.evidence == "unavailable":
            continue
        tools.append(_tool(
            catalog, ctx, microsoft.connector_id, operation.name, operation.tool_name,
            operation.summary, operation.input_schema, operation.output_schema,
            operation.requires_approval, timeout_seconds=15.0,
        ))
        registered.add(operation.tool_name)
    for tool in microsoft_document_tools(catalog, ctx):
        if tool.name not in registered:
            tools.append(tool)
            registered.add(tool.name)
    for spec, operation in catalog.visible_operations(ctx):
        if operation.tool_name in registered or operation.tool_name == "m365_send_mail":
            continue
        if operation.effect not in {Effect.READ, Effect.DRAFT}:
            continue
        tools.append(_tool(
            catalog, ctx, spec.connector_id, operation.name, operation.tool_name,
            operation.summary, operation.input_schema, operation.output_schema,
            operation.requires_approval,
        ))
    return tools


def public_view(task: AgentTask, trace: ExecutionTrace, *, running: bool = False) -> dict[str, Any]:
    pending = None
    if task.pending_approval is not None:
        item = task.pending_approval
        presentation = approval_presentation(item.tool, item.arguments, item.reason)
        pending = {
            "call_id": item.call_id,
            "tool": item.tool,
            "arguments": redact(item.arguments),
            "reason": item.reason,
            "what_changes": presentation["what_changes"],
            "why": presentation["why"],
            "system": presentation["system"],
            "risks": presentation["risks"],
            "verification_plan": presentation["verification_plan"],
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
    incident = incident_from_output(task.final_output)
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
        "incident_report": redact(incident) if incident else None,
        "task_kind": task.task_kind,
        "tools_executed": [
            str(item.get("tool"))
            for item in task.record.results
            if item.get("ok") and item.get("tool")
        ],
        "running": bool(running),
        "cancellable": bool(
            running
            or task.execution == ExecutionStatus.QUEUED
            or task.state in _PAUSED
            or (not task.is_terminal and task.execution not in EXECUTION_TERMINAL)
        ),
    }


class AgentDesk:
    """In-memory tasks for one loopback console, with optional on-disk history."""

    def __init__(
        self,
        catalog: Catalog | None = None,
        ctx: TenantContext | None = None,
        documents: Any = None,
        history_dir: Path | str | None = None,
        ops_centre: Any = None,
    ) -> None:
        self.catalog = catalog if catalog is not None else platform_catalog()[0]
        self.ctx = ctx or TenantContext.create(_CONSOLE_TENANT, _CONSOLE_PRINCIPAL, [])
        self.documents = documents
        self.ops_centre = ops_centre
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, Any]] = {}
        if history_dir is None:
            history_dir = os.environ.get("AGENT_HISTORY_DIR", "")
        self.history = TaskHistoryStore(history_dir) if history_dir else None
        from windows_repair.agent_tools import RepairToolSession

        self.audit = AuditLog()
        self.repair_tools = RepairToolSession(audit=self.audit)
        self._queue: list[str] = []
        self._active_id: str | None = None

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
        rows.append({
            "connector_id": "helpdesk",
            "version": "local",
            "service": "IT helpdesk tools",
            "summary": "Classify issues, check platform health, read allowlisted logs, run safe diagnostics, and apply approved local remediations.",
            "auth": "none",
            "connected": True,
            "account": None,
            "readiness": "mock-tested",
            "detail": (
                "Local tools only. No unrestricted shell. Remediation pauses for approval. "
                "Microsoft 365 and enrolled-device tools stay separate and appear only when connected."
            ),
            "operations": [
                {
                    "name": name,
                    "tool_name": name,
                    "summary": summary,
                    "effect": effect,
                    "scope": "helpdesk:local",
                    "requires_approval": approval,
                    "available": True,
                    "evidence": "mock-tested",
                    "status": "mock-tested",
                    "provider_permissions": [],
                }
                for name, summary, effect, approval in (
                    ("classify_it_issue", "Classify the IT issue and desired outcome.", "read", False),
                    ("check_platform_health", "Check local model, gateway, and console health.", "read", False),
                    ("read_approved_log", "Read an allowlisted diagnostic log with secrets redacted.", "read", False),
                    ("run_safe_diagnostic", "Run one allowlisted local diagnostic check.", "read", False),
                    ("apply_safe_remediation", "Apply one allowlisted local change after approval.", "consequential", True),
                    ("compose_incident_report", "Assemble the incident report fields.", "read", False),
                )
            ],
        })
        rows.append({
            "connector_id": "windows_repair",
            "version": "local",
            "service": "Windows repair diagnostics",
            "summary": "Registered read-only Windows checks and an approval record that does not change this computer.",
            "auth": "none",
            "connected": True,
            "account": None,
            "readiness": "mock-tested",
            "detail": (
                "The diagnose tool can run a registered read-only collector on the computer "
                "that hosts the console. Unit tests use a fake collector. Privileged repair "
                "stays disabled. This is not a second computer and not a remote shell."
            ),
            "operations": [
                {
                    "name": name,
                    "tool_name": name,
                    "summary": summary,
                    "effect": effect,
                    "scope": "windows:local",
                    "requires_approval": approval,
                    "available": True,
                    "evidence": "mock-tested",
                    "status": "mock-tested",
                    "provider_permissions": [],
                }
                for name, summary, effect, approval in (
                    ("windows_repair_plan", "Choose a registered procedure id from a symptom.", "read", False),
                    ("windows_repair_diagnose", "Run one registered read-only check. Result text is untrusted.", "read", False),
                    ("windows_repair_request_change", "Record approval for an elevated procedure. Nothing is changed.", "consequential", True),
                )
            ],
        })
        rows.append({
            "connector_id": "mac_checks",
            "version": "catalogue",
            "service": "Mac troubleshooting",
            "summary": "Documented read-only Mac checks. Live Mac is NOT TESTED.",
            "auth": "none",
            "connected": False,
            "account": None,
            "readiness": LIVE_MAC,
            "detail": (
                "Live Mac is NOT TESTED. Checks are interpreted from fixtures in tests. "
                "This Windows host does not execute them. No remote Mac agent binary is in this repository."
            ),
            "operations": [
                {
                    "name": item.check_id,
                    "tool_name": "mac_diagnose",
                    "summary": item.summary,
                    "effect": "read",
                    "scope": "mac:read",
                    "requires_approval": False,
                    "available": False,
                    "evidence": LIVE_MAC,
                    "status": LIVE_MAC,
                    "provider_permissions": [],
                }
                for item in MAC_CHECKS
            ],
        })
        for row in rows:
            if row.get("connector_id") != "microsoft365":
                continue
            operations = list(row.get("operations") or [])
            present = {item.get("tool_name") for item in operations}
            for name, summary in (
                ("m365_create_document", "Create a document. Not approved until the catalog lists the write."),
                ("m365_update_document", "Update a document. Not approved until the catalog lists the write."),
            ):
                if name in present:
                    continue
                operations.append({
                    "name": name.removeprefix("m365_"),
                    "tool_name": name,
                    "summary": summary,
                    "effect": "consequential",
                    "scope": "files:write",
                    "requires_approval": True,
                    "available": False,
                    "evidence": "unavailable",
                    "status": "not-approved",
                    "provider_permissions": [],
                })
            row["operations"] = operations
        return rows

    def _view(self, task: AgentTask, trace: ExecutionTrace, *, running: bool = False) -> dict[str, Any]:
        view = public_view(task, trace, running=running)
        if self.history is not None:
            self.history.save(view)
        return view

    def _session(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(task_id)
        if session is None:
            raise KeyError(task_id)
        return session

    def _busy_unlocked(self) -> bool:
        if self._active_id is None:
            return False
        session = self._sessions.get(self._active_id)
        if session is None:
            self._active_id = None
            return False
        thread = session.get("thread")
        # Claimed for launch but thread not attached yet still counts as busy.
        if thread is None:
            return True
        return thread.is_alive()

    def _mark_queued(self, task: AgentTask) -> None:
        task.execution = ExecutionStatus.QUEUED
        task.status_log = [ExecutionStatus.QUEUED.value]

    def _pop_next_queued_unlocked(self) -> str | None:
        while self._queue:
            candidate = self._queue.pop(0)
            queued = self._sessions.get(candidate)
            if queued is None:
                continue
            if queued["task"].is_terminal or queued["cancel"].cancelled:
                continue
            return candidate
        return None

    def _start_thread(self, task_id: str) -> None:
        session = self._session(task_id)
        runner: AgentRunner = session["runner"]
        task: AgentTask = session["task"]
        trace: ExecutionTrace = session["trace"]
        cancel: CancellationToken = session["cancel"]

        def worker() -> None:
            try:
                runner.run(task, cancel)
            finally:
                # Persist the snapshot before the thread looks idle. On Windows
                # a history write that overlaps directory cleanup fails the test
                # and can leave a partial file as the last record.
                try:
                    self._view(task, trace, running=False)
                finally:
                    with self._lock:
                        current = self._sessions.get(task_id)
                        if current is not None:
                            current["thread"] = None
                        if self._active_id == task_id:
                            self._active_id = None
                    self._pump_queue()

        thread = threading.Thread(target=worker, name=f"agent-{task_id[:8]}", daemon=True)
        with self._lock:
            session["thread"] = thread
            self._active_id = task_id
        self._view(task, trace, running=True)
        thread.start()

    def _pump_queue(self) -> None:
        with self._lock:
            if self._busy_unlocked():
                return
            next_id = self._pop_next_queued_unlocked()
            if next_id is None:
                return
            self._active_id = next_id
        self._start_thread(next_id)

    def start(
        self,
        goal: str,
        model: ModelClient,
        *,
        wall_seconds: float = 60.0,
        wait: bool = True,
        started_by: str = "",
        task_type: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 2000:
            raise ValueError("task must be 1 to 2000 characters")
        kind = resolve_task_kind(goal, task_type)
        cancel = CancellationToken()
        trace = ExecutionTrace()

        def on_progress(task: AgentTask) -> None:
            with self._lock:
                session = self._sessions.get(task.task_id)
                running = bool(session and session.get("thread") and session["thread"].is_alive())
            self._view(task, trace, running=running)

        registry = ToolRegistry(
            tools_for(
                self.catalog, self.ctx, self.documents,
                ops_centre=self.ops_centre, repair_session=self.repair_tools,
            )
        )
        runner = AgentRunner(
            model, registry, trace=trace, model_timeout=wall_seconds, on_progress=on_progress,
            audit=self.audit,
        )
        if kind in {"it_support", "windows_repair", "mac_troubleshooting", "microsoft_documents"} or looks_like_it_support(goal):
            # Live Qwen helpdesk needs classify → diagnose → approve → verify →
            # report; 16k tokens ran out after a successful remediation.
            budget = Budget(
                max_iterations=12, max_tool_calls=10, max_total_tokens=48000,
                max_wall_seconds=wall_seconds,
            )
        else:
            budget = Budget(
                max_iterations=6, max_tool_calls=4, max_total_tokens=12000,
                max_wall_seconds=wall_seconds,
            )
        allowed = allowlist_for(kind, registry.names())
        task = runner.new_task(goal, budget=budget, allowed_tools=allowed, task_kind=kind or None)
        session = {
            "runner": runner,
            "task": task,
            "trace": trace,
            "cancel": cancel,
            "thread": None,
            "started_by": started_by.strip()[:128] if isinstance(started_by, str) else "",
        }
        with self._lock:
            self._sessions[task.task_id] = session

        if wait:
            runner.run(task, cancel)
            return self._view(task, trace, running=False)

        with self._lock:
            if self._busy_unlocked():
                self._mark_queued(task)
                self._queue.append(task.task_id)
                queued = True
            else:
                self._active_id = task.task_id
                queued = False
        if queued:
            return self._view(task, trace, running=False)
        self._start_thread(task.task_id)
        return public_view(task, trace, running=True)

    def get(self, task_id: str) -> dict[str, Any]:
        try:
            session = self._session(task_id)
        except KeyError:
            if self.history is not None:
                stored = self.history.get(task_id)
                if stored is not None:
                    return stored
            raise
        task = session["task"]
        trace = session["trace"]
        thread = session.get("thread")
        running = bool(thread is not None and thread.is_alive())
        return public_view(task, trace, running=running)

    def history_list(self, *, limit: int = 20) -> list[dict[str, Any]]:
        live: dict[str, dict[str, Any]] = {}
        with self._lock:
            for task_id, session in self._sessions.items():
                thread = session.get("thread")
                running = bool(thread is not None and thread.is_alive())
                live[task_id] = public_view(session["task"], session["trace"], running=running)
        if self.history is None:
            rows = sorted(
                live.values(),
                key=lambda row: row.get("task_id") or "",
                reverse=True,
            )
            return rows[:limit]
        # Refresh history for live tasks, then list from disk (newest first).
        for view in live.values():
            self.history.save(view)
        return self.history.list(limit=limit)

    def decide(
        self, task_id: str, approved: bool, approver: str, call_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("call_id is required")
        session = self._session(task_id)
        runner, task, trace, cancel = (
            session["runner"], session["task"], session["trace"], session["cancel"],
        )
        pending = task.pending_approval
        if pending is None or pending.call_id != call_id:
            raise ValueError("approval does not match the pending action")
        if arguments is not None and arguments != pending.arguments:
            raise ValueError("approval arguments do not match the pending action")
        starter = str(session.get("started_by") or "").strip()
        if approved and starter and approver.strip() == starter:
            raise ValueError("the operator who started this task cannot confirm it")
        runner.resolve_approval(
            task, approved=approved, approver=approver, call_id=call_id, cancel=cancel,
        )
        return self._view(task, trace, running=False)

    def inform(self, task_id: str, text: str) -> dict[str, Any]:
        session = self._session(task_id)
        runner, task, trace, cancel = (
            session["runner"], session["task"], session["trace"], session["cancel"],
        )
        runner.provide_information(task, text, cancel)
        return self._view(task, trace, running=False)

    def cancel(self, task_id: str) -> dict[str, Any]:
        session = self._session(task_id)
        runner, task, trace, cancel = (
            session["runner"], session["task"], session["trace"], session["cancel"],
        )
        cancel.cancel()
        with self._lock:
            if task_id in self._queue:
                self._queue = [item for item in self._queue if item != task_id]
        thread = session.get("thread")
        if thread is not None and thread.is_alive():
            # Cooperative: the worker checks the token between steps.
            return public_view(task, trace, running=True)
        runner.cancel(task, "cancelled by the operator")
        return self._view(task, trace, running=False)
