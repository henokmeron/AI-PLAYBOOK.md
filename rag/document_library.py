"""Safe persistent document-library operations for the local RAG prototype.

Files are stored under a caller-supplied managed root, grouped by validated
collection names. Uploads are base64-encoded JSON and capped at 10 MiB decoded.
This module does not execute uploaded content.
"""
from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path
from typing import Any

ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".html", ".htm", ".docx", ".pdf", ".xlsx"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_FILENAME_CHARS = 120
COLLECTION_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}\Z")


class DocumentLibraryError(ValueError):
    """A request is invalid or a document operation cannot be completed."""


def validate_collection_name(collection: Any) -> str:
    if not isinstance(collection, str) or not COLLECTION_RE.fullmatch(collection):
        raise DocumentLibraryError(
            "collection must use 1–40 lowercase letters, digits, hyphens or underscores and begin with a letter or digit"
        )
    return collection


def validate_filename(filename: Any) -> str:
    if not isinstance(filename, str) or not filename or len(filename) > MAX_FILENAME_CHARS:
        raise DocumentLibraryError(f"filename must be 1–{MAX_FILENAME_CHARS} characters")
    if filename in {".", ".."} or filename.startswith("."):
        raise DocumentLibraryError("hidden or relative filenames are not allowed")
    if "/" in filename or "\\" in filename or Path(filename).name != filename:
        raise DocumentLibraryError("filename must be a plain filename without path separators")
    if any(ord(character) < 32 or ord(character) == 127 for character in filename):
        raise DocumentLibraryError("filename contains a control character")
    suffix = Path(filename).suffix.casefold()
    if suffix not in ALLOWED_EXTENSIONS:
        raise DocumentLibraryError(
            "unsupported extension; accepted types are txt, md, csv, html, htm, docx, pdf and xlsx"
        )
    return filename


def _collection_dir(root: Path, collection: str) -> Path:
    validated = validate_collection_name(collection)
    resolved_root = root.resolve()
    target = (resolved_root / validated).resolve()
    if target == resolved_root or resolved_root not in target.parents:
        raise DocumentLibraryError("invalid collection path")
    return target


def decode_content(content_base64: Any) -> bytes:
    if not isinstance(content_base64, str) or not content_base64:
        raise DocumentLibraryError("content_base64 must be a non-empty base64 string")
    # Reject overlong content before allocating the decoded buffer.
    if len(content_base64) > ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 8:
        raise DocumentLibraryError(f"uploaded file exceeds {MAX_UPLOAD_BYTES} bytes")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DocumentLibraryError("content_base64 is not valid base64") from exc
    if not content:
        raise DocumentLibraryError("uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise DocumentLibraryError(f"uploaded file exceeds {MAX_UPLOAD_BYTES} bytes")
    return content


def store_document(
    root: Path,
    collection: Any,
    filename: Any,
    content_base64: Any,
    overwrite: Any = False,
) -> dict[str, Any]:
    collection_name = validate_collection_name(collection)
    safe_filename = validate_filename(filename)
    if not isinstance(overwrite, bool):
        raise DocumentLibraryError("overwrite must be true or false")
    content = decode_content(content_base64)
    folder = _collection_dir(root, collection_name)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / safe_filename
        if target.is_symlink():
            raise DocumentLibraryError("symbolic-link targets are not allowed")
        if target.exists() and not overwrite:
            raise FileExistsError(f"{safe_filename} already exists in collection {collection_name}")
        # Direct write works on the mounted Global Volume; atomic rename is not
        # assumed because the mount is FUSE-backed. Write only the target file.
        with target.open("wb" if overwrite else "xb") as stream:
            stream.write(content)
    except DocumentLibraryError:
        raise
    except FileExistsError:
        raise
    except OSError as exc:
        raise DocumentLibraryError(f"could not store document: {exc}") from exc
    return {
        "collection": collection_name,
        "filename": safe_filename,
        "size_bytes": len(content),
        "extension": Path(safe_filename).suffix.casefold(),
    }


def list_documents(root: Path, collection: Any) -> list[dict[str, Any]]:
    collection_name = validate_collection_name(collection)
    folder = _collection_dir(root, collection_name)
    if not folder.exists():
        return []
    if folder.is_symlink() or not folder.is_dir():
        raise DocumentLibraryError("collection path is not a regular directory")
    documents: list[dict[str, Any]] = []
    try:
        for entry in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
            if entry.is_symlink() or not entry.is_file():
                continue
            try:
                filename = validate_filename(entry.name)
                stat = entry.stat()
            except DocumentLibraryError:
                continue
            documents.append({
                "filename": filename,
                "size_bytes": stat.st_size,
                "extension": entry.suffix.casefold(),
            })
    except OSError as exc:
        raise DocumentLibraryError(f"could not list collection: {exc}") from exc
    return documents


def delete_document(root: Path, collection: Any, filename: Any) -> dict[str, Any]:
    collection_name = validate_collection_name(collection)
    safe_filename = validate_filename(filename)
    folder = _collection_dir(root, collection_name)
    target = folder / safe_filename
    if target.is_symlink():
        raise DocumentLibraryError("symbolic-link targets are not allowed")
    if not target.is_file():
        raise FileNotFoundError(f"{safe_filename} was not found in collection {collection_name}")
    try:
        target.unlink()
    except OSError as exc:
        raise DocumentLibraryError(f"could not delete document: {exc}") from exc
    return {"collection": collection_name, "filename": safe_filename, "deleted": True}


def get_collection_dir(root: Path, collection: Any) -> Path:
    """Return a validated collection path for use by RAG retrieval."""
    return _collection_dir(root, validate_collection_name(collection))
