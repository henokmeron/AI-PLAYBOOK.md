# BM25 retrieval calibration — fictional demo corpus — 2026-10-11

## Observed result

Source: user screenshot from `rag/evaluate_retrieval.py`, run locally without inference calls.

- Documents: 2 (`expenses-policy.md`, `employee-handbook.md`)
- Chunks: 2
- Answerable examples: 6; expected source was top-ranked in 6/6.
- Answerable top-score range: **2.351–5.797**.
- Unanswerable examples: 6.
- Unanswerable top-score range: **0.690–2.258**.
- Gap between closest observed positive and negative scores: **0.093** (2.351 − 2.258).

The 12 query cases covered expense receipt deadline, approval over £100, reimbursement timing, rail class, office hours and document storage (answerable), plus yacht colour, VAT number, payroll identifier, Paris registered office, CEO's favourite food and incorporation date (unanswerable).

## Decision

For the **existing two-file fictional demo corpus only**, configure `rag/ask_documents.py` to require a top BM25 score of at least **2.30** before sending evidence to Gemma. This value sits in the observed gap for this tiny labelled sample. It is provisional, not a universal relevance threshold.

A narrow gap makes this fragile: another query wording or document could shift scores. Before using a different corpus, build a representative answerable/unanswerable set and rerun calibration. If ranges overlap, do not use a single threshold to claim relevance; improve retrieval and evaluation.

## Validation still required

- Refresh `ask_documents.py` and `run_rag_regression.py` on the current Pod from GitHub.
- Run the revised five-case regression suite. It should show the gate blocks the low-score yacht question before model inference, while a separate invocation with `--min-score 0` verifies the model's abstention when the irrelevant chunks are deliberately passed through.
- Record the actual run before calling this threshold validated even on the demo set.
