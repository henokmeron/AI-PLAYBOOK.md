"""Built-in, read-only or pure-compute tools. No shell or write-capable filesystem tools."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.rag_library import SearchBackend
from ..tools import ToolRegistry
from .calculator import calculator_tool
from .files import AuthorisedRoot, default_extractor, list_documents_tool, read_document_tool
from .search import document_qa_tool, document_search_tool
from .structured import structured_output_tool
from .tables import table_analysis_tool


def default_registry(
    *,
    document_root: Path | None = None,
    search_backend: SearchBackend | None = None,
    output_schemas: dict[str, dict[str, Any]] | None = None,
    use_rag_extractor: bool = True,
) -> ToolRegistry:
    registry = ToolRegistry([calculator_tool()])
    if document_root is not None:
        root = AuthorisedRoot(document_root)
        extractor = default_extractor() if use_rag_extractor else None
        registry.register(list_documents_tool(root))
        registry.register(read_document_tool(root, extractor))
        registry.register(table_analysis_tool(root))
    if search_backend is not None:
        registry.register(document_search_tool(search_backend))
    if output_schemas:
        registry.register(structured_output_tool(output_schemas))
    return registry


__all__ = [
    "AuthorisedRoot", "calculator_tool", "default_registry", "document_qa_tool",
    "document_search_tool", "list_documents_tool", "read_document_tool",
    "structured_output_tool", "table_analysis_tool",
]
