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
            "licence_note": "Confirm Apache-2.0 on the exact upstream revision before commercial deployment.",
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
