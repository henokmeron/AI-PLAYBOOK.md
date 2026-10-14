#!/usr/bin/env python3
"""Ablate individual retrieval changes on dataset v1 (offline, deterministic).

Each variant monkeypatches one feature off and reports recall@1/@3, MRR and
gate behaviour, so every retained change is justified by measured gain.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "rag"))
sys.path.insert(0, str(HERE))

import document_loaders  # noqa: E402
import rag_engine  # noqa: E402
import retrieval_pipeline  # noqa: E402
from run_retrieval import load_questions, score_question, summarise  # noqa: E402

DATASET = HERE / "datasets" / "v1"


def run(min_coverage: float = 0.0) -> dict:
    index = retrieval_pipeline.load_collection(DATASET / "docs")
    rows = []
    for item in load_questions(DATASET):
        outcome = retrieval_pipeline.search(item["question"], index, 8, min_coverage=min_coverage)
        result = {
            "abstain": outcome.abstain,
            "reason": outcome.reason,
            "groups": [
                {"score": g.score, "source": g.chunk.source, "text": g.chunk.text, "files": g.files}
                for g in outcome.groups
            ],
        }
        rows.append(score_question(item, result))
    s = summarise(rows)
    return {k: s[k] for k in ("recall@1", "recall@3", "recall@5", "mrr", "answerable_false_abstain_rate",
                              "unanswerable_gate_abstain_rate", "mean_context_chars")}


def main() -> int:
    results = {"all_changes": run()}

    original_stem = rag_engine.stem
    rag_engine.stem = lambda token: token
    results["no_plural_folding"] = run()
    rag_engine.stem = original_stem

    original_chunk_segments = rag_engine.chunk_segments
    original_index_terms = rag_engine.index_terms

    def chunk_without_names(source, segments, **kwargs):
        rag_engine.index_terms = lambda text: [] if text == rag_engine.Path(source).stem else original_index_terms(text)
        try:
            return original_chunk_segments(source, segments, **kwargs)
        finally:
            rag_engine.index_terms = original_index_terms

    rag_engine.chunk_segments = chunk_without_names
    results["no_filename_terms"] = run()
    rag_engine.chunk_segments = original_chunk_segments

    original_re = rag_engine.INDEX_TOKEN_RE
    rag_engine.INDEX_TOKEN_RE = rag_engine.TOKEN_RE
    results["no_underscore_split"] = run()
    rag_engine.INDEX_TOKEN_RE = original_re

    original_csv = document_loaders._read_csv_segment

    def plain_csv(path):
        segment = original_csv(path)
        lines = []
        for line in segment.text.splitlines():
            head, _, rest = line.partition(": ")
            lines.append(head + ": " + " | ".join(c.split("=", 1)[-1] for c in rest.split(" | ")))
        return document_loaders.Segment("\n".join(lines), {"kind": "table", "table_header": ""})

    document_loaders._read_csv_segment = plain_csv
    results["no_csv_header_pairing"] = run()
    document_loaders._read_csv_segment = original_csv

    for threshold in (0.10, 0.15, 0.18, 0.20, 0.25):
        results[f"coverage_gate_{threshold:.2f}"] = run(min_coverage=threshold)
    text = json.dumps(results, indent=2)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
