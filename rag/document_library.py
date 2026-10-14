"""Safe persistent document-library operations for the local RAG prototype.

Files are stored under a caller-supplied managed root, grouped by validated
collection names. Uploads are base64-encoded JSON and capped at 10 MiB decoded.
This module does not execute uploaded content.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from pathlib import Path
import tempfile
from typing import Any

from document_loaders import DocumentLoadError, read_document

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

    # Validate the uploaded bytes with the same parser used during RAG retrieval
    # before storing them, so one corrupt file does not break an entire collection.
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="rag-upload-validation-",
            suffix=Path(safe_filename).suffix.casefold(),
            delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)
        extracted = read_document(temp_path)
        if not extracted.strip():
            raise DocumentLibraryError("uploaded document contains no extractable text")
    except DocumentLibraryError:
        raise
    except DocumentLoadError as exc:
        raise DocumentLibraryError(f"uploaded document could not be parsed: {exc}") from exc
    except OSError as exc:
        raise DocumentLibraryError(f"could not validate uploaded document: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def find_duplicate_content(root: Path, collection: Any, filename: Any) -> list[str]:
    """Return other files in the collection whose bytes are identical to ``filename``."""
    collection_name = validate_collection_name(collection)
    safe_filename = validate_filename(filename)
    folder = _collection_dir(root, collection_name)
    target = folder / safe_filename
    if not target.is_file():
        return []
    try:
        size = target.stat().st_size
        target_hash: str | None = None
        duplicates = []
        for entry in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
            if entry.name == safe_filename or entry.is_symlink() or not entry.is_file():
                continue
            if entry.stat().st_size != size:
                continue
            target_hash = target_hash or _sha256_file(target)
            if _sha256_file(entry) == target_hash:
                duplicates.append(entry.name)
    except OSError:
        return []
    return duplicates


def get_collection_dir(root: Path, collection: Any) -> Path:
    """Return a validated collection path for use by RAG retrieval."""
    return _collection_dir(root, validate_collection_name(collection))


def _chunk_counts(folder: Path) -> dict[str, int]:
    """Chunk count per loadable file; unreadable files are skipped individually."""
    from rag_engine import load_document_chunks, supported_paths

    counts: dict[str, int] = {}
    for path in supported_paths(folder):
        relative = path.relative_to(folder).as_posix()
        try:
            chunks = load_document_chunks(path, relative)
        except (DocumentLoadError, OSError):
            continue
        if chunks:
            counts[relative] = len(chunks)
    return counts


def indexed_source_names(root: Path, collection: Any) -> list[str]:
    """Return filenames currently loadable as RAG chunks for a collection."""
    folder = get_collection_dir(root, collection)
    if not folder.is_dir():
        return []
    return sorted(_chunk_counts(folder))


def verify_document_searchable(root: Path, collection: Any, filename: Any) -> dict[str, Any]:
    """Confirm a stored file is present on disk and appears in retrieval chunks."""
    collection_name = validate_collection_name(collection)
    safe_filename = validate_filename(filename)
    folder = get_collection_dir(root, collection_name)
    target = folder / safe_filename
    if not target.is_file():
        raise DocumentLibraryError(f"{safe_filename} is not stored in collection {collection_name}")
    counts = _chunk_counts(folder)
    sources = sorted(counts)
    if safe_filename not in counts:
        raise DocumentLibraryError(
            f"{safe_filename} was stored but is not yet searchable in collection {collection_name}"
        )
    chunk_count = counts[safe_filename]
    return {
        "collection": collection_name,
        "filename": safe_filename,
        "searchable": True,
        "chunk_count": chunk_count,
        "indexed_sources": sources,
    }


def verify_document_removed(root: Path, collection: Any, filename: Any) -> dict[str, Any]:
    """Confirm a deleted file is absent from disk and from retrieval chunks."""
    collection_name = validate_collection_name(collection)
    safe_filename = validate_filename(filename)
    folder = get_collection_dir(root, collection_name)
    target = folder / safe_filename
    if target.exists():
        raise DocumentLibraryError(f"{safe_filename} still exists on disk in collection {collection_name}")
    sources = indexed_source_names(root, collection_name)
    if safe_filename in sources:
        raise DocumentLibraryError(
            f"{safe_filename} was deleted from disk but still appears in searchable chunks"
        )
    return {
        "collection": collection_name,
        "filename": safe_filename,
        "deleted": True,
        "removed_from_index": True,
        "indexed_sources": sources,
    }


def sanitize_history_for_collection(
    history: list[dict[str, str]],
    current_filenames: list[str],
) -> list[dict[str, str]]:
    """Neutralize prior turns that cite documents no longer in the collection."""
    if not history:
        return []
    active = {name.casefold() for name in current_filenames}
    cleaned: list[dict[str, str]] = []
    for item in history:
        role = item["role"]
        content = item["content"]
        if role == "assistant":
            lowered = content.casefold()
            stale = [
                name for name in _filenames_mentioned(content)
                if name.casefold() not in active
            ]
            # Also catch common citation shapes that embed the old basename.
            if stale or _mentions_missing_source_label(lowered, active):
                content = (
                    "[Prior assistant answer omitted because it cited document(s) that are "
                    "no longer in the active collection. Do not reuse rates, tables or "
                    "citations from omitted turns.]"
                )
        cleaned.append({"role": role, "content": content})
    return cleaned


def _filenames_mentioned(text: str) -> list[str]:
    found: list[str] = []
    for match in re.finditer(
        r"([A-Za-z0-9][^\\/:*?\"<>|\r\n]{0,180}\.(?:xlsx|pdf|docx|csv|md|txt|html|htm))",
        text,
        flags=re.IGNORECASE,
    ):
        name = Path(match.group(1)).name.strip()
        if name and name not in found:
            found.append(name)
    return found


def _mentions_missing_source_label(lowered_text: str, active_filenames: set[str]) -> bool:
    for name in re.findall(r"file=([^;\]]+)", lowered_text):
        candidate = Path(name.strip()).name.casefold()
        if candidate and candidate not in active_filenames:
            return True
    return False
