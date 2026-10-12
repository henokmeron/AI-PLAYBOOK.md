# RAG BM25 Retrieval Baseline — 2026-10-12

## Environment

- Model: existing Gemma 4 31B-it; unchanged.
- Retriever: current BM25-style keyword retrieval in `rag/ask_documents.py`.
- Corpus: two demo Markdown files in `/workspace/rag-demo-docs`.
- Chunks loaded: 2.
- Evaluation script: `rag/evaluate_retrieval.py`.
- This benchmark performs retrieval only; it does not evaluate generated answer correctness or citation precision.

## Observed results

| ID | Label | Top score | Top source correct |
|---|---|---:|---|
| A1 | Answerable | 5.363 | Yes — expenses-policy.md |
| A2 | Answerable | 4.538 | Yes — expenses-policy.md |
| A3 | Answerable | 5.200 | Yes — expenses-policy.md |
| A4 | Answerable | 4.615 | Yes — expenses-policy.md |
| A5 | Answerable | 5.797 | Yes — employee-handbook.md |
| A6 | Answerable | 2.351 | Yes — employee-handbook.md |
| U1 | Unanswerable | 0.690 | Negative case |
| U2 | Unanswerable | 0.963 | Negative case |
| U3 | Unanswerable | 1.355 | Negative case |
| U4 | Unanswerable | 2.258 | Negative case |
| U5 | Unanswerable | 0.690 | Negative case |
| U6 | Unanswerable | 0.694 | Negative case |

- Answerable expected source top-ranked: 6/6.
- Answerable top-score range: 2.351–5.797.
- Unanswerable top-score range: 0.690–2.258.
- The observed minimum positive and maximum negative scores are separated by 0.093.

## Interpretation and limits

This small sample has no overlap between answerable and unanswerable top scores, but the 0.093 separation is narrow. It does not establish robust abstention on a larger or changing corpus. The demo threshold of 2.30 is supported only as a provisional threshold for this exact two-file demo set; it must not be reused as a universal threshold or applied to managed customer collections without separate calibration.

The corpus contains only two documents and six positive/six negative questions. It does not yet test paraphrases, synonyms, multi-document synthesis, conflicting or superseded policies, long documents, tables, PDF/XLSX extraction, source-span accuracy, prompt injection, tenant isolation, or generated answer faithfulness.

## Next evaluation gates

1. Test the live RAG API on answerable, paraphrased, and unanswerable questions; record generated answer and source metadata.
2. Expand the labelled dataset to cover the cases above, with expected document and supporting source span.
3. Measure retrieval recall@k, answer correctness, citation precision, unsupported-claim rate, and abstention quality.
4. Compare current BM25 with hybrid lexical + semantic retrieval and reranking on the same frozen test set.
5. Keep corpus-specific thresholds; do not change the current retriever until a reproducible comparison shows improvement.

Status: **small-corpus retrieval baseline recorded; not production approval**.
