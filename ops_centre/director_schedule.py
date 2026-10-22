"""Durable schedule for the Operations Director report.

The schedule is a private JSON file. It does not start the model, the
console, or any paid service. A missed interval is recorded and the next
run is still due. The report itself stays read-only.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from integrations.state_guard import assert_private, restrict_private

from .service import OpsCentre

DEFAULT_INTERVAL_SECONDS = 3600
MIN_INTERVAL_SECONDS = 300
MAX_INTERVAL_SECONDS = 86400 * 7


class DirectorScheduleError(ValueError):
    """Schedule file or interval is not usable."""


def default_schedule_path() -> Path:
    raw = os.environ.get("DIRECTOR_SCHEDULE_FILE", "").strip()
    if raw:
        return Path(raw)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "AI-PLAYBOOK" / "director-schedule.json"


def _default_builder(centre: OpsCentre) -> dict[str, Any]:
    from .director import build_report

    return build_report(centre)


class DirectorSchedule:
    def __init__(
        self,
        path: Path | None = None,
        *,
        clock: Callable[[], float] = time.time,
        builder: Callable[[OpsCentre], dict[str, Any]] | None = None,
    ) -> None:
        self.path = path or default_schedule_path()
        self._clock = clock
        self._builder = builder or _default_builder
        self._lock = threading.RLock()
        self.enabled = False
        self.interval_seconds = DEFAULT_INTERVAL_SECONDS
        self.next_due_at: float | None = None
        self.last_run_at: float | None = None
        self.last_outcome: str | None = None
        self.last_error: str | None = None
        self.missed_runs = 0
        if self.path.is_file():
            self._load()

    def configure(self, *, enabled: bool, interval_seconds: int | None = None) -> dict[str, Any]:
        with self._lock:
            if interval_seconds is not None:
                interval = int(interval_seconds)
                if interval < MIN_INTERVAL_SECONDS or interval > MAX_INTERVAL_SECONDS:
                    raise DirectorScheduleError(
                        f"interval must be between {MIN_INTERVAL_SECONDS} and {MAX_INTERVAL_SECONDS} seconds"
                    )
                self.interval_seconds = interval
            self.enabled = bool(enabled)
            now = self._clock()
            if self.enabled and self.next_due_at is None:
                self.next_due_at = now + self.interval_seconds
            if not self.enabled:
                self.next_due_at = None
            self._save()
            return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "available": True,
                "enabled": self.enabled,
                "interval_seconds": self.interval_seconds,
                "next_due_at": self.next_due_at,
                "last_run_at": self.last_run_at,
                "last_outcome": self.last_outcome,
                "last_error": self.last_error,
                "missed_runs": self.missed_runs,
                "due": bool(
                    self.enabled
                    and self.next_due_at is not None
                    and self._clock() >= float(self.next_due_at)
                ),
                "path": str(self.path),
            }

    def run_due(self, centre: OpsCentre, *, force: bool = False) -> dict[str, Any] | None:
        with self._lock:
            now = self._clock()
            if not force:
                if not self.enabled or self.next_due_at is None:
                    return None
                if now < float(self.next_due_at):
                    return None
                overdue = now - float(self.next_due_at)
                if overdue >= self.interval_seconds:
                    self.missed_runs += int(overdue // self.interval_seconds)
            try:
                report = self._builder(centre)
                outcome = str(report.get("overall") or "unknown").lower().replace(" ", "_")
                self.last_run_at = now
                self.last_outcome = outcome
                self.last_error = None
                self.next_due_at = now + self.interval_seconds
                centre.record_event(
                    event_type="director.schedule.run",
                    component="director",
                    outcome=outcome,
                    severity="info",
                    actor="director_schedule",
                    summary=f"Scheduled Director report overall {report.get('overall')}",
                    detail={
                        "missed_runs": self.missed_runs,
                        "forced": force,
                        "interval_seconds": self.interval_seconds,
                    },
                )
                self._save()
                return report
            except Exception as exc:  # noqa: BLE001 — durable schedule must survive a bad report
                self.last_run_at = now
                self.last_outcome = "failed"
                self.last_error = type(exc).__name__
                self.next_due_at = now + self.interval_seconds
                centre.record_event(
                    event_type="director.schedule.failed",
                    component="director",
                    outcome="failed",
                    severity="warning",
                    actor="director_schedule",
                    summary="Scheduled Director report failed",
                    detail={"error": type(exc).__name__, "missed_runs": self.missed_runs},
                )
                self._save()
                raise

    def _save(self) -> None:
        payload = {
            "version": 1,
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "next_due_at": self.next_due_at,
            "last_run_at": self.last_run_at,
            "last_outcome": self.last_outcome,
            "last_error": self.last_error,
            "missed_runs": self.missed_runs,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        restrict_private(temporary)
        from integrations.state_guard import replace_file
        replace_file(temporary, self.path)
        restrict_private(self.path)
        assert_private(self.path)

    def _load(self) -> None:
        try:
            assert_private(self.path)
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise DirectorScheduleError("director schedule file is not usable") from exc
        if not isinstance(raw, dict) or raw.get("version") != 1:
            raise DirectorScheduleError("director schedule file is not usable")
        self.enabled = bool(raw.get("enabled"))
        self.interval_seconds = int(raw.get("interval_seconds") or DEFAULT_INTERVAL_SECONDS)
        self.next_due_at = raw.get("next_due_at")
        self.last_run_at = raw.get("last_run_at")
        self.last_outcome = raw.get("last_outcome")
        self.last_error = raw.get("last_error")
        self.missed_runs = int(raw.get("missed_runs") or 0)
