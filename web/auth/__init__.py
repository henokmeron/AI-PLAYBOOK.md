"""Named-operator authentication for the loopback console."""

from .permissions import Permission, Role, permissions_for
from .service import AuthService, AuthError, OperatorRecord, SessionRecord

__all__ = [
    "AuthService",
    "AuthError",
    "OperatorRecord",
    "SessionRecord",
    "Permission",
    "Role",
    "permissions_for",
]
