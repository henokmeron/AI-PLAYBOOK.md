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
    """Split document text into overlapping chunks, preferring spreadsheet row bounds."""
    text = text.strip()
    if not text:
        return []
    # Keep each "Sheet: … | Row N:" line intact so age-band/rate associations survive.
    if "| Row " in text:
        lines = text.splitlines()
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in lines:
            line_len = len(line) + (1 if current else 0)
            if current and current_len + line_len > max_chars:
                chunks.append("\n".join(current))
                # Overlap with prior spreadsheet rows when possible.
                overlap_lines: list[str] = []
                overlap_len = 0
                for prior in reversed(current):
                    add = len(prior) + (1 if overlap_lines else 0)
                    if overlap_len + add > overlap and overlap_lines:
                        break
                    overlap_lines.insert(0, prior)
                    overlap_len += add
                current = overlap_lines
                current_len = overlap_len
            if current:
                current.append(line)
                current_len += line_len
            else:
                current = [line]
                current_len = len(line)
        if current:
            chunks.append("\n".join(current))
        return chunks

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
