"""AI Security and Operations Centre — local-first monitoring, alerts, incidents.

This package does not start the GPU model. Health probes use HTTP only so the
centre remains useful when Qwen is down. See docs/ops_centre/GAP_AND_ARCHITECTURE.md.
"""
from __future__ import annotations

from .service import OpsCentre, OpsCentreConfig

__all__ = ["OpsCentre", "OpsCentreConfig"]
