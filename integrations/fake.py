"""In-memory fake document-store connector for tests. Not a real integration.

Resource ids are global (as with real SaaS APIs) and each resource records its
owning tenant, so cross-tenant access attempts are detectable.
"""
from __future__ import annotations

import itertools
from typing import Any, Callable

from .connector import Connector, Operation
from .errors import AuthenticationError, IntegrationError, InvalidRequest, NotFound
from .resilience import Page
from .tenancy import Access, Scope, TenantContext

PAGE_SIZE_MAX = 50


class FakeDocumentConnector(Connector):
    name = "fake_docs"
    operations = {
        "list_documents": Operation("list_documents", Access.READ, Scope("documents", Access.READ), idempotent=True),
        "get_document": Operation("get_document", Access.READ, Scope("documents", Access.READ), idempotent=True),
        "create_document": Operation("create_document", Access.WRITE, Scope("documents", Access.WRITE),
                                     idempotent=False, requires_approval=True),
        "delete_document": Operation("delete_document", Access.WRITE, Scope("documents", Access.WRITE),
                                     idempotent=False, requires_approval=True),
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._docs: dict[str, dict[str, Any]] = {}
        self._ids = itertools.count(1)
        self._idempotency: dict[str, str] = {}
        self._faults: list[Callable[[], IntegrationError]] = []
        self.calls = 0

    # --- test helpers -----------------------------------------------------
    def seed(self, tenant_id: str, title: str, body: str) -> str:
        doc_id = f"doc-{next(self._ids)}"
        self._docs[doc_id] = {"id": doc_id, "tenant_id": tenant_id, "title": title, "body": body}
        return doc_id

    def inject_faults(self, *factories: Callable[[], IntegrationError]) -> None:
        self._faults.extend(factories)

    # --- connector implementation ----------------------------------------
    def authenticate(self, ctx: TenantContext) -> None:
        secret = self._secrets.get("FAKE_DOCS_TOKEN")
        if len(secret.reveal()) < 16:
            raise AuthenticationError("fake credential too short")

    def _perform(self, ctx: TenantContext, op: Operation, params: dict[str, Any]) -> Any:
        self.calls += 1
        if self._faults:
            raise self._faults.pop(0)()
        handler = getattr(self, "_op_" + op.name)
        return handler(ctx, params)

    def _owned(self, ctx: TenantContext, doc_id: Any) -> dict[str, Any]:
        doc = self._docs.get(doc_id) if isinstance(doc_id, str) else None
        if doc is None:
            raise NotFound("document not found")
        ctx.require_tenant(doc["tenant_id"])
        return doc

    def _op_list_documents(self, ctx: TenantContext, params: dict[str, Any]) -> Page:
        size = params.get("page_size", 10)
        if not isinstance(size, int) or not 1 <= size <= PAGE_SIZE_MAX:
            raise InvalidRequest("page_size must be 1-50")
        owned = sorted((d for d in self._docs.values() if d["tenant_id"] == ctx.tenant_id),
                       key=lambda d: int(d["id"].split("-")[1]))
        start = int(params.get("cursor") or 0)
        items = [{"id": d["id"], "title": d["title"]} for d in owned[start:start + size]]
        nxt = str(start + size) if start + size < len(owned) else None
        return Page(items, nxt)

    def _op_get_document(self, ctx: TenantContext, params: dict[str, Any]) -> dict[str, Any]:
        doc = self._owned(ctx, params.get("id"))
        return {"id": doc["id"], "title": doc["title"], "body": doc["body"]}

    def _op_create_document(self, ctx: TenantContext, params: dict[str, Any]) -> dict[str, Any]:
        key = params.get("_idempotency_key")
        if key and key in self._idempotency:
            return {"id": self._idempotency[key], "deduplicated": True}
        title, body = params.get("title"), params.get("body")
        if not isinstance(title, str) or not title.strip() or not isinstance(body, str):
            raise InvalidRequest("title and body are required")
        doc_id = self.seed(ctx.tenant_id, title.strip(), body)
        if key:
            self._idempotency[key] = doc_id
        return {"id": doc_id, "deduplicated": False}

    def _op_delete_document(self, ctx: TenantContext, params: dict[str, Any]) -> dict[str, Any]:
        doc = self._owned(ctx, params.get("id"))
        del self._docs[doc["id"]]
        return {"id": doc["id"], "deleted": True}
