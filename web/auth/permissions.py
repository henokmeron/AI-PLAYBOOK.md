"""Explicit role → permission matrix for console operators."""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Permission(str, Enum):
    OPS_VIEW = "ops:view"
    OPS_ALERT_WRITE = "ops:alert_write"
    OPS_INCIDENT_WRITE = "ops:incident_write"
    AGENT_VIEW = "agent:view"
    AGENT_START = "agent:start"
    AGENT_APPROVE = "agent:approve"
    CHAT = "chat:use"
    DOCS = "docs:use"
    CONNECTORS_VIEW = "connectors:view"
    CONNECTORS_MANAGE = "connectors:manage"
    ADMIN_OPERATORS = "admin:operators"


_VIEWER = frozenset({
    Permission.OPS_VIEW,
    Permission.AGENT_VIEW,
    Permission.CONNECTORS_VIEW,
    Permission.CHAT,
    Permission.DOCS,
})

_OPERATOR = _VIEWER | frozenset({
    Permission.OPS_ALERT_WRITE,
    Permission.OPS_INCIDENT_WRITE,
    Permission.AGENT_START,
    Permission.AGENT_APPROVE,
    Permission.CONNECTORS_MANAGE,
})

_ADMIN = _OPERATOR | frozenset({Permission.ADMIN_OPERATORS})

_MATRIX = {
    Role.VIEWER: _VIEWER,
    Role.OPERATOR: _OPERATOR,
    Role.ADMIN: _ADMIN,
}


def permissions_for(role: Role | str) -> frozenset[Permission]:
    if isinstance(role, str):
        role = Role(role)
    return _MATRIX[role]


def role_names() -> tuple[str, ...]:
    return tuple(item.value for item in Role)
