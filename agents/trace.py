"""Redacted execution records for agent runs.

Records hold metadata (states, tool names, redacted arguments, short result
previews, budgets). They never include the system prompt or full documents.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .redaction import redact, redact_text

PREVIEW_CHARS = 300


@dataclass
class TraceEvent:
    seq: int
    at: float
    task_id: str
    kind: str
    state: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq, "at": self.at, "task_id": self.task_id,
            "kind": self.kind, "state": self.state, "data": self.data,
        }


class ExecutionTrace:
    def __init__(
        self,
        sink_path: Path | None = None,
        clock: Callable[[], float] = time.time,
        known_secrets: frozenset[str] = frozenset(),
    ) -> None:
        self.events: list[TraceEvent] = []
        self._sink_path = sink_path
        self._clock = clock
        self._secrets = known_secrets

    def record(self, task_id: str, kind: str, state: str, **data: Any) -> TraceEvent:
        event = TraceEvent(
            seq=len(self.events) + 1,
            at=round(self._clock(), 3),
            task_id=task_id,
            kind=kind,
            state=state,
            data=redact(data, self._secrets),
        )
        self.events.append(event)
        if self._sink_path is not None:
            with self._sink_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event.to_dict(), sort_keys=True, default=str) + "\n")
        return event

    def preview(self, text: str) -> str:
        cleaned = redact_text(text, self._secrets)
        return cleaned if len(cleaned) <= PREVIEW_CHARS else cleaned[:PREVIEW_CHARS] + "..."

    def kinds(self) -> list[str]:
        return [event.kind for event in self.events]
