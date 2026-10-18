"""Auditable agent task history on local disk.

Stores only the public operator view (already redacted). Does not store system
prompts, model transcripts, or API keys. Retention is bounded.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_MAX_TASKS = 100
SUMMARY_KEYS = (
    "task_id", "state", "execution", "goal", "answer", "failure",
    "updated_at", "created_at", "running",
)


def _safe_id(task_id: str) -> str:
    if not isinstance(task_id, str) or not task_id or len(task_id) > 64:
        raise ValueError("invalid task_id")
    if any(ch for ch in task_id if ch not in "0123456789abcdefABCDEF"):
        # uuid hex is expected; also allow hyphen-free ids only
        if not all(c.isalnum() or c in "-_" for c in task_id):
            raise ValueError("invalid task_id")
    return task_id


class TaskHistoryStore:
    """Append/overwrite JSON snapshots under ``root``. Thread-safe."""

    def __init__(self, root: Path | str, *, max_tasks: int = DEFAULT_MAX_TASKS) -> None:
        self.root = Path(root)
        if max_tasks < 1 or max_tasks > 10_000:
            raise ValueError("max_tasks out of range")
        self.max_tasks = max_tasks
        self._lock = threading.Lock()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self.root / f"{_safe_id(task_id)}.json"

    def save(self, view: dict[str, Any]) -> dict[str, Any]:
        task_id = view.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("view requires task_id")
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record = dict(view)
        record.setdefault("created_at", now)
        record["updated_at"] = now
        path = self._path(task_id)
        with self._lock:
            if path.exists():
                try:
                    prior = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(prior, dict) and isinstance(prior.get("created_at"), str):
                        record["created_at"] = prior["created_at"]
                except (OSError, json.JSONDecodeError):
                    pass
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(tmp, path)
            self._prune_unlocked()
        return record

    def get(self, task_id: str) -> dict[str, Any] | None:
        path = self._path(task_id)
        with self._lock:
            if not path.exists():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        return data if isinstance(data, dict) else None

    def list(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("limit out of range")
        with self._lock:
            files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            rows: list[dict[str, Any]] = []
            for path in files[:limit]:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(data, dict):
                    continue
                rows.append({k: data.get(k) for k in SUMMARY_KEYS if k in data or k in ("task_id", "execution", "goal")})
            return rows

    def _prune_unlocked(self) -> None:
        files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[self.max_tasks:]:
            try:
                path.unlink()
            except OSError:
                pass
