#!/usr/bin/env python3
"""Deterministic, GPU-free retrieval benchmark for the Document Q&A pipeline.

Relevance is defined by gold evidence *spans* (document + exact text), so the
labels survive chunking changes: a retrieved chunk is relevant when it comes
from a gold document (or lists it as an identical duplicate) and contains the
span after whitespace/case normalisation.

The RAG implementation under test is loaded from ``--rag-dir`` so the same
harness can score the current tree and a historical baseline exported with
``git show <commit>:rag/<file>``. When the directory provides
``retrieval_pipeline.search`` that is used (same code path as the gateway);
otherwise the legacy gateway behaviour (broad-question top-k widening, BM25,
duplicate collapse, managed min score 0.0) is reproduced.

Usage:
    python eval/rag/run_retrieval.py --rag-dir rag --label current \
        --out eval/rag/results/retrieval-current.json
"""
from __future__ import annotations

import argparse
import importlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE / "datasets" / "v1"
KS = (1, 3, 5, 8)
TOP_K_DEFAULT = 8
TOP_K_MAX = 20
LEGACY_BROAD_MARKERS = (
    "every ", "all ", "complete", "full table", "entire", "each age", "each placement",
    "all age", "all placement", "list all", "list every",
)


def normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def load_questions(dataset: Path) -> list[dict[str, Any]]:
    rows = []
    for line in (dataset / "questions.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def import_rag(rag_dir: Path):
    sys.path.insert(0, str(rag_dir.resolve()))
    for name in ("document_loaders", "rag_engine", "retrieval_pipeline"):
        sys.modules.pop(name, None)
    engine = importlib.import_module("rag_engine")
    try:
        pipeline = importlib.import_module("retrieval_pipeline")
    except ImportError:
        pipeline = None
    return engine, pipeline


def legacy_search(engine, question: str, chunks: list, top_k: int) -> dict[str, Any]:
    effective = top_k
    if any(marker in question.casefold() for marker in LEGACY_BROAD_MARKERS):
        effective = max(top_k, min(TOP_K_MAX, max(TOP_K_DEFAULT, top_k * 2)))
    ranked = engine.retrieve(question, chunks, top_k=effective)
    if not ranked:
        return {"abstain": True, "reason": "no_match", "groups": []}
    groups = engine.dedupe_ranked_chunks(ranked)
    return {
        "abstain": False,
        "reason": None,
        "groups": [{"score": s, "source": c.source, "text": c.text, "files": f} for s, c, f in groups],
    }


def is_relevant(group: dict[str, Any], gold: list[dict[str, str]]) -> set[int]:
    text = normalise(group["text"])
    files = set(group.get("files") or [group["source"]])
    return {
        index for index, item in enumerate(gold)
        if item["doc"] in files and normalise(item["span"]) in text
    }


def score_question(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    gold = item["gold"]
    groups = result["groups"]
    row: dict[str, Any] = {
        "id": item["id"],
        "category": item["category"],
        "expect": item["expect"],
        "abstained": bool(result["abstain"]),
        "reason": result.get("reason"),
        "returned": len(groups),
        "context_chars": sum(len(g["text"]) for g in groups),
    }
    if not gold:
        return row
    hits = [is_relevant(group, gold) for group in groups]
    for k in KS:
        top = hits[:k]
        covered = set().union(*top) if top else set()
        row[f"recall@{k}"] = len(covered) / len(gold)
        row[f"precision@{k}"] = (sum(1 for h in top if h) / len(top)) if top else 0.0
    covered_all = set().union(*hits) if hits else set()
    row["recall@returned"] = len(covered_all) / len(gold)
    gold_docs = {g["doc"] for g in gold}
    found_docs = {g["doc"] for i, g in enumerate(gold) if i in covered_all}
    row["doc_recall@returned"] = len(found_docs) / len(gold_docs)
    first = next((rank for rank, h in enumerate(hits, start=1) if h), None)
    row["mrr"] = 1.0 / first if first else 0.0
    return row


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [r for r in rows if r["expect"] == "answer" and "mrr" in r]
    unanswerable = [r for r in rows if r["expect"] == "abstain"]
    summary: dict[str, Any] = {"questions": len(rows), "answerable_with_gold": len(answerable)}
    for key in [f"recall@{k}" for k in KS] + [f"precision@{k}" for k in KS] + [
        "recall@returned", "doc_recall@returned", "mrr",
    ]:
        summary[key] = round(statistics.mean(r[key] for r in answerable), 4) if answerable else None
    summary["answerable_false_abstain_rate"] = round(
        sum(1 for r in answerable if r["abstained"]) / len(answerable), 4) if answerable else None
    summary["unanswerable_gate_abstain_rate"] = round(
        sum(1 for r in unanswerable if r["abstained"]) / len(unanswerable), 4) if unanswerable else None
    summary["mean_context_chars"] = round(statistics.mean(r["context_chars"] for r in rows), 1)
    summary["max_context_chars"] = max(r["context_chars"] for r in rows)
    by_category: dict[str, dict[str, Any]] = {}
    for category in sorted({r["category"] for r in rows}):
        subset = [r for r in rows if r["category"] == category and "mrr" in r]
        if subset:
            by_category[category] = {
                "n": len(subset),
                "recall@returned": round(statistics.mean(r["recall@returned"] for r in subset), 4),
                "recall@5": round(statistics.mean(r["recall@5"] for r in subset), 4),
                "mrr": round(statistics.mean(r["mrr"] for r in subset), 4),
            }
    summary["by_category"] = by_category
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline retrieval benchmark (no GPU).")
    parser.add_argument("--rag-dir", type=Path, default=HERE.parent.parent / "rag")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--label", default="current")
    parser.add_argument("--top-k", type=int, default=TOP_K_DEFAULT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    engine, pipeline = import_rag(args.rag_dir)
    docs = args.dataset / "docs"
    started = time.perf_counter()
    if pipeline is not None:
        chunks = pipeline.load_collection(docs).chunks
    else:
        chunks = engine.load_chunks(docs)
    load_ms = (time.perf_counter() - started) * 1000

    rows = []
    latencies = []
    for item in load_questions(args.dataset):
        t0 = time.perf_counter()
        if pipeline is not None:
            outcome = pipeline.search(item["question"], chunks, top_k=args.top_k)
            result = {
                "abstain": outcome.abstain,
                "reason": outcome.reason,
                "groups": [
                    {"score": g.score, "source": g.chunk.source, "text": g.chunk.text, "files": g.files}
                    for g in outcome.groups
                ],
            }
        else:
            result = legacy_search(engine, item["question"], chunks, args.top_k)
        latencies.append((time.perf_counter() - t0) * 1000)
        rows.append(score_question(item, result))

    summary = summarise(rows)
    summary.update({
        "label": args.label,
        "pipeline": "retrieval_pipeline.search" if pipeline is not None else "legacy_bm25",
        "chunks": len(chunks),
        "index_build_ms": round(load_ms, 1),
        "search_ms_p50": round(statistics.median(latencies), 3),
        "search_ms_max": round(max(latencies), 3),
    })
    report = {"summary": summary, "questions": rows}
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    printable = {k: v for k, v in summary.items() if k != "by_category"}
    print(json.dumps(printable, indent=2))
    print(json.dumps(summary["by_category"], indent=2))
    misses = [r["id"] for r in rows if r.get("recall@returned", 1.0) < 1.0]
    print("incomplete_recall:", ",".join(misses) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
