"""Safe persistent document-library operations for the local RAG prototype.

Files are stored under a caller-supplied managed root, grouped by validated
collection names. Uploads are base64-encoded JSON and capped at 10 MiB decoded.
This module does not execute uploaded content.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
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


class DocumentAccessError(DocumentLibraryError):
    """The caller is not allowed to read or replace this document."""


_META_DIR = ".library-meta"
_UNSPECIFIED_OWNER = "unspecified"
_ACTOR_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}\Z")
_DOWNLOAD_DENIED = "actor is not allowed to download this document"


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
    if "/" in filename or "\\" in filename or ":" in filename or Path(filename).name != filename:
        raise DocumentLibraryError("filename must be a plain filename without path separators")
    if filename.endswith((" ", ".")):
        raise DocumentLibraryError("filename must not end with a space or a dot")
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
    raw = resolved_root / validated
    if raw.is_symlink():
        raise DocumentLibraryError("collection path must not be a symbolic link")
    target = raw.resolve()
    if target == resolved_root or resolved_root not in target.parents or target.is_symlink():
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


def _validate_actor(actor: Any, *, required: bool) -> str | None:
    if actor is None and not required:
        return None
    if not isinstance(actor, str) or not _ACTOR_RE.fullmatch(actor) or actor == _UNSPECIFIED_OWNER:
        raise DocumentAccessError(_DOWNLOAD_DENIED)
    return actor


def _validate_owner(owner: Any) -> str:
    if owner is None:
        return _UNSPECIFIED_OWNER
    if not isinstance(owner, str) or not _ACTOR_RE.fullmatch(owner) or owner == _UNSPECIFIED_OWNER:
        raise DocumentLibraryError("owner must be a plain operator name")
    return owner


def _meta_dir(root: Path, collection: str) -> Path:
    collection_name = validate_collection_name(collection)
    resolved_root = root.resolve()
    base = resolved_root / _META_DIR
    if base.is_symlink():
        raise DocumentLibraryError("metadata path must not be a symbolic link")
    raw = base / collection_name
    if raw.is_symlink():
        raise DocumentLibraryError("metadata path must not be a symbolic link")
    target = raw.resolve()
    if target == resolved_root or resolved_root not in target.parents or target.is_symlink():
        raise DocumentLibraryError("invalid metadata path")
    return target


def _meta_path(root: Path, collection: str, filename: str) -> Path:
    folder = _meta_dir(root, collection)
    path = folder / f"{filename}.json"
    if path.is_symlink() or path.name != f"{filename}.json":
        raise DocumentLibraryError("invalid metadata path")
    resolved = path.resolve() if path.exists() else path
    if folder.resolve() not in resolved.parents and resolved.parent != folder.resolve():
        raise DocumentLibraryError("invalid metadata path")
    return path


def _read_meta(root: Path, collection: str, filename: str) -> dict[str, Any] | None:
    path = _meta_path(root, collection, filename)
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_meta(root: Path, collection: str, filename: str, payload: dict[str, Any]) -> None:
    path = _meta_path(root, collection, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _version_path(root: Path, collection: str, filename: str, version: int) -> Path:
    if isinstance(version, bool) or not isinstance(version, int) or version < 1 or version > 10000:
        raise DocumentLibraryError("version is not available")
    folder = _meta_dir(root, collection) / "versions" / filename
    if folder.is_symlink():
        raise DocumentLibraryError("symbolic-link targets are not allowed")
    path = folder / f"v{version}.bin"
    resolved_folder = folder.resolve()
    resolved = path.resolve() if path.exists() else path
    meta_root = _meta_dir(root, collection).resolve()
    if meta_root not in resolved.parents and resolved.parent != resolved_folder:
        raise DocumentLibraryError("invalid version path")
    if path.is_symlink():
        raise DocumentLibraryError("symbolic-link targets are not allowed")
    return path


def _authorise(meta: dict[str, Any], actor: Any) -> str:
    checked = _validate_actor(actor, required=True)
    assert checked is not None
    owner = meta.get("owner") if isinstance(meta.get("owner"), str) else _UNSPECIFIED_OWNER
    readers = meta.get("readers") if isinstance(meta.get("readers"), list) else []
    allowed = {owner} | {item for item in readers if isinstance(item, str)}
    if owner == _UNSPECIFIED_OWNER or checked not in allowed:
        raise DocumentAccessError(_DOWNLOAD_DENIED)
    return checked


def _public_record(
    collection: str,
    filename: str,
    meta: dict[str, Any] | None,
    *,
    size_bytes: int,
) -> dict[str, Any]:
    owner = _UNSPECIFIED_OWNER
    version = None
    status = "unknown"
    retained = 0
    if isinstance(meta, dict):
        if isinstance(meta.get("owner"), str):
            owner = meta["owner"]
        if isinstance(meta.get("version"), int) and not isinstance(meta.get("version"), bool):
            version = meta["version"]
        if isinstance(meta.get("status"), str):
            status = meta["status"]
        retained_rows = meta.get("retained")
        if isinstance(retained_rows, list):
            retained = len(retained_rows)
    return {
        "collection": collection,
        "filename": filename,
        "size_bytes": size_bytes,
        "extension": Path(filename).suffix.casefold(),
        "owner": owner,
        "version": version if version is not None else 0,
        "status": status,
        "retained_versions": retained,
    }


def store_document(
    root: Path,
    collection: Any,
    filename: Any,
    content_base64: Any,
    overwrite: Any = False,
    *,
    owner: Any = None,
    actor: Any = None,
) -> dict[str, Any]:
    collection_name = validate_collection_name(collection)
    safe_filename = validate_filename(filename)
    if not isinstance(overwrite, bool):
        raise DocumentLibraryError("overwrite must be true or false")
    content = decode_content(content_base64)
    recorded_owner = _validate_owner(owner)

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
    archived: Path | None = None
    previous: bytes | None = None
    existing: dict[str, Any] | None = None
    target = folder / safe_filename
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise DocumentLibraryError("symbolic-link targets are not allowed")
        existing = _read_meta(root, collection_name, safe_filename)
        if target.exists() and not overwrite:
            raise FileExistsError(f"{safe_filename} already exists in collection {collection_name}")
        if target.is_file() and overwrite:
            previous = target.read_bytes()
            if previous == content:
                raise DocumentLibraryError(
                    "uploaded file duplicates the stored version; the previous version was kept"
                )
            owner_now = existing.get("owner") if isinstance(existing, dict) else _UNSPECIFIED_OWNER
            if owner_now != _UNSPECIFIED_OWNER:
                _authorise(existing or {"owner": owner_now}, actor)
                recorded_owner = owner_now
            prior_version = 1
            if isinstance(existing, dict) and isinstance(existing.get("version"), int):
                prior_version = existing["version"]
            archived = _version_path(root, collection_name, safe_filename, prior_version)
            archived.parent.mkdir(parents=True, exist_ok=True)
            partial = archived.with_suffix(".partial")
            partial.write_bytes(previous)
            os.replace(partial, archived)
        # Direct write works on the mounted Global Volume; atomic rename is not
        # assumed because the mount is FUSE-backed. Write only the target file.
        with target.open("wb" if overwrite else "xb") as stream:
            stream.write(content)
    except DocumentLibraryError:
        raise
    except FileExistsError:
        raise
    except OSError as exc:
        if previous is not None and archived is not None:
            try:
                target.write_bytes(previous)
                archived.unlink(missing_ok=True)
            except OSError:
                pass
        raise DocumentLibraryError(f"could not store document: {exc}") from exc

    retained: list[dict[str, Any]] = []
    version = 1
    if previous is not None and isinstance(existing, dict):
        retained = [item for item in existing.get("retained") or [] if isinstance(item, dict)]
        prior_version = existing.get("version") if isinstance(existing.get("version"), int) else 1
        retained.append({
            "version": prior_version,
            "sha256": hashlib.sha256(previous).hexdigest(),
            "size_bytes": len(previous),
            "status": "retained",
        })
        version = prior_version + 1
    meta = {
        "owner": recorded_owner,
        "version": version,
        "status": "active",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "readers": [],
        "retained": retained,
    }
    _write_meta(root, collection_name, safe_filename, meta)
    record = _public_record(collection_name, safe_filename, meta, size_bytes=len(content))
    return record


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
            meta = _read_meta(root, collection_name, filename)
            documents.append(_public_record(collection_name, filename, meta, size_bytes=stat.st_size))
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
    meta = _read_meta(root, collection_name, safe_filename)
    try:
        target.unlink()
    except OSError as exc:
        raise DocumentLibraryError(f"could not delete document: {exc}") from exc
    if isinstance(meta, dict):
        meta["status"] = "deleted"
        try:
            _write_meta(root, collection_name, safe_filename, meta)
        except OSError as exc:
            raise DocumentLibraryError(f"could not keep the previous version: {exc}") from exc
    return {"collection": collection_name, "filename": safe_filename, "deleted": True}


def _load_version_bytes(root: Path, collection: str, filename: str, version: int) -> bytes:
    path = _version_path(root, collection, filename, version)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"version {version} was not found for {filename}")
    return path.read_bytes()


def read_authorised_document(
    root: Path,
    collection: Any,
    filename: Any,
    actor: Any,
    version: Any = None,
) -> dict[str, Any]:
    """Return one stored file to an allowed actor. There is no public URL."""
    collection_name = validate_collection_name(collection)
    safe_filename = validate_filename(filename)
    meta = _read_meta(root, collection_name, safe_filename) or {"owner": _UNSPECIFIED_OWNER}
    _authorise(meta, actor)
    current = _collection_dir(root, collection_name) / safe_filename
    if version is None:
        if not current.is_file() or current.is_symlink():
            raise FileNotFoundError(f"{safe_filename} was not found in collection {collection_name}")
        content = current.read_bytes()
        chosen = meta.get("version") if isinstance(meta.get("version"), int) else 0
        status = meta.get("status") if isinstance(meta.get("status"), str) else "active"
    else:
        if isinstance(version, bool) or not isinstance(version, int):
            raise DocumentLibraryError("version must be an integer")
        current_version = meta.get("version") if isinstance(meta.get("version"), int) else None
        if version == current_version and current.is_file() and not current.is_symlink():
            content = current.read_bytes()
            chosen = version
            status = "active"
        else:
            content = _load_version_bytes(root, collection_name, safe_filename, version)
            chosen = version
            status = "retained"
    record = _public_record(collection_name, safe_filename, meta, size_bytes=len(content))
    record["version"] = chosen
    record["status"] = status
    record["content_base64"] = base64.b64encode(content).decode("ascii")
    return record


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
        lowered = content.casefold()
        stale = [
            name for name in _filenames_mentioned(content)
            if name.casefold() not in active
        ]
        # A user turn can quote a deleted rate just as an assistant turn can.
        if stale or _mentions_missing_source_label(lowered, active):
            content = (
                "[Prior turn omitted because it cited document(s) that are "
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
