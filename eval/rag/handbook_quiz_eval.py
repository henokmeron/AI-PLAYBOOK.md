#!/usr/bin/env python3
"""Score the recovered MSFC handbook quiz against a local collection.

Prints page numbers, scores, and whether the traced passages were packed.
Does not print the handbook. Exit 0 when the collection is absent unless
--require is set. Exit 1 when a required page is indexed but not packed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "rag"), str(ROOT / "api")]

from retrieval_pipeline import FileBackedBm25Store, build_evidence, search, split_numbered_questions  # noqa: E402
import local_gateway as gateway  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "datasets" / "msfc-hdbk-3173-quiz.json"


def load_fixture() -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    question = data["question"]
    if len(question) != data["question_chars"] or not question.endswith(data["question_tail"]):
        raise SystemExit("fixture question does not match the recovered 2000-character paste")
    return data


def phrase_pages(chunks: list, phrase: str) -> list[int]:
    pages = []
    needle = phrase.casefold()
    for chunk in chunks:
        if needle in chunk.text.casefold():
            page = chunk.meta.get("page")
            if isinstance(page, int) and page not in pages:
                pages.append(page)
    return pages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", type=Path, default=None)
    parser.add_argument("--require", action="store_true")
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()
    fixture = load_fixture()
    if args.collection is None or not args.collection.is_dir():
        print("collection_absent", args.collection)
        return 2 if args.require else 0

    question = fixture["question"]
    index = FileBackedBm25Store().load(args.collection)
    pages = {chunk.meta.get("page") for chunk in index.chunks if isinstance(chunk.meta.get("page"), int)}
    print("chunks", len(index.chunks), "distinct_pages", len(pages), "sources", len(index.sources))
    for phrase in fixture["absent_phrases"]:
        print("absent_phrase", phrase, "pages", phrase_pages(index.chunks, phrase)[:5])

    parts = split_numbered_questions(question)
    print("parts", len(parts), "q10_chars", len(parts[-1]) if parts else 0)
    outcome = search(
        question, index, args.top_k,
        allowed_sources=set(index.sources), min_score=0.0, min_coverage=0.15,
    )
    ratio = gateway.evidence_chars_per_token(outcome.groups)
    _history, budget, _dropped = gateway.fit_history_to_budget(
        question, [], index.sources, chars_per_token=ratio,
    )
    pack = build_evidence(outcome.groups, budget)
    packed_pages = [source.get("location", {}).get("page") for source in pack.sources]
    print(
        "packed", len(pack.sources),
        "dropped", pack.dropped,
        "budget", budget,
        "chars_per_token", ratio,
        "pages", packed_pages,
    )
    failures = 0
    for number, part in enumerate(parts, start=1):
        one = search(
            part, index, args.top_k,
            allowed_sources=set(index.sources), min_score=0.0, min_coverage=0.15,
        )
        got = [group.chunk.meta.get("page") for group in one.groups[:8]]
        needed = fixture["recall_pages"].get(str(number), [])
        in_part = [page for page in needed if page in got]
        in_pack = [page for page in needed if page in packed_pages]
        missed = bool(needed) and not in_pack
        if missed:
            failures += 1
        print(
            "Q", number,
            "abstain", one.abstain,
            "reason", one.reason,
            "top", None if one.top_score is None else round(one.top_score, 3),
            "pages", got[:5],
            "needed", needed,
            "in_part", in_part,
            "in_pack", in_pack,
            "pack_miss", missed,
        )
    print("recall_failures", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
