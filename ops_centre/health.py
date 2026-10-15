"""Independent service health probes — must not require Qwen to report failures."""
from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .models import ServiceHealth, ServiceState, Verification
from .store import utc_now

ProbeFn = Callable[[str, float], dict[str, Any]]


def _http_probe(url: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — configured loopback
            code = int(getattr(response, "status", 0) or 0)
            body = response.read(400).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "http_status": int(exc.code),
            "detail": f"HTTP {exc.code}",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "body": "",
        }
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {
            "ok": False,
            "http_status": 0,
            "detail": f"{type(exc).__name__}: {exc}"[:200],
            "latency_ms": int((time.monotonic() - started) * 1000),
            "body": "",
        }
    return {
        "ok": 200 <= code < 400,
        "http_status": code,
        "detail": (body[:120] if body and not body.lstrip().lower().startswith("<!") else f"HTTP {code}"),
        "latency_ms": int((time.monotonic() - started) * 1000),
        "body": body,
    }


class HealthAggregator:
    """Layered checks: liveness → readiness. Never marks healthy without a probe."""

    def __init__(
        self,
        *,
        qwen_url: str | None = None,
        gateway_live_url: str | None = None,
        gateway_ready_url: str | None = None,
        console_url: str | None = None,
        probe: ProbeFn | None = None,
        timeout: float = 2.5,
    ) -> None:
        self.qwen_url = qwen_url or os.environ.get("OPS_QWEN_URL", "http://127.0.0.1:8002/health")
        self.gateway_live_url = gateway_live_url or os.environ.get(
            "OPS_GATEWAY_LIVE_URL", "http://127.0.0.1:8010/livez"
        )
        self.gateway_ready_url = gateway_ready_url or os.environ.get(
            "OPS_GATEWAY_READY_URL", "http://127.0.0.1:8010/readyz"
        )
        self.console_url = console_url or os.environ.get("OPS_CONSOLE_URL", "http://127.0.0.1:8080/api/status")
        self._probe = probe or _http_probe
        self._timeout = timeout

    def _one(
        self,
        name: str,
        url: str,
        *,
        check_kind: str,
        interpret: Callable[[dict[str, Any]], tuple[str, str]] | None = None,
    ) -> ServiceHealth:
        verified_at = utc_now()
        result = self._probe(url, self._timeout)
        if interpret is None:
            state = ServiceState.HEALTHY.value if result.get("ok") else ServiceState.UNAVAILABLE.value
            detail = str(result.get("detail") or "")
        else:
            state, detail = interpret(result)
        return ServiceHealth(
            name=name,
            state=state,
            verification=Verification.OBSERVED.value,
            verified_at=verified_at,
            latency_ms=result.get("latency_ms"),
            http_status=result.get("http_status"),
            detail=detail[:300],
            check_kind=check_kind,
        )

    def snapshot(self) -> dict[str, Any]:
        services: list[ServiceHealth] = []

        def gateway_live(result: dict[str, Any]) -> tuple[str, str]:
            if not result.get("ok"):
                return ServiceState.UNAVAILABLE.value, str(result.get("detail") or "unreachable")
            return ServiceState.HEALTHY.value, "process alive"

        def gateway_ready(result: dict[str, Any]) -> tuple[str, str]:
            if result.get("http_status") == 503:
                return ServiceState.DEGRADED.value, "alive but upstream not ready"
            if not result.get("ok"):
                return ServiceState.UNAVAILABLE.value, str(result.get("detail") or "unreachable")
            return ServiceState.HEALTHY.value, "upstream ready"

        def console_status(result: dict[str, Any]) -> tuple[str, str]:
            if not result.get("ok"):
                return ServiceState.UNAVAILABLE.value, str(result.get("detail") or "unreachable")
            try:
                payload = json.loads(result.get("body") or "{}")
            except json.JSONDecodeError:
                return ServiceState.DEGRADED.value, "console responded but status JSON was invalid"
            connection = str(payload.get("connection") or "unknown")
            if connection == "ready":
                return ServiceState.HEALTHY.value, f"connection={connection}"
            if connection in {"degraded", "unreachable", "misconfigured"}:
                return ServiceState.DEGRADED.value, f"connection={connection}"
            return ServiceState.UNKNOWN.value, f"connection={connection}"

        services.append(self._one("gateway_live", self.gateway_live_url, check_kind="liveness", interpret=gateway_live))
        services.append(self._one("gateway_ready", self.gateway_ready_url, check_kind="readiness", interpret=gateway_ready))
        services.append(self._one("qwen", self.qwen_url, check_kind="liveness"))
        services.append(self._one("console", self.console_url, check_kind="functional", interpret=console_status))

        # Local resources — observed when readable; unknown otherwise (no fake numbers).
        disk = self._disk_health()
        services.append(disk)

        overall = self._overall(services)
        return {
            "overall": overall,
            "verification": Verification.OBSERVED.value,
            "verified_at": utc_now(),
            "services": [s.to_public() for s in services],
            "note": (
                "Statuses are from fresh HTTP/local probes in this process. "
                "Unavailable Qwen does not prevent reporting other failures."
            ),
        }

    def _disk_health(self) -> ServiceHealth:
        verified_at = utc_now()
        roots = []
        for candidate in (Path("/workspace"), Path("/tmp"), Path(".")):
            try:
                if candidate.exists():
                    roots.append(candidate)
            except OSError:
                continue
        if not roots:
            return ServiceHealth(
                name="disk",
                state=ServiceState.UNKNOWN.value,
                verification=Verification.UNKNOWN.value,
                verified_at=verified_at,
                detail="no readable path to measure",
                check_kind="functional",
            )
        parts = []
        worst = ServiceState.HEALTHY.value
        for root in roots[:3]:
            try:
                usage = shutil.disk_usage(root)
            except OSError as exc:
                parts.append(f"{root}: error {exc}")
                worst = ServiceState.UNKNOWN.value
                continue
            free_pct = (usage.free / usage.total * 100.0) if usage.total else 0.0
            parts.append(
                f"{root}: free={usage.free // (1024**3)}GiB ({free_pct:.0f}%)"
            )
            if free_pct < 5:
                worst = ServiceState.UNAVAILABLE.value
            elif free_pct < 15 and worst == ServiceState.HEALTHY.value:
                worst = ServiceState.DEGRADED.value
        return ServiceHealth(
            name="disk",
            state=worst,
            verification=Verification.OBSERVED.value,
            verified_at=verified_at,
            detail="; ".join(parts)[:400],
            check_kind="functional",
        )

    @staticmethod
    def _overall(services: list[ServiceHealth]) -> str:
        states = {s.state for s in services}
        if ServiceState.UNAVAILABLE.value in states:
            return ServiceState.UNAVAILABLE.value
        if ServiceState.DEGRADED.value in states or ServiceState.UNKNOWN.value in states:
            return ServiceState.DEGRADED.value
        if states == {ServiceState.HEALTHY.value}:
            return ServiceState.HEALTHY.value
        return ServiceState.UNKNOWN.value
