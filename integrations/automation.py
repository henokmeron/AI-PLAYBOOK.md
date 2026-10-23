"""Durable automation boundary for sensitive actions.

The agent queue already pauses for approval. This store is the record that
survives a process restart. The same idempotency key does not run an action
twice. Power Automate is not connected: without a webhook URL the action is
NOT TESTED and no request is sent.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable

_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,80}\Z")
_ACTION = re.compile(r"[a-z][a-z0-9._]{0,63}\Z")
_SECRET_KEYS = frozenset({"password", "token", "secret", "api_key", "authorization"})
SENSITIVE_ACTIONS = frozenset({"repair.execute", "mail.send", "power_automate.run"})
POWER_AUTOMATE_ACTION = "power_automate.run"
MAX_ATTEMPTS = 3
LIVE_POWER_AUTOMATE = "NOT TESTED"


class AutomationError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def power_automate_configured(env: dict[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return bool(str(source.get("POWER_AUTOMATE_WEBHOOK_URL") or "").strip())


class AutomationStore:
    def __init__(self, root: Path | str, *, env: dict[str, str] | None = None) -> None:
        self.root = Path(root)
        self._env = env
        self._lock = threading.Lock()
        self._tasks: dict[str, dict[str, Any]] = {}
        self._by_key: dict[str, str] = {}
        self._load()

    def submit(
        self,
        *,
        action: Any,
        idempotency_key: Any,
        actor: Any,
        idempotent: bool,
        payload: dict[str, Any] | None = None,
        agent_task_id: str | None = None,
    ) -> dict[str, Any]:
        name = self._action(action)
        key = self._key(idempotency_key)
        who = self._actor(actor)
        body = self._payload(payload or {})
        sensitive = name in SENSITIVE_ACTIONS
        with self._lock:
            existing_id = self._by_key.get(key)
            if existing_id is not None:
                view = self._public(self._tasks[existing_id])
                view["duplicate"] = True
                view["ran"] = False
                return view
            task_id = f"auto-{len(self._tasks) + 1:04d}-{key[:12]}"
            task = {
                "id": task_id,
                "action": name,
                "idempotency_key": key,
                "actor": who,
                "idempotent": bool(idempotent),
                "sensitive": sensitive,
                "payload": body,
                "agent_task_id": agent_task_id if isinstance(agent_task_id, str) and agent_task_id else None,
                "status": "awaiting_approval" if sensitive else "queued",
                "attempts": 0,
                "approval": None,
                "live_power_automate": LIVE_POWER_AUTOMATE if name == POWER_AUTOMATE_ACTION else None,
            }
            self._tasks[task_id] = task
            self._by_key[key] = task_id
            self._save_locked()
            view = self._public(task)
            view["duplicate"] = False
            view["ran"] = False
            return view

    def approve(self, task_id: str, approver: Any) -> dict[str, Any]:
        who = self._actor(approver)
        with self._lock:
            task = self._require(task_id)
            if not task["sensitive"]:
                raise AutomationError("this action does not require approval")
            if task["status"] == "completed":
                raise AutomationError("task is already completed")
            task["status"] = "approved"
            task["approval"] = {"approver": who}
            self._save_locked()
            view = self._public(task)
            view["ran"] = False
            return view

    def run(
        self,
        task_id: str,
        runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            task = self._require(task_id)
            if task["status"] in {"completed", "not_tested"}:
                view = self._public(task)
                view["duplicate"] = True
                view["ran"] = False
                return view
            if task["sensitive"] and task["status"] != "approved":
                view = self._public(task)
                view["ran"] = False
                view["repair_status"] = "approval_required"
                return view
            if task["action"] == POWER_AUTOMATE_ACTION and not power_automate_configured(self._env):
                task["status"] = "not_tested"
                task["live_power_automate"] = LIVE_POWER_AUTOMATE
                self._save_locked()
                view = self._public(task)
                view["ran"] = False
                return view
            if task["status"] == "failed" and not task["idempotent"]:
                view = self._public(task)
                view["ran"] = False
                return view
            if task["attempts"] >= MAX_ATTEMPTS:
                task["status"] = "failed"
                self._save_locked()
                view = self._public(task)
                view["ran"] = False
                return view
            task["attempts"] += 1
            attempt = task["attempts"]
            action = task["action"]
            payload = dict(task["payload"])
        if runner is None:
            with self._lock:
                task = self._tasks[task_id]
                task["status"] = "failed"
                self._save_locked()
                view = self._public(task)
                view["ran"] = False
                return view
        try:
            outcome = runner({"action": action, "payload": payload, "attempt": attempt})
        except Exception:
            with self._lock:
                task = self._tasks[task_id]
                if task["idempotent"] and task["attempts"] < MAX_ATTEMPTS:
                    task["status"] = "retrying"
                else:
                    task["status"] = "failed"
                self._save_locked()
                view = self._public(task)
                view["ran"] = True
                return view
        with self._lock:
            task = self._tasks[task_id]
            task["status"] = "completed"
            task["result"] = outcome if isinstance(outcome, dict) else {"ok": True}
            self._save_locked()
            view = self._public(task)
            view["ran"] = True
            return view

    def get(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            return self._public(self._require(task_id))

    def _public(self, task: dict[str, Any]) -> dict[str, Any]:
        view = {
            "id": task["id"],
            "action": task["action"],
            "status": task["status"],
            "idempotent": task["idempotent"],
            "sensitive": task["sensitive"],
            "attempts": task["attempts"],
            "agent_task_id": task.get("agent_task_id"),
            "approval": dict(task["approval"]) if task.get("approval") else None,
            "live_power_automate": task.get("live_power_automate"),
        }
        return view

    def _require(self, task_id: str) -> dict[str, Any]:
        if not isinstance(task_id, str) or task_id not in self._tasks:
            raise AutomationError("task not found")
        return self._tasks[task_id]

    def _action(self, value: Any) -> str:
        if not isinstance(value, str) or not _ACTION.fullmatch(value):
            raise AutomationError("action is not allowed")
        return value

    def _key(self, value: Any) -> str:
        if not isinstance(value, str) or not _KEY.fullmatch(value):
            raise AutomationError("idempotency key is required")
        return value

    def _actor(self, value: Any) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}", value):
            raise AutomationError("actor is required")
        return value

    def _payload(self, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise AutomationError("payload must be an object")
        for key in value:
            if str(key).casefold() in _SECRET_KEYS:
                raise AutomationError("payload cannot contain a secret")
        encoded = json.dumps(value, sort_keys=True)
        if len(encoded) > 4000:
            raise AutomationError("payload is too large")
        return json.loads(encoded)

    def _load(self) -> None:
        path = self.root / "automation.json"
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, list):
            return
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("idempotency_key"), str):
                self._tasks[item["id"]] = item
                self._by_key[item["idempotency_key"]] = item["id"]

    def _save_locked(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "automation.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(list(self._tasks.values()), sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
