"""Remote-support boundary.

Choice: MeshCentral (self-hosted). It already has device groups, remote
desktop, and an API, so this platform does not invent a remote-control
protocol. The upstream project states the Apache 2.0 licence; confirm the
LICENSE file in the version you deploy before commercial use.

This module does not connect to MeshCentral unless MESHCENTRAL_URL is set,
and a set URL is still UNKNOWN until a health check succeeds. Screen control
is not treated as proof that a Windows repair ran.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit


_LICENCE = (
    "MeshCentral 1.2.6, published 2026-09-24, is the current GitHub release checked on 2026-10-19. "
    "The master LICENSE file is Apache License 2.0, copyright 2017-2025 Intel Corporation. "
    "Apache-2.0 allows commercial use when its notice and attribution terms are kept. "
    "This process has not downloaded or installed that release."
)


def status_from_env(environ: dict[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if environ is None else environ
    url = (source.get("MESHCENTRAL_URL") or "").strip()
    group = (source.get("MESHCENTRAL_GROUP") or "").strip()
    if not url:
        return {
            "product": "MeshCentral",
            "state": "NOT CONFIGURED",
            "checked_at": None,
            "remote_desktop_verified": False,
            "detail": "Set MESHCENTRAL_URL to the server you operate. No remote session was opened.",
            "licence_note": _LICENCE,
            "manual_steps": [
                "Install MeshCentral on a server you control.",
                "Create one device group per customer organisation.",
                "Enrol the Windows computer with the MeshAgent and show the customer the consent prompt.",
                "Put only the server URL in MESHCENTRAL_URL. Do not commit tokens.",
            ],
        }
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return {
            "product": "MeshCentral",
            "state": "DEGRADED",
            "checked_at": None,
            "remote_desktop_verified": False,
            "detail": "MESHCENTRAL_URL must be https with a hostname. No connection was attempted.",
        }
    return {
        "product": "MeshCentral",
        "state": "UNKNOWN",
        "checked_at": None,
        "remote_desktop_verified": False,
        "group_set": bool(group),
        "detail": "URL is present. This process did not log in or open a remote desktop session.",
    }


def check_remote(environ: dict[str, str] | None = None, *, timeout: float = 3) -> dict[str, Any]:
    """Probe a configured URL. A reachable page is not a remote desktop session."""
    report = status_from_env(environ)
    report["remote_desktop_verified"] = False
    report["session_established"] = False
    if report["state"] != "UNKNOWN":
        return report
    url = (os.environ if environ is None else environ).get("MESHCENTRAL_URL", "").strip()
    import urllib.error
    import urllib.request
    from datetime import datetime, timezone

    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — operator-configured URL only
            code = int(getattr(response, "status", 0) or 0)
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
    except Exception as exc:  # noqa: BLE001 — report the failure, do not claim a session
        report["state"] = "DEGRADED"
        report["availability"] = "UNAVAILABLE"
        report["checked_at"] = datetime.now(timezone.utc).isoformat()
        report["detail"] = f"UNAVAILABLE: {type(exc).__name__}. No remote session was opened."
        report["http_status"] = 0
        return report
    report["state"] = "UNKNOWN"
    report["availability"] = "REACHABLE_NOT_AUTHENTICATED"
    report["checked_at"] = datetime.now(timezone.utc).isoformat()
    report["http_status"] = code
    report["detail"] = f"HTTP {code} from the configured URL. No login and no remote desktop session were performed."
    return report


def request_session(*, operator: str, device_id: str, tenant_id: str, customer_authorised: bool) -> dict[str, Any]:
    """Record a session request. This build cannot establish the desktop connection."""
    if not operator or not device_id or not tenant_id or not customer_authorised:
        return {
            "established": False,
            "state": "denied",
            "remote_desktop_verified": False,
            "detail": "An operator, enrolled device, tenant, and recorded customer authorisation are required.",
        }
    return {
        "established": False,
        "state": "not_established",
        "remote_desktop_verified": False,
        "operator": operator,
        "device_id": device_id,
        "tenant_id": tenant_id,
        "detail": "MeshCentral is not logged in from this process. The session was not opened.",
        "llm_mouse_control": False,
        "llm_shell": False,
    }


def revoke_session(record: dict[str, Any]) -> dict[str, Any]:
    updated = dict(record)
    updated["state"] = "revoked"
    updated["established"] = False
    updated["remote_desktop_verified"] = False
    updated["detail"] = "Local session record revoked. No live MeshCentral session was connected."
    return updated


def session_requirements() -> dict[str, Any]:
    return {
        "operator_authenticated": True,
        "device_enrolled": True,
        "customer_authorisation_recorded": True,
        "scope_required": True,
        "revocation_required": True,
        "audit_required": True,
        "llm_mouse_control": False,
        "llm_shell": False,
    }
