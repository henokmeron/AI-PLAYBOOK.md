"""Microsoft 365 and Azure catalog entries.

Read-only Graph and Azure inventory call Microsoft only after Entra sign-in.
Sending mail and every Azure write stay disabled. Live connectivity requires
MICROSOFT_CLIENT_ID and account consent.
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
    "properties": {
        "status": {"type": "string"},
        "detail": {"type": "string", "maxLength": 300},
        "items": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "name"],
                "properties": {
                    "id": {"type": "string", "maxLength": 512},
                    "name": {"type": "string", "maxLength": 300},
                    "detail": {"type": "string", "maxLength": 500},
                    "link": {"type": "string", "maxLength": 400},
                },
            },
        },
    },
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
    version="0.2.0",
    service="Microsoft 365",
    summary="Outlook, Teams, OneDrive and SharePoint through Microsoft Graph.",
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
        _op(
            "search_teams_messages",
            "Search recent Teams chats the account can read.",
            Effect.READ,
            "teams:read",
            ("Chat.Read",),
            _QUERY,
            _OBJECT_RESULT,
            "mock-tested",
        ),
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
        _op(
            "search_files",
            "Search OneDrive files the account can read.",
            Effect.READ,
            "files:read",
            ("Files.Read",),
            _QUERY,
            _OBJECT_RESULT,
            "mock-tested",
        ),
        _op(
            "search_sharepoint",
            "Search SharePoint sites and drives the account can read.",
            Effect.READ,
            "sites:read",
            ("Sites.Read.All",),
            _QUERY,
            _OBJECT_RESULT,
            "mock-tested",
        ),
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

AZURE = ConnectorSpec(
    connector_id="azure",
    version="0.1.0",
    service="Microsoft Azure",
    summary="Read-only Azure subscription and resource inventory.",
    auth="oauth_delegated",
    operations=(
        OperationSpec(
            name="list_subscriptions",
            summary="List Azure subscriptions the signed-in account can read.",
            effect=Effect.READ,
            scope="azure:read",
            input_schema={"type": "object", "additionalProperties": False, "properties": {}},
            output_schema=_OBJECT_RESULT,
            provider_permissions=("user_impersonation",),
            tool_name="azure_list_subscriptions",
            requires_approval=False,
            idempotent=True,
            evidence="mock-tested",
        ),
        OperationSpec(
            name="list_resources",
            summary="List resources in one Azure subscription the account can read.",
            effect=Effect.READ,
            scope="azure:read",
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["subscription_id"],
                "properties": {
                    "subscription_id": {"type": "string", "minLength": 8, "maxLength": 64},
                },
            },
            output_schema=_OBJECT_RESULT,
            provider_permissions=("user_impersonation",),
            tool_name="azure_list_resources",
            requires_approval=False,
            idempotent=True,
            evidence="mock-tested",
        ),
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


def _item(row_id: str, name: str, detail: str = "", link: str = "") -> dict[str, str]:
    item = {"id": _clip(row_id, 180), "name": _clip(name, 300) or "(unnamed)"}
    if detail:
        item["detail"] = _clip(detail, 500)
    if link.startswith("https://"):
        item["link"] = _clip(link, 400)
    return item


class Microsoft365Client:
    """Graph and Azure reads. Sending mail and Azure writes are refused."""

    def __init__(self, oauth: MicrosoftOAuth | None = None) -> None:
        self.oauth = oauth
        self.network_calls = 0

    def apply(self, catalog: Catalog, tenant_id: str) -> None:
        record = catalog.connection(tenant_id, MICROSOFT_365.connector_id)
        azure = catalog.connection(tenant_id, AZURE.connector_id)
        bundle = self.oauth.bundle if self.oauth is not None else None
        if bundle is None:
            record.connected = False
            record.account = None
            record.granted_scopes = frozenset()
            record.detail = "Connect a work or school account before mail, Teams, or files can be read."
            azure.connected = False
            azure.account = None
            azure.granted_scopes = frozenset()
            azure.detail = "Azure inventory is NOT CONFIGURED until Microsoft sign-in grants ARM access."
            return
        record.connected = True
        record.account = bundle.account
        granted: set[str] = set()
        assert self.oauth is not None
        if self.oauth.has_mail_read():
            granted.add("mail:read")
        if self.oauth.has_graph_scope("Chat.Read"):
            granted.add("teams:read")
        if self.oauth.has_graph_scope("Files.Read"):
            granted.add("files:read")
        if self.oauth.has_graph_scope("Sites.Read.All"):
            granted.add("sites:read")
        record.granted_scopes = frozenset(granted)
        if granted:
            record.detail = "Read-only Microsoft Graph is connected. Sending mail is not available."
        else:
            record.detail = "Signed in, but no read scopes were granted for mail, Teams, or files."
        azure.connected = self.oauth.has_azure_read()
        azure.account = bundle.account
        if azure.connected:
            azure.granted_scopes = frozenset({"azure:read"})
            azure.detail = "Read-only Azure inventory is connected. Resource changes are not available."
        else:
            azure.granted_scopes = frozenset()
            azure.detail = "Azure inventory is NOT CONFIGURED. ARM user_impersonation was not granted."

    def perform(self, connector_id: str, operation: str, params: dict[str, Any]) -> Any:
        if connector_id == AZURE.connector_id:
            return self._azure(operation, params)
        if operation == "search_mail":
            return self._search_mail(str(params.get("query", "")))
        if operation == "read_mail":
            return self._read_mail(str(params.get("message_id", "")))
        if operation == "search_teams_messages":
            return self._search_teams(str(params.get("query", "")))
        if operation == "search_files":
            return self._search_files(str(params.get("query", "")))
        if operation == "search_sharepoint":
            return self._search_sharepoint(str(params.get("query", "")))
        raise AuthenticationError(
            f"Microsoft 365 {operation} is not enabled. No request was sent."
        )

    def _search_mail(self, query: str) -> dict[str, Any]:
        cleaned = " ".join(query.replace("\\", " ").replace('"', " ").split())
        if not cleaned:
            raise InvalidRequest("mail search text is empty")
        payload = self._graph("/me/messages", {
            "$search": f'"{cleaned[:200]}"',
            "$top": "5",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,webLink",
        }, "Mail.Read")
        raw = payload.get("value", [])
        if not isinstance(raw, list):
            raise InvalidRequest("Microsoft Graph did not return a message list.")
        rows = [_message(item) for item in raw if isinstance(item, dict)]
        result: dict[str, Any] = {"status": "ok", "messages": rows[:5]}
        if not rows:
            result["detail"] = "No messages matched this search."
        return result

    def _read_mail(self, message_id: str) -> dict[str, Any]:
        if (
            not _MESSAGE_ID.fullmatch(message_id)
            or ".." in message_id
            or "//" in message_id
            or message_id.startswith("/")
        ):
            raise InvalidRequest("message id is not usable")
        quoted = urllib.parse.quote(message_id, safe="")
        try:
            payload = self._graph("/me/messages/" + quoted, {
                "$select": "id,subject,from,receivedDateTime,bodyPreview,webLink",
            }, "Mail.Read")
        except NotFound:
            return {"status": "not_found", "messages": [], "detail": "Microsoft Graph did not find that message."}
        return {"status": "ok", "messages": [_message(payload)]}

    def _search_teams(self, query: str) -> dict[str, Any]:
        cleaned = " ".join(query.split())
        if not cleaned:
            raise InvalidRequest("Teams search text is empty")
        payload = self._graph("/me/chats", {"$top": "20", "$select": "id,topic,chatType"}, "Chat.Read")
        raw = payload.get("value", [])
        if not isinstance(raw, list):
            raise InvalidRequest("Microsoft Graph did not return a chat list.")
        needle = cleaned.casefold()
        items = []
        for chat in raw:
            if not isinstance(chat, dict):
                continue
            name = _clip(chat.get("topic") or chat.get("chatType") or "chat", 300)
            if needle not in name.casefold() and needle not in _clip(chat.get("id"), 180).casefold():
                continue
            items.append(_item(str(chat.get("id") or ""), name, _clip(chat.get("chatType"), 100)))
            if len(items) >= 10:
                break
        result: dict[str, Any] = {"status": "ok", "items": items}
        if not items:
            result["detail"] = "No Teams chats matched this search."
        return result

    def _search_files(self, query: str) -> dict[str, Any]:
        cleaned = " ".join(query.replace("'", " ").replace('"', " ").split())
        if not cleaned:
            raise InvalidRequest("file search text is empty")
        safe = cleaned[:120].replace("\\", " ")
        payload = self._graph(
            f"/me/drive/root/search(q='{safe}')",
            {"$top": "10", "$select": "id,name,webUrl,size"},
            "Files.Read",
        )
        raw = payload.get("value", [])
        if not isinstance(raw, list):
            raise InvalidRequest("Microsoft Graph did not return a file list.")
        items = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            size = row.get("size")
            detail = f"size={size}" if isinstance(size, int) else ""
            items.append(_item(str(row.get("id") or ""), str(row.get("name") or ""), detail, str(row.get("webUrl") or "")))
            if len(items) >= 10:
                break
        result: dict[str, Any] = {"status": "ok", "items": items}
        if not items:
            result["detail"] = "No OneDrive files matched this search."
        return result

    def _search_sharepoint(self, query: str) -> dict[str, Any]:
        cleaned = " ".join(query.replace("'", " ").split())
        if not cleaned:
            raise InvalidRequest("SharePoint search text is empty")
        payload = self._graph(
            "/sites",
            {"search": cleaned[:120], "$top": "10", "$select": "id,displayName,webUrl,description"},
            "Sites.Read.All",
        )
        raw = payload.get("value", [])
        if not isinstance(raw, list):
            raise InvalidRequest("Microsoft Graph did not return a site list.")
        items = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            items.append(_item(
                str(row.get("id") or ""),
                str(row.get("displayName") or ""),
                _clip(row.get("description"), 500),
                str(row.get("webUrl") or ""),
            ))
            if len(items) >= 10:
                break
        result: dict[str, Any] = {"status": "ok", "items": items}
        if not items:
            result["detail"] = "No SharePoint sites matched this search."
        return result

    def _azure(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        if operation == "list_subscriptions":
            payload = self._arm("/subscriptions", {"api-version": "2020-01-01"})
            raw = payload.get("value", [])
            if not isinstance(raw, list):
                raise InvalidRequest("Azure did not return a subscription list.")
            items = []
            for row in raw:
                if not isinstance(row, dict):
                    continue
                items.append(_item(
                    str(row.get("subscriptionId") or row.get("id") or ""),
                    str(row.get("displayName") or "subscription"),
                    _clip(row.get("state"), 100),
                ))
                if len(items) >= 10:
                    break
            result: dict[str, Any] = {"status": "ok", "items": items}
            if not items:
                result["detail"] = "No Azure subscriptions were returned for this account."
            return result
        if operation == "list_resources":
            sub = str(params.get("subscription_id") or "").strip()
            if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", sub):
                raise InvalidRequest("subscription id is not usable")
            payload = self._arm(
                f"/subscriptions/{urllib.parse.quote(sub, safe='')}/resources",
                {"api-version": "2021-04-01", "$top": "10"},
            )
            raw = payload.get("value", [])
            if not isinstance(raw, list):
                raise InvalidRequest("Azure did not return a resource list.")
            items = []
            for row in raw:
                if not isinstance(row, dict):
                    continue
                items.append(_item(
                    str(row.get("id") or ""),
                    str(row.get("name") or "resource"),
                    _clip(row.get("type"), 200),
                ))
                if len(items) >= 10:
                    break
            result = {"status": "ok", "items": items}
            if not items:
                result["detail"] = "No Azure resources were returned for this subscription."
            return result
        raise AuthenticationError(f"Azure {operation} is not enabled. No request was sent.")

    def _graph(self, path: str, query: dict[str, str], scope: str) -> dict[str, Any]:
        if self.oauth is None or self.oauth.bundle is None:
            raise AuthenticationError("Microsoft 365 is not connected. No request was sent.")
        before = self.oauth.graph_calls
        try:
            return self.oauth.graph_get(path, query, required_scope=scope)
        finally:
            self.network_calls += self.oauth.graph_calls - before

    def _arm(self, path: str, query: dict[str, str]) -> dict[str, Any]:
        if self.oauth is None or self.oauth.bundle is None:
            raise AuthenticationError("Azure is NOT CONFIGURED. No request was sent.")
        before = self.oauth.graph_calls
        try:
            return self.oauth.arm_get(path, query)
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
        if connector_id in {MICROSOFT_365.connector_id, AZURE.connector_id}:
            return client.perform(connector_id, operation, params)
        if connector_id == ENDPOINT.connector_id:
            return endpoint.perform(connector_id, operation, params)
        raise AuthenticationError(f"{connector_id} has no client. No request was sent.")

    catalog = Catalog([MICROSOFT_365, AZURE, ENDPOINT], perform)
    catalog.endpoint_service = endpoint  # type: ignore[attr-defined]
    catalog.devices = registry  # type: ignore[attr-defined]
    if oauth is not None:
        client.apply(catalog, "local-console")
    return catalog, client
