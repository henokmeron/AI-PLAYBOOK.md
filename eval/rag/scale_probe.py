#!/usr/bin/env python3
"""Measure in-process BM25 index build/search latency and memory at larger sizes.

Synthetic chunks only (no documents are parsed), so this isolates the index
cost that a vector/lexical store migration would replace.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "rag"))
from rag_engine import Bm25Index, Chunk, index_terms  # noqa: E402

VOCAB = [f"term{i}" for i in range(20000)]
QUERIES = ["term12 term873 term4410 policy", "term5 term99 term19999", "rate band term300 term301 term302"]


def make_chunks(count: int, seed: int = 7) -> list[Chunk]:
    rng = random.Random(seed)
    chunks = []
    for i in range(count):
        words = [rng.choice(VOCAB[:2000]) if rng.random() < 0.7 else rng.choice(VOCAB) for _ in range(180)]
        text = " ".join(words + ["policy", "rate", "band"])
        terms = index_terms(text)
        chunks.append(Chunk(f"doc{i // 10}.txt", i % 10 + 1, text, terms, Counter(terms)))
    return chunks


def main() -> int:
    results = []
    for count in (1_000, 10_000, 50_000):
        tracemalloc.start()
        chunks = make_chunks(count)
        t0 = time.perf_counter()
        index = Bm25Index(chunks)
        build_ms = (time.perf_counter() - t0) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        timings = []
        for _ in range(3):
            for query in QUERIES:
                t0 = time.perf_counter()
                index.search(query, 8)
                timings.append((time.perf_counter() - t0) * 1000)
        results.append({
            "chunks": count,
            "build_ms": round(build_ms, 1),
            "search_ms_p50": round(statistics.median(timings), 1),
            "search_ms_max": round(max(timings), 1),
            "peak_python_mem_mb": round(peak / 1e6, 1),
        })
        print(json.dumps(results[-1]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
