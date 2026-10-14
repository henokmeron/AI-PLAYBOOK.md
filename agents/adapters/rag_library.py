"""Adapters that call the existing RAG library or gateway API without modifying them.

``rag/`` modules use flat imports (``from document_loaders import ...``), so the
folder is appended to ``sys.path`` on first use. Nothing in ``rag/`` is edited.
"""
from __future__ import annotations

import importlib
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Protocol

from ..model import validate_endpoint
from ..tools import ToolInputError, ToolPermissionError, ToolTransientError

DEFAULT_RAG_DIR = Path(__file__).resolve().parents[2] / "rag"
MAX_RESPONSE_BYTES = 2_000_000
_lock = threading.Lock()
_modules: dict[str, Any] | None = None


def load_rag_modules(rag_dir: Path = DEFAULT_RAG_DIR) -> dict[str, Any]:
    global _modules
    with _lock:
        if _modules is None:
            path = str(Path(rag_dir).resolve())
            if path not in sys.path:
                sys.path.append(path)
            _modules = {
                name: importlib.import_module(name)
                for name in ("document_loaders", "rag_engine", "document_library")
            }
        return _modules


class SearchBackend(Protocol):
    def search(self, query: str, collection: str, top_k: int) -> list[dict[str, Any]]: ...


class RagLibrarySearchBackend:
    """BM25 retrieval over a managed collection using ``rag/`` functions directly.

    ``allowed_collections`` is the tenant boundary: the agent can only search the
    collections the caller was granted, even if others exist on disk.
    """

    def __init__(self, managed_root: Path, allowed_collections: list[str], rag_dir: Path = DEFAULT_RAG_DIR) -> None:
        if not allowed_collections:
            raise ValueError("at least one allowed collection is required")
        self.managed_root = Path(managed_root)
        self.allowed = frozenset(allowed_collections)
        self._rag_dir = rag_dir

    def search(self, query: str, collection: str, top_k: int) -> list[dict[str, Any]]:
        if collection not in self.allowed:
            raise ToolPermissionError(f"collection {collection!r} is not granted to this task")
        mods = load_rag_modules(self._rag_dir)
        library, engine = mods["document_library"], mods["rag_engine"]
        try:
            folder = library.get_collection_dir(self.managed_root, collection)
            listed = {item["filename"] for item in library.list_documents(self.managed_root, collection)}
        except library.DocumentLibraryError as exc:
            raise ToolInputError(str(exc)) from None
        if not listed or not folder.is_dir():
            return []
        try:
            chunks = [c for c in engine.load_chunks(folder) if c.source in listed]
        except RuntimeError:
            return []
        ranked = engine.retrieve(query, chunks, top_k=top_k)
        hits = []
        for score, chunk, files in engine.dedupe_ranked_chunks(ranked):
            hits.append({"file": files[0], "also_in": files[1:], "chunk": chunk.number,
                         "score": round(float(score), 3), "text": chunk.text})
        return hits


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


class GatewayDocumentQABackend:
    """Calls ``POST /v1/rag/ask`` on the loopback platform gateway.

    The gateway has no retrieval-only endpoint, so this returns the gateway's
    grounded answer plus its source list (both treated as untrusted).
    """

    def __init__(
        self,
        gateway_url: str,
        api_key_provider: Callable[[], str],
        allowed_collections: list[str],
        timeout: float = 180.0,
        opener: Any = None,
    ) -> None:
        self.base = validate_endpoint(gateway_url)
        self._key = api_key_provider
        self.allowed = frozenset(allowed_collections)
        self.timeout = timeout
        self._opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _RejectRedirects())

    def __repr__(self) -> str:
        return f"GatewayDocumentQABackend(base={self.base!r})"

    def ask(self, question: str, collection: str, top_k: int) -> dict[str, Any]:
        if collection not in self.allowed:
            raise ToolPermissionError(f"collection {collection!r} is not granted to this task")
        key = self._key()
        if not key:
            raise ToolPermissionError("gateway key is not configured")
        request = urllib.request.Request(
            f"{self.base}/v1/rag/ask",
            data=json.dumps({"question": question, "collection": collection, "top_k": top_k}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 502, 503, 504}:
                raise ToolTransientError(f"gateway returned HTTP {exc.code}") from None
            raise ToolInputError(f"gateway returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ToolTransientError("gateway unreachable") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ToolInputError("gateway response too large")
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ToolInputError("gateway response was not JSON") from None
        if not isinstance(body, dict):
            raise ToolInputError("gateway response was not an object")
        sources = body.get("sources") if isinstance(body.get("sources"), list) else []
        return {
            "status": str(body.get("status", "unknown")),
            "answer": str(body.get("answer", ""))[:6000],
            "sources": [
                {"label": str(s.get("label", "")), "file": str(s.get("file", "")),
                 "chunk": int(s.get("chunk", 0)) if isinstance(s.get("chunk"), int) else 0}
                for s in sources[:20] if isinstance(s, dict)
            ],
            "untrusted": True,
        }
