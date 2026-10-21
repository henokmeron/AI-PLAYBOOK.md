"""Current-health window for retained agent failures.

The audit log is not trimmed here. A failure outside the window stays on disk
and is omitted from the current health decision.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Mapping

DEFAULT_WINDOW_SECONDS = 24 * 3600
MAX_WINDOW_SECONDS = 30 * 24 * 3600
_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\b")


def failure_window_seconds(env: Mapping[str, str] | None = None) -> int:
    source = os.environ if env is None else env
    raw = str(source.get("DIRECTOR_AGENT_FAILURE_WINDOW_SECONDS", "")).strip()
    if not raw:
        return DEFAULT_WINDOW_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_WINDOW_SECONDS
    if value < 60 or value > MAX_WINDOW_SECONDS:
        return DEFAULT_WINDOW_SECONDS
    return value


def parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def within_window(stamp: object, *, now: datetime, window_seconds: int) -> bool | None:
    """True inside the window, False when older, None when the stamp is unusable."""
    parsed = parse_utc(stamp)
    if parsed is None:
        return None
    return (now - parsed).total_seconds() <= window_seconds


def evidence_is_current(lines: list[object] | None, *, now: datetime, window_seconds: int) -> bool:
    """An alert stays current when any evidence line is recent or has no timestamp.

    Every line must carry an old timestamp before the alert is historical.
    This does not resolve or delete the alert.
    """
    if not lines:
        return True
    saw_old = False
    for line in lines:
        match = _STAMP.match(str(line).strip())
        if match is None:
            return True
        flag = within_window(match.group(1), now=now, window_seconds=window_seconds)
        if flag is None or flag:
            return True
        saw_old = True
    return not saw_old
