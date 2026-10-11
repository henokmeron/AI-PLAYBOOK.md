#!/usr/bin/env python3
"""Measure BM25 retrieval scores on a small labelled answerable/unanswerable set.

This tool does not call the LLM and does not change ask_documents.py.
It reports the top result and score so a rejection threshold can be based on
observed examples rather than chosen by guesswork.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ask_documents import load_chunks, retrieve

CASES = [
    {
        "id": "A1",
        "label": "answerable",
        "question": "How many business days do employees have to submit expense receipts?",
        "expected_source": "expenses-policy.md",
    },
    {
        "id": "A2",
        "label": "answerable",
        "question": "Who must approve a single expense above £100?",
        "expected_source": "expenses-policy.md",
    },
    {
        "id": "A3",
        "label": "answerable",
        "question": "When are approved complete expense claims normally reimbursed?",
        "expected_source": "expenses-policy.md",
    },
    {
        "id": "A4",
        "label": "answerable",
        "question": "What class should employees book for rail travel?",
        "expected_source": "expenses-policy.md",
    },
    {
        "id": "A5",
        "label": "answerable",
        "question": "What hours is the support office staffed Monday to Friday?",
        "expected_source": "employee-handbook.md",
    },
    {
        "id": "A6",
        "label": "answerable",
        "question": "Where should company documents be stored?",
        "expected_source": "employee-handbook.md",
    },
    {
        "id": "U1",
        "label": "unanswerable",
        "question": "What colour is the CEO's private yacht?",
        "expected_source": None,
    },
    {
        "id": "U2",
        "label": "unanswerable",
        "question": "What is the company's VAT registration number?",
        "expected_source": None,
    },
    {
        "id": "U3",
        "label": "unanswerable",
        "question": "What is the employee payroll identifier?",
        "expected_source": None,
    },
    {
        "id": "U4",
        "label": "unanswerable",
        "question": "Does the company have a registered office in Paris?",
        "expected_source": None,
    },
    {
        "id": "U5",
        "label": "unanswerable",
        "question": "What is the CEO's favourite food?",
        "expected_source": None,
    },
    {
        "id": "U6",
        "label": "unanswerable",
        "question": "What date was the company incorporated?",
        "expected_source": None,
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=Path("/workspace/rag-demo-docs"))
    args = parser.parse_args()

    try:
        chunks = load_chunks(args.docs)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("=== BM25 retrieval score calibration (no LLM calls) ===")
    print(f"Documents: {args.docs}")
    print(f"Chunks: {len(chunks)}")
    print("Higher scores generally indicate stronger lexical matches; scores alone do not prove factual answerability.")
    print()

    rows: list[tuple[str, str, float, bool | None]] = []
    for case in CASES:
        results = retrieve(case["question"], chunks, top_k=1)
        if not results:
            top_score = 0.0
            top_source = "(no match)"
        else:
            top_score, chunk = results[0]
            top_source = chunk.source
        if case["expected_source"] is None:
            correct_source: bool | None = None
            assessment = "NEGATIVE"
        else:
            correct_source = top_source == case["expected_source"]
            assessment = "TOP SOURCE CORRECT" if correct_source else "TOP SOURCE WRONG"
        rows.append((case["label"], case["id"], top_score, correct_source))
        print(f'[{case["label"].upper():12}] {case["id"]} score={top_score:.3f} | {assessment} | {top_source}')
        print(f'  Q: {case["question"]}')

    positives = sorted(r[2] for r in rows if r[0] == "answerable")
    negatives = sorted(r[2] for r in rows if r[0] == "unanswerable")
    positive_correct = sum(1 for r in rows if r[0] == "answerable" and r[3])
    print("\n=== SCORE SUMMARY ===")
    print(f"Answerable cases: {len(positives)}; expected source top-ranked: {positive_correct}/{len(positives)}")
    print(f"Answerable top-score range: {positives[0]:.3f}–{positives[-1]:.3f}")
    print(f"Unanswerable cases: {len(negatives)}; top-score range: {negatives[0]:.3f}–{negatives[-1]:.3f}")
    print("Do not select a threshold blindly if these ranges overlap. Review the labelled cases and expand the dataset before changing retrieval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
