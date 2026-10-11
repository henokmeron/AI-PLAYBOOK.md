"""Pure-Python BM25 retrieval engine shared by CLI and HTTP API."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from document_loaders import DocumentLoadError, SUPPORTED_EXTENSIONS, read_document

TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
@dataclass
class Chunk:
    source: str
    number: int
    text: str
    tokens: list[str]
    term_counts: Counter[str]


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def split_chunks(text: str, max_chars: int = 1200, overlap: int = 160) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
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


def load_chunks(folder: Path) -> list[Chunk]:
    if not folder.exists() or not folder.is_dir():
        raise RuntimeError(f"Document folder does not exist or is not a directory: {folder}")
    paths = sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.casefold() in SUPPORTED_EXTENSIONS
    )
    chunks: list[Chunk] = []
    for path in paths:
        try:
            text = read_document(path)
        except (DocumentLoadError, OSError) as exc:
            raise RuntimeError(f"Could not read document {path}: {exc}") from exc
        relative = path.relative_to(folder).as_posix()
        for index, part in enumerate(split_chunks(text), start=1):
            tokens = tokenize(part)
            if tokens:
                chunks.append(Chunk(relative, index, part, tokens, Counter(tokens)))
    if not chunks:
        raise RuntimeError(f"No readable non-empty supported document chunks found in {folder}")
    return chunks


def retrieve(question: str, chunks: list[Chunk], top_k: int = 4) -> list[tuple[float, Chunk]]:
    q_tokens = list(dict.fromkeys(tokenize(question)))
    if not q_tokens:
        return []
    doc_freq: Counter[str] = Counter()
    for chunk in chunks:
        doc_freq.update(set(chunk.tokens))
    total_docs = len(chunks)
    average_length = sum(len(chunk.tokens) for chunk in chunks) / max(total_docs, 1)
    k1, b = 1.5, 0.75
    ranked: list[tuple[float, Chunk]] = []
    for chunk in chunks:
        length_norm = k1 * (1 - b + b * len(chunk.tokens) / max(average_length, 1))
        score = 0.0
        for term in q_tokens:
            frequency = chunk.term_counts.get(term, 0)
            if not frequency:
                continue
            df = doc_freq.get(term, 0)
            idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
            score += idf * (frequency * (k1 + 1)) / (frequency + length_norm)
        if score > 0:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:top_k]
