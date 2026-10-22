"""Pure-Python BM25 retrieval engine shared by CLI and HTTP API."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from document_loaders import (
    DocumentLoadError,
    SUPPORTED_EXTENSIONS,
    Segment,
    read_document_segments,
)

TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
INDEX_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
ROW_NUMBER_RE = re.compile(r"(?:^|\| )Row (\d+):")
MAX_HEADER_CHARS = 150
# Function words that carry no evidence; used only for query coverage scoring.
STOPWORDS = frozenset(
    "a an and any are as at be by can do does did for from has have how i if in is it its "
    "me my of on or our per should that the their there this to was we what when where "
    "which who whom why will with would you your give list tell show "
    # Request-framing words ("list every ... in the complete table") are not evidence.
    "every all each complete full entire table summary summarise summarize detail please".split()
)


@dataclass
class Chunk:
    source: str
    number: int
    text: str
    tokens: list[str]
    term_counts: Counter[str]
    # Location metadata for citations: page, sheet, row_start, row_end, kind.
    meta: dict[str, object] = field(default_factory=dict)
    # Short document/table context (title or CSV header) indexed with the chunk.
    header: str = ""


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def stem(token: str) -> str:
    """Conservative S-stemmer: folds plurals only (passwords -> password)."""
    if len(token) <= 3 or token.isdigit():
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def index_terms(text: str) -> list[str]:
    """Terms used for ranking: underscore-split, case-folded, plural-folded."""
    return [stem(token.casefold()) for token in INDEX_TOKEN_RE.findall(text)]


def _char_split(text: str, max_chars: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + max_chars // 2, end)
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _pack_units(units: list[str], max_chars: int, overlap: int, joiner: str) -> list[str]:
    """Greedily pack whole units (rows/paragraphs/lines) into chunks with unit overlap."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for unit in units:
        if len(unit) > max_chars:
            if current:
                chunks.append(joiner.join(current))
                current, current_len = [], 0
            chunks.extend(_char_split(unit, max_chars, overlap))
            continue
        add = len(unit) + (len(joiner) if current else 0)
        if current and current_len + add > max_chars:
            chunks.append(joiner.join(current))
            carried: list[str] = []
            carried_len = 0
            for prior in reversed(current):
                extra = len(prior) + (len(joiner) if carried else 0)
                if carried_len + extra > overlap:
                    break
                carried.insert(0, prior)
                carried_len += extra
            # Keep room for the unit that triggered the flush.
            while carried and carried_len + len(joiner) + len(unit) > max_chars:
                carried_len -= len(carried.pop(0)) + len(joiner)
            current = carried
            current_len = max(carried_len, 0)
            add = len(unit) + (len(joiner) if current else 0)
        current.append(unit)
        current_len += add
    if current:
        chunks.append(joiner.join(current))
    return chunks


def split_chunks(text: str, max_chars: int = 1200, overlap: int = 160) -> list[str]:
    """Split text into chunks on structural boundaries.

    Spreadsheet/CSV rows and paragraphs are kept whole; a single unit longer
    than ``max_chars`` falls back to a newline-preferring character split.
    """
    text = text.strip()
    if not text:
        return []
    if "| Row " in text:
        return _pack_units(text.splitlines(), max_chars, overlap, "\n")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) > 1:
        return _pack_units(paragraphs, max_chars, overlap, "\n\n")
    return _pack_units([line for line in text.splitlines() if line.strip()], max_chars, overlap, "\n")


def chunk_segments(source: str, segments: list[Segment], max_chars: int = 1200, overlap: int = 160) -> list[Chunk]:
    """Chunk one document's segments, attaching location metadata to each chunk."""
    chunks: list[Chunk] = []
    # Users refer to documents by name ("the rate register"), so filename words
    # are indexed with every chunk of that file.
    name_terms = index_terms(Path(source).stem)
    for segment in segments:
        context = str(segment.meta.get("table_header") or "")[:MAX_HEADER_CHARS]
        for part in split_chunks(segment.text, max_chars=max_chars, overlap=overlap):
            meta: dict[str, object] = {"kind": segment.meta.get("kind", "text")}
            for key in ("page", "sheet"):
                if segment.meta.get(key) not in (None, ""):
                    meta[key] = segment.meta[key]
            rows = [int(n) for n in ROW_NUMBER_RE.findall(part)]
            if rows:
                meta["row_start"], meta["row_end"] = min(rows), max(rows)
            header = context if context and context not in part else ""
            body_terms = index_terms(header + "\n" + part if header else part)
            terms = name_terms + body_terms if body_terms else []
            if terms:
                chunks.append(Chunk(source, len(chunks) + 1, part, terms, Counter(terms), meta, header))
    return chunks


def normalize_evidence_text(text: str) -> str:
    """Normalize chunk text for duplicate-workbook comparison."""
    rows = [line.strip() for line in text.splitlines() if "| Row " in line]
    if rows:
        return "\n".join(rows)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def dedupe_ranked_chunks(
    ranked: list[tuple[float, Chunk]],
) -> list[tuple[float, Chunk, list[str]]]:
    """Collapse identical evidence from different files while retaining filenames.

    Returns (score, representative_chunk, all_matching_filenames).
    """
    groups: list[tuple[float, Chunk, list[str]]] = []
    index_by_key: dict[str, int] = {}
    for score, chunk in ranked:
        key = normalize_evidence_text(chunk.text)
        existing = index_by_key.get(key)
        if existing is None:
            index_by_key[key] = len(groups)
            groups.append((score, chunk, [chunk.source]))
            continue
        best_score, best_chunk, files = groups[existing]
        if chunk.source not in files:
            files.append(chunk.source)
        if score > best_score:
            groups[existing] = (score, chunk, files)
    return groups


def load_document_chunks(path: Path, source: str) -> list[Chunk]:
    """Parse and chunk one file. Raises DocumentLoadError/OSError on bad input."""
    return chunk_segments(source, read_document_segments(path))


def supported_paths(folder: Path) -> list[Path]:
    """Files this folder may index.

    Symbolic links are omitted. A link planted in one collection must not
    make another collection's file readable here. The resolved path also has
    to stay inside the folder.
    """
    root = folder.resolve()
    found: list[Path] = []
    for path in folder.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved != root and root not in resolved.parents:
            continue
        found.append(path)
    return sorted(found)


def load_chunks(folder: Path) -> list[Chunk]:
    if not folder.exists() or not folder.is_dir():
        raise RuntimeError(f"Document folder does not exist or is not a directory: {folder}")
    chunks: list[Chunk] = []
    for path in supported_paths(folder):
        relative = path.relative_to(folder).as_posix()
        try:
            chunks.extend(load_document_chunks(path, relative))
        except (DocumentLoadError, OSError) as exc:
            raise RuntimeError(f"Could not read document {path}: {exc}") from exc
    if not chunks:
        raise RuntimeError(f"No readable non-empty supported document chunks found in {folder}")
    return chunks


class Bm25Index:
    """Precomputed BM25 statistics over a fixed chunk list."""

    k1 = 1.5
    b = 0.75

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.doc_freq: Counter[str] = Counter()
        for chunk in chunks:
            self.doc_freq.update(set(chunk.tokens))
        self.total = len(chunks)
        self.average_length = sum(len(c.tokens) for c in chunks) / max(self.total, 1)

    def idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        return math.log(1 + (self.total - df + 0.5) / (df + 0.5))

    def score(self, q_terms: list[str], chunk: Chunk) -> float:
        length_norm = self.k1 * (1 - self.b + self.b * len(chunk.tokens) / max(self.average_length, 1))
        total = 0.0
        for term in q_terms:
            frequency = chunk.term_counts.get(term, 0)
            if frequency:
                total += self.idf(term) * (frequency * (self.k1 + 1)) / (frequency + length_norm)
        return total

    def search(self, question: str, top_k: int) -> list[tuple[float, Chunk]]:
        q_terms = list(dict.fromkeys(index_terms(question)))
        if not q_terms:
            return []
        ranked = [(s, c) for c in self.chunks if (s := self.score(q_terms, c)) > 0]
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[:top_k]

    def coverage(self, question: str, chunk: Chunk) -> float:
        """IDF-weighted share of informative query terms present in the chunk."""
        q_terms = [t for t in dict.fromkeys(index_terms(question)) if t not in STOPWORDS]
        if not q_terms:
            return 0.0
        weights = {t: self.idf(t) for t in q_terms}
        total = sum(weights.values())
        hit = sum(w for t, w in weights.items() if chunk.term_counts.get(t))
        return hit / total if total else 0.0


def retrieve(
    question: str,
    chunks: list[Chunk],
    top_k: int = 4,
    index: Bm25Index | None = None,
) -> list[tuple[float, Chunk]]:
    return (index or Bm25Index(chunks)).search(question, top_k)
