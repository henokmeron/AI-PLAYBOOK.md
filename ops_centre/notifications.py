"""Notification adapters. Secrets must come from the environment, never source."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .models import Alert


class Notifier(Protocol):
    def send_alert(self, alert: Alert) -> dict[str, Any]: ...


@dataclass
class NullNotifier:
    """Default: in-dashboard only. Always safe when no channel is configured."""

    def send_alert(self, alert: Alert) -> dict[str, Any]:
        return {
            "delivered": False,
            "channel": "none",
            "detail": "No external notifier configured; alert remains in the Operations dashboard.",
            "alert_id": alert.alert_id,
        }


def build_notifier() -> Notifier:
    # Future: email/webhook when OPS_NOTIFY_WEBHOOK_URL and secrets are set deliberately.
    return NullNotifier()
