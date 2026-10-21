"""Microsoft 365 catalog entry.

Read-only Outlook mail can call Microsoft Graph after the console completes
Entra sign-in. Sending mail and every other write stay disabled. The Cursor
Teams plugin is not used here.
"""
from __future__ import annotations

from typing import Any, Mapping

import re
import urllib.parse

from .catalog import Catalog, ConnectorSpec, Effect, OperationSpec
from .endpoint import ENDPOINT, DeviceRegistry, EndpointService
from .errors import AuthenticationError, InvalidRequest, NotFound
from .microsoft_oauth import MicrosoftOAuth

_MESSAGE_ID = re.compile(r"[A-Za-z0-9_+=/\-]{8,512}\Z")
_MAIL_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "messages"],
    "properties": {
        "status": {"type": "string"},
        "detail": {"type": "string", "maxLength": 300},
        "messages": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "subject", "sender", "preview"],
                "properties": {
                    "id": {"type": "string", "maxLength": 512},
                    "subject": {"type": "string", "maxLength": 300},
                    "sender": {"type": "string", "maxLength": 200},
                    "preview": {"type": "string", "maxLength": 500},
                    "link": {"type": "string", "maxLength": 400},
                },
            },
        },
    },
}

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
    "properties": {"status": {"type": "string"}, "detail": {"type": "string", "maxLength": 300}},
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
    output_schema: dict[str, Any] | None = None,
    evidence: str = "unavailable",
) -> OperationSpec:
    return OperationSpec(
        name=name,
        summary=summary,
        effect=effect,
        scope=scope,
        input_schema=schema or _QUERY,
        output_schema=output_schema or _OBJECT_RESULT,
        provider_permissions=permissions,
        tool_name="m365_" + name,
        requires_approval=effect in {Effect.DRAFT, Effect.REVERSIBLE, Effect.CONSEQUENTIAL},
        idempotent=effect is Effect.READ,
        evidence=evidence,
    )


MICROSOFT_365 = ConnectorSpec(
    connector_id="microsoft365",
    version="0.1.0",
    service="Microsoft 365",
    summary="Outlook, Teams, files and calendar through Microsoft Graph. Not connected.",
    auth="oauth_delegated",
    operations=(
        _op("search_mail", "Search the connected mailbox.", Effect.READ, "mail:read", ("Mail.Read",),
            _QUERY, _MAIL_RESULT, "mock-tested"),
        _op("read_mail", "Read one authorised message.", Effect.READ, "mail:read", ("Mail.Read",), {
            "type": "object",
            "additionalProperties": False,
            "required": ["message_id"],
            "properties": {"message_id": {"type": "string", "minLength": 8, "maxLength": 512}},
        }, _MAIL_RESULT, evidence="mock-tested"),
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


def microsoft_configuration(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Report whether an application id is present. The id itself is never returned."""
    source = env or {}
    present = bool(str(source.get("MICROSOFT_CLIENT_ID", "")).strip())
    return {
        "status": "configured" if present else "NOT CONFIGURED",
        "client_id": "present" if present else "absent",
    }


def _clip(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else ""
    return text.replace("\r", " ").replace("\n", " ")[:limit]


def _message(item: dict[str, Any]) -> dict[str, str]:
    sender = item.get("from") if isinstance(item.get("from"), dict) else {}
    email = sender.get("emailAddress") if isinstance(sender.get("emailAddress"), dict) else {}
    row = {
        "id": _clip(item.get("id"), 180),
        "subject": _clip(item.get("subject"), 300) or "(no subject)",
        "sender": _clip(email.get("address"), 200) or "(unknown sender)",
        "preview": _clip(item.get("bodyPreview"), 500),
    }
    link = _clip(item.get("webLink"), 400)
    if link.startswith("https://"):
        row["link"] = link
    return row


class Microsoft365Client:
    """Read-only Graph mail. Sending and other writes are refused."""

    def __init__(self, oauth: MicrosoftOAuth | None = None) -> None:
        self.oauth = oauth
        self.network_calls = 0

    def apply(self, catalog: Catalog, tenant_id: str) -> None:
        record = catalog.connection(tenant_id, MICROSOFT_365.connector_id)
        bundle = self.oauth.bundle if self.oauth is not None else None
        if bundle is None:
            record.connected = False
            record.account = None
            record.granted_scopes = frozenset()
            record.detail = "Connect a work or school account before mail can be read."
            return
        record.connected = True
        record.account = bundle.account
        if self.oauth is not None and self.oauth.has_mail_read():
            record.granted_scopes = frozenset({"mail:read"})
            record.detail = "Read-only mail is connected. Sending a message is not available."
            return
        record.granted_scopes = frozenset()
        record.detail = "Signed in, but Mail.Read was not granted. Mail search is unavailable."

    def perform(self, connector_id: str, operation: str, params: dict[str, Any]) -> Any:
        if operation == "search_mail":
            return self._search(str(params.get("query", "")))
        if operation == "read_mail":
            return self._read(str(params.get("message_id", "")))
        raise AuthenticationError(
            f"Microsoft 365 {operation} is not enabled. No request was sent."
        )

    def _search(self, query: str) -> dict[str, Any]:
        cleaned = " ".join(query.replace("\\", " ").replace('"', " ").split())
        if not cleaned:
            raise InvalidRequest("mail search text is empty")
        payload = self._get("/me/messages", {
            "$search": f'"{cleaned[:200]}"',
            "$top": "5",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,webLink",
        })
        raw = payload.get("value", [])
        if not isinstance(raw, list):
            raise InvalidRequest("Microsoft Graph did not return a message list.")
        rows = [_message(item) for item in raw if isinstance(item, dict)]
        result: dict[str, Any] = {"status": "ok", "messages": rows[:5]}
        if not rows:
            result["detail"] = "No messages matched this search."
        return result

    def _read(self, message_id: str) -> dict[str, Any]:
        if (
            not _MESSAGE_ID.fullmatch(message_id)
            or ".." in message_id
            or "//" in message_id
            or message_id.startswith("/")
        ):
            raise InvalidRequest("message id is not usable")
        quoted = urllib.parse.quote(message_id, safe="")
        try:
            payload = self._get("/me/messages/" + quoted, {
                "$select": "id,subject,from,receivedDateTime,bodyPreview,webLink",
            })
        except NotFound:
            return {"status": "not_found", "messages": [], "detail": "Microsoft Graph did not find that message."}
        return {"status": "ok", "messages": [_message(payload)]}

    def _get(self, path: str, query: dict[str, str]) -> dict[str, Any]:
        if self.oauth is None or self.oauth.bundle is None:
            raise AuthenticationError("Microsoft 365 is not connected. No request was sent.")
        before = self.oauth.graph_calls
        try:
            return self.oauth.graph_get(path, query)
        finally:
            self.network_calls += self.oauth.graph_calls - before


def platform_catalog(
    oauth: MicrosoftOAuth | None = None,
    devices: DeviceRegistry | None = None,
) -> tuple[Catalog, Microsoft365Client]:
    client = Microsoft365Client(oauth)
    registry = devices if devices is not None else DeviceRegistry()
    endpoint = EndpointService(registry)

    def perform(connector_id: str, operation: str, params: dict[str, Any]) -> Any:
        if connector_id == MICROSOFT_365.connector_id:
            return client.perform(connector_id, operation, params)
        if connector_id == ENDPOINT.connector_id:
            return endpoint.perform(connector_id, operation, params)
        raise AuthenticationError(f"{connector_id} has no client. No request was sent.")

    catalog = Catalog([MICROSOFT_365, ENDPOINT], perform)
    catalog.endpoint_service = endpoint  # type: ignore[attr-defined]
    catalog.devices = registry  # type: ignore[attr-defined]
    return catalog, client
