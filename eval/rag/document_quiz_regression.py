#!/usr/bin/env python3
"""Offline quiz regression that does not use one particular PDF.

Builds a synthetic multi-section corpus and a numbered quiz longer than the
old 2,000-character question box. Scores five behaviours and prints counts:

- silent truncation: a maxlength box that stores a prefix drops the closing
  marker; the current limit keeps the whole quiz
- context packing: the spreadsheet character ratio versus the prose ratio,
  using the gateway budget
- multi-question prompts: each numbered item is gated on its own
- abstention: the item whose terms are not in the corpus still abstains and
  is left out of the model prompt
- citations: a missing label is withheld; a grounded quote is kept; a quote
  that is not in the chunk is withheld

No model is called. Exit 1 when a check fails. The printed JSON has counts,
ratios, and booleans, not the document text.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT / "rag", ROOT / "api"):
    entry = str(extra)
    if entry not in sys.path:
        sys.path.insert(0, entry)

import local_gateway as gateway  # noqa: E402
from retrieval_pipeline import (  # noqa: E402
    FileBackedBm25Store,
    answer_delivery,
    build_evidence,
    generation_question,
    search,
    split_numbered_questions,
)

OLD_SILENT_CAP = 2000
ANSWERABLE_COUNT = 8
ABSENT_NUMBER = 9
TAIL_NUMBER = 10
TAIL_MARKER = "quiztailcomplete"
ABSENT_TERMS = ("zanthorpe", "brindlewick")
FACTS = (
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "twentyone",
    "twentytwo",
    "twentythree",
    "twentyfour",
    "twentyfive",
    "twentysix",
)


def section_token(number: int) -> str:
    return f"markersection{number:02d}"


def section_filename(number: int) -> str:
    return f"section-{number:02d}.txt"


def _paragraph(token: str, fact: str, salt: str, extra: str = "") -> str:
    filler = " ".join(f"{token}{salt}{i:02d}" for i in range(48))
    sentence = f"Depot record {token} states the axle count is {fact}."
    tail = f" {extra}" if extra else ""
    return f"{sentence}{tail} {filler}"


def write_corpus(folder: Path) -> None:
    """One text file per answerable section. Two paragraphs become two chunks."""
    numbers = list(range(1, ANSWERABLE_COUNT + 1)) + [TAIL_NUMBER]
    for number in numbers:
        token = section_token(number)
        fact = FACTS[number - 1]
        extra = f"The closing marker is {TAIL_MARKER}." if number == TAIL_NUMBER else ""
        body = _paragraph(token, fact, "a", extra) + "\n\n" + _paragraph(token, fact, "b")
        (folder / section_filename(number)).write_text(body, encoding="utf-8")


def _answerable_line(number: int) -> str:
    token = section_token(number)
    return (
        f"{number}. Where does the depot record {token}, "
        "and which axle count does that record state?"
    )


def build_quiz() -> str:
    """Numbered quiz whose closing marker sits past the old silent cap.

    The absent item uses terms that are not written into any section. The
    padding on the last item repeats words that are in that section, so the
    length does not by itself force an abstention.
    """
    lines = [_answerable_line(number) for number in range(1, ANSWERABLE_COUNT + 1)]
    lines.append(
        f"{ABSENT_NUMBER}. What is the {ABSENT_TERMS[0]} {ABSENT_TERMS[1]} "
        "tariff for a private yacht launch? Give the exact figure."
    )
    token = section_token(TAIL_NUMBER)
    repeated = (
        f"Where does the depot record {token}, and which axle count does that record state?"
    )
    question = ""
    for copies in range(8, 40):
        padding = " ".join([repeated] * copies)
        question = "\n\n".join(lines + [
            f"{TAIL_NUMBER}. {padding} The closing marker is {TAIL_MARKER}.",
        ])
        if question.find(TAIL_MARKER) > OLD_SILENT_CAP:
            break
    if question.find(TAIL_MARKER) <= OLD_SILENT_CAP:
        raise RuntimeError("quiz tail marker is inside the old silent cap")
    if len(question) > gateway.MAX_QUESTION_CHARS:
        raise RuntimeError("quiz exceeds the current question limit")
    return question


def stored_question(text: str, cap: int, *, refuse_over: bool) -> str | None:
    """What a question box keeps.

    ``refuse_over`` is the current box: a paste past the cap is rejected and
    the end is not stored as a cut-off prefix. The old box stored ``text[:cap]``.
    """
    if len(text) <= cap:
        return text
    if refuse_over:
        return None
    return text[:cap]


def _pack(question: str, index, ratio: float) -> dict:
    outcome = search(
        question,
        index,
        8,
        allowed_sources=set(index.sources),
        min_score=0.0,
        min_coverage=0.15,
    )
    model_question, notes = generation_question(question, outcome.part_abstain)
    _history, budget, history_dropped = gateway.fit_history_to_budget(
        model_question,
        [],
        index.sources,
        chars_per_token=ratio,
    )
    pack = build_evidence(outcome.groups, budget)
    packed_text = "\n".join(pack.blocks)
    return {
        "ratio": ratio,
        "budget": budget,
        "packed": len(pack.sources),
        "dropped": pack.dropped,
        "evidence_chars": pack.chars,
        "history_dropped": history_dropped,
        "groups": len(outcome.groups),
        "tail_marker_packed": TAIL_MARKER in packed_text.casefold(),
        "packed_files": [source["file"] for source in pack.sources],
        "model_question": model_question,
        "notes": notes,
        "part_abstain": list(outcome.part_abstain),
        "abstain": outcome.abstain,
    }


def _citation_checks(folder: Path) -> dict:
    sample = (folder / section_filename(1)).read_text(encoding="utf-8")
    first_paragraph = sample.split("\n\n", 1)[0]
    quote = f"Depot record {section_token(1)} states the axle count is {FACTS[0]}"
    missing, _missing_info = answer_delivery(f"{quote}.", 1)
    grounded, _grounded_info = answer_delivery(f"{quote} [Source 1].", 1, [first_paragraph])
    invented, _invented_info = answer_delivery(
        f"Depot record {section_token(1)} states the axle count is ninety [Source 1].",
        1,
        [first_paragraph],
    )
    return {
        "missing_label_withheld": missing == "abstained",
        "grounded_quote_kept": grounded == "answered",
        "ungrounded_quote_withheld": invented == "abstained",
    }


def evaluate() -> dict:
    question = build_quiz()
    old_stored = stored_question(question, OLD_SILENT_CAP, refuse_over=False)
    current_stored = stored_question(
        question, gateway.MAX_QUESTION_CHARS, refuse_over=True,
    )
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="quiz-regression-") as tmp:
        folder = Path(tmp)
        write_corpus(folder)
        index = FileBackedBm25Store().load(folder)
        before = _pack(question, index, gateway.RAG_CHARS_PER_TOKEN)
        after_ratio = _detected_ratio(question, index)
        after = _pack(question, index, after_ratio)
        citations = _citation_checks(folder)
        absent_alone = search(
            question.split("\n\n")[ABSENT_NUMBER - 1],
            index,
            8,
            allowed_sources=set(index.sources),
            min_score=0.0,
            min_coverage=0.15,
        )
        tail_alone = search(
            _answerable_line(TAIL_NUMBER),
            index,
            8,
            allowed_sources=set(index.sources),
            min_score=0.0,
            min_coverage=0.15,
        )
        corpus_files = len(index.sources)
        corpus_chunks = len(index.chunks)

    parts = split_numbered_questions(question)
    model_question = after.pop("model_question")
    notes = after.pop("notes")
    part_abstain = after.pop("part_abstain")
    before.pop("model_question")
    before.pop("notes")
    before.pop("part_abstain")
    report = {
        "question_chars": len(question),
        "parts": len(parts),
        "old_cap_chars": OLD_SILENT_CAP,
        "current_cap_chars": gateway.MAX_QUESTION_CHARS,
        "tail_marker_in_full": TAIL_MARKER in question,
        "tail_marker_in_old_cap": TAIL_MARKER in (old_stored or ""),
        "old_cap_stored_chars": len(old_stored or ""),
        "current_cap_keeps_quiz": current_stored == question,
        "before": before,
        "after": after,
        "citations": citations,
        "absent_part_abstains": (
            len(part_abstain) == len(parts) and part_abstain[ABSENT_NUMBER - 1] is True
        ),
        "answerable_parts_abstain": [
            index + 1 for index, flag in enumerate(part_abstain) if flag and index + 1 != ABSENT_NUMBER
        ],
        "absent_terms_in_model_question": any(term in model_question.casefold() for term in ABSENT_TERMS),
        "tail_marker_in_model_question": TAIL_MARKER in model_question.casefold(),
        "absent_note_count": sum(1 for note in notes if f"Question {ABSENT_NUMBER}" in note),
        "standalone_absent_abstains": absent_alone.abstain and not absent_alone.groups,
        "standalone_absent_reason": absent_alone.reason,
        "standalone_tail_abstains": tail_alone.abstain,
        "corpus_files": corpus_files,
        "corpus_chunks": corpus_chunks,
    }
    if not report["tail_marker_in_full"] or report["tail_marker_in_old_cap"]:
        failures.append("silent_truncation")
    if not report["current_cap_keeps_quiz"]:
        failures.append("current_cap_drops_quiz")
    if report["parts"] < 2:
        failures.append("not_a_multi_question_prompt")
    if not report["absent_part_abstains"] or report["absent_terms_in_model_question"]:
        failures.append("abstention")
    if not report["standalone_absent_abstains"]:
        failures.append("standalone_abstention")
    if report["standalone_tail_abstains"] or report["answerable_parts_abstain"]:
        failures.append("answerable_abstained")
    if not report["tail_marker_in_model_question"]:
        failures.append("tail_omitted_from_prompt")
    if report["absent_note_count"] != 1:
        failures.append("absent_note")
    if before["packed"] >= after["packed"]:
        failures.append("prose_budget_did_not_pack_more")
    if not after["tail_marker_packed"]:
        failures.append("tail_not_packed_at_prose_ratio")
    if before["tail_marker_packed"]:
        failures.append("tail_packed_at_spreadsheet_ratio")
    if after["ratio"] <= before["ratio"]:
        failures.append("prose_ratio_not_wider")
    for name, ok in citations.items():
        if not ok:
            failures.append(name)
    report["failures"] = failures
    report["ok"] = not failures
    return report


def _detected_ratio(question: str, index) -> float:
    """Prose-or-table ratio the gateway would use for this quiz."""
    outcome = search(
        question,
        index,
        8,
        allowed_sources=set(index.sources),
        min_score=0.0,
        min_coverage=0.15,
    )
    return gateway.evidence_chars_per_token(outcome.groups)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = evaluate()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    before = report["before"]
    after = report["after"]
    print(
        "before_packed", before["packed"],
        "before_dropped", before["dropped"],
        "before_ratio", before["ratio"],
        "after_packed", after["packed"],
        "after_dropped", after["dropped"],
        "after_ratio", after["ratio"],
        "failures", ",".join(report["failures"]) or "none",
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
