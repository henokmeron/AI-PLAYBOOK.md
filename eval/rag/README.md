# Document Q&A benchmark

Dataset v1 is 11 synthetic documents (txt, md, html, csv, xlsx, docx, pdf) and 40 questions
in `datasets/v1/questions.jsonl`. Each question has a category, an expected outcome
(`answer` or `abstain`), gold evidence spans, and a reference answer. Nothing in it is a
real customer document.

## Retrieval only (no GPU, no services)

```bash
python eval/rag/run_retrieval.py --rag-dir rag --label current --out eval/rag/results/retrieval-current.json
python eval/rag/ablate_retrieval.py eval/rag/results/ablation-v1.json
python eval/rag/scale_probe.py
```

`run_retrieval.py` calls search with the coverage gate off. The gateway default is
`RAG_MIN_COVERAGE=0.15`; `ablate_retrieval.py` reports that threshold separately.
Rebuild the documents with `python eval/rag/build_dataset_v1.py` (it checks them with `--check`).

## Answers, against a running gateway

`run_e2e.py` uploads the dataset to one collection, asks every question, and scores the
answers. Point it at an isolated gateway. Do not point it at the gateway you are using.

```bash
python eval/rag/run_e2e.py --base-url http://127.0.0.1:8014 --key-file /path/to/key --label current --out results.json
python eval/rag/run_limits_probe.py --base-url http://127.0.0.1:8014 --key-file /path/to/key --label current --out limits.json
```

`eval/rag/pod_test_gateway.sh` starts that gateway on the Pod, on port 8014, with its own key.
It refuses the live ports.

The 2026-10-14 numbers are in `docs/results/rag-benchmark-2026-10-14.md`.

## Numbered quiz, no GPU

`document_quiz_regression.py` builds its own sections. It does not read the
handbook and it does not score memorised answers. It compares the old
2,000-character prefix with the current question limit, packs the same
retrieval at the spreadsheet ratio and at the prose ratio, and checks
abstention and citations.

```bash
python eval/rag/document_quiz_regression.py
```

Exit 0 when every check passes. The 2026-10-23 counts are in
`docs/results/document-quiz-regression-2026-10-23.md`.
