"""Controlled agent foundation (prototype). Stdlib only; see docs/agents/README.md."""
from __future__ import annotations

from .model import ModelError, ModelReply, OpenAICompatibleClient, ScriptedModel
from .runtime import AgentRunner, CancellationToken
from .state import AgentTask, Budget, TaskState
from .tools import Tool, ToolRegistry
from .trace import ExecutionTrace

__all__ = [
    "AgentRunner", "AgentTask", "Budget", "CancellationToken", "ExecutionTrace",
    "ModelError", "ModelReply", "OpenAICompatibleClient", "ScriptedModel",
    "TaskState", "Tool", "ToolRegistry",
]
