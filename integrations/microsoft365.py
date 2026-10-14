"""Microsoft 365 catalog entry.

This does not call Microsoft Graph. Until an account is connected through the
platform's own consent flow, every operation stops before a network request.
The Cursor Teams plugin is not used here: it talks to Cursor's own service.
"""
from __future__ import annotations

from typing import Any

from .catalog import Catalog, ConnectorSpec, Effect, OperationSpec
from .errors import AuthenticationError

_QUERY = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 500}},
}
_OBJECT_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status"],
    "properties": {"status": {"type": "string"}, "detail": {"type": "string"}},
}
_MESSAGE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["to", "subject", "body"],
    "properties": {
        "to": {"type": "string", "minLength": 3, "maxLength": 200},
        "subject": {"type": "string", "minLength": 1, "maxLength": 200},
        "body": {"type": "string", "minLength": 1, "maxLength": 8000},
    },
}


def _op(
    name: str,
    summary: str,
    effect: Effect,
    scope: str,
    permissions: tuple[str, ...],
    schema: dict[str, Any] | None = None,
) -> OperationSpec:
    return OperationSpec(
        name=name,
        summary=summary,
        effect=effect,
        scope=scope,
        input_schema=schema or _QUERY,
        output_schema=_OBJECT_RESULT,
        provider_permissions=permissions,
        tool_name="m365_" + name,
        requires_approval=effect in {Effect.REVERSIBLE, Effect.CONSEQUENTIAL},
        idempotent=effect is Effect.READ,
    )


MICROSOFT_365 = ConnectorSpec(
    connector_id="microsoft365",
    version="0.1.0",
    service="Microsoft 365",
    summary="Outlook, Teams, files and calendar through Microsoft Graph. Not connected.",
    auth="oauth_delegated",
    operations=(
        _op("search_mail", "Search the connected mailbox.", Effect.READ, "mail:read", ("Mail.Read",)),
        _op("read_mail", "Read one authorised message.", Effect.READ, "mail:read", ("Mail.Read",), {
            "type": "object",
            "additionalProperties": False,
            "required": ["message_id"],
            "properties": {"message_id": {"type": "string", "minLength": 1, "maxLength": 200}},
        }),
        _op("create_mail_draft", "Create an unsent mail draft.", Effect.DRAFT, "mail:write",
            ("Mail.ReadWrite",), _MESSAGE),
        _op("send_mail", "Send an email.", Effect.CONSEQUENTIAL, "mail:write", ("Mail.Send",), _MESSAGE),
        _op("search_teams_messages", "Search Teams chats and channel messages the account can read.",
            Effect.READ, "teams:read", ("Chat.Read", "ChannelMessage.Read.All")),
        _op("send_teams_message", "Send a Teams chat or channel message.", Effect.CONSEQUENTIAL,
            "teams:write", ("Chat.ReadWrite", "ChannelMessage.Send"), {
                "type": "object",
                "additionalProperties": False,
                "required": ["conversation_id", "body"],
                "properties": {
                    "conversation_id": {"type": "string", "minLength": 1, "maxLength": 200},
                    "body": {"type": "string", "minLength": 1, "maxLength": 8000},
                },
            }),
        _op("search_files", "Search files the account can read in OneDrive or SharePoint.",
            Effect.READ, "files:read", ("Files.Read",)),
        _op("list_calendar", "List events on the connected calendar.", Effect.READ, "calendar:read",
            ("Calendars.Read",)),
        _op("update_calendar_event", "Change or create a calendar event.", Effect.CONSEQUENTIAL,
            "calendar:write", ("Calendars.ReadWrite",), {
                "type": "object",
                "additionalProperties": False,
                "required": ["summary"],
                "properties": {"summary": {"type": "string", "minLength": 1, "maxLength": 300}},
            }),
    ),
)


class Microsoft365Client:
    """Placeholder. ``network_calls`` stays zero until a Graph client exists."""

    def __init__(self) -> None:
        self.network_calls = 0

    def perform(self, connector_id: str, operation: str, params: dict[str, Any]) -> Any:
        raise AuthenticationError("Microsoft 365 is not connected. No request was sent.")


def platform_catalog() -> tuple[Catalog, Microsoft365Client]:
    client = Microsoft365Client()

    def perform(connector_id: str, operation: str, params: dict[str, Any]) -> Any:
        if connector_id != MICROSOFT_365.connector_id:
            raise AuthenticationError(f"{connector_id} has no client")
        return client.perform(connector_id, operation, params)

    return Catalog([MICROSOFT_365], perform), client
