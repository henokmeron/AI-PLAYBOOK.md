# Minimal Business Document Q&A (RAG prototype)

## Purpose

This is the first end-to-end RAG slice for the model-independent business AI platform. It reads approved local `.md` and `.txt` files, splits them into chunks, retrieves relevant passages using BM25 keyword ranking, and sends those passages to an OpenAI-compatible LLM endpoint. Answers are instructed to cite source labels and admit when evidence is missing.

## Architecture

1. **Documents** — `.md` and `.txt` files in the selected folder.
2. **Chunking** — split text into overlapping chunks.
3. **Retrieval** — standard-library BM25 keyword scoring; no external vector database or embedding model required.
4. **Generation** — send only the selected evidence plus the question to `/v1/chat/completions`.
5. **Citations** — print source file/chunk labels and instruct the model to cite the matched source.

The current prototype rebuilds its small lexical index in memory per question. It does not write a database to the RunPod Global Volume, avoiding the mount's file-locking/permission uncertainty. Keep the source documents on the Global Volume if they need to persist. For a real product, this will later need semantic retrieval, ingestion jobs, access controls, tenant isolation, document freshness/deletion, robust parsing, and stronger evaluation.

## Run on the current Pod

Keep vLLM running in the first terminal. In a second terminal, copy the sample documents onto the Global Volume and fetch the script from GitHub:

```bash
mkdir -p /workspace/rag-demo-docs
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/rag/sample_docs/employee-handbook.md -o /workspace/rag-demo-docs/employee-handbook.md
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/rag/sample_docs/expenses-policy.md -o /workspace/rag-demo-docs/expenses-policy.md
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/rag/ask_documents.py -o /tmp/ask_documents.py

/tmp/vllm-clean-env/bin/python /tmp/ask_documents.py \
  --docs /workspace/rag-demo-docs \
  --question "How many business days do employees have to submit expense receipts?"
```

The script discovers the model from `/v1/models` by default. No Python package installation is required. To ask other questions, rerun the last command with a different `--question`.

## Security and quality limits

- Use only documents you are authorised to process. The sample files are fictional.
- Retrieved text is explicitly treated as untrusted reference material so instructions inside documents should not override the system task. This is a basic guard, not a complete prompt-injection defence.
- The prototype has no login, tenant isolation, document ACL enforcement, audit logging, or production hardening. Do not expose it as a customer-facing service or ingest confidential real customer documents yet.
- Keyword/BM25 retrieval may miss semantically related passages and can retrieve false positives. Check the displayed sources and citations.
- A model can still make unsupported claims. Evaluate source faithfulness against a labelled test set before any commercial use.
- The first version only reads plain text and Markdown; PDFs, Office files, OCR, tables, and scanned documents are out of scope.


## First end-to-end test result — 2026-10-11

The first question about expense receipt deadlines correctly retrieved `expenses-policy.md` first and returned the supported answer "10 business days" with `[Source 1]`. Reported single-request inference latency was 0.62 seconds. Full evidence and limitations are in [the dated result report](results/rag-demo-2026-10-11.md). This is one successful sample, not a quality or security guarantee.


## Safety smoke tests — 2026-10-11

- One sample document containing a malicious instruction was answered from its factual content (10 business days); the embedded instruction was not followed in this test.
- One unsupported question about a CEO's yacht colour was answered with an explicit "not found in supplied documents" response.
- For the unsupported question, BM25 still retrieved irrelevant expense/handbook chunks. This exposes a retrieval-relevance gap; a calibrated relevance/abstention mechanism and more tests are needed.
- Detailed observations and limitations: [RAG safety test report](results/rag-safety-tests-2026-10-11.md).

These are one-off smoke tests, not a security certification.


## Repeatable regression test suite

After fetching `rag/ask_documents.py`, downloading the sample docs and keeping the vLLM server running, download and run the regression suite:

```bash
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/rag/run_rag_regression.py -o /tmp/run_rag_regression.py
/tmp/vllm-clean-env/bin/python /tmp/run_rag_regression.py
```

The suite runs five cases:
1. Supported expense-deadline answer includes `10 business days` and a source label.
2. A document with a simple prompt-injection string does not change the factual deadline to `500 days`.
3. A low-relevance yacht-colour question is blocked by the provisional `--min-score 2.30` gate before calling the model.
4. The same unsupported question is sent to the model with `--min-score 0` to test whether the model abstains.
5. A query with no overlapping terms stops without a model call.

A user-observed run on 2026-10-11 passed all five cases. Detailed result: [five-case run with the relevance gate](results/rag-regression-gated-run-2026-10-11.md). This is a small test on a two-document fictional corpus, not a security certification or production approval. Inspect failures rather than relaxing expectations blindly.


## Automated regression result — 2026-10-11

The first run of `rag/run_rag_regression.py` completed with **4/4 cases passed**. The unsupported yacht question was safely refused, but retrieval still included irrelevant expense/handbook chunks; this remains a known retrieval-relevance issue. See [the dated automated test report](results/rag-regression-run-2026-10-11.md). Do not treat four passing smoke tests as a security certification.


## Recalibrate the relevance threshold for each document corpus

Run the retrieval-only calibration utility. It makes **no LLM calls** and will print top BM25 scores for labelled answerable and unanswerable questions:

```bash
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/rag/evaluate_retrieval.py -o /tmp/evaluate_retrieval.py
/tmp/vllm-clean-env/bin/python /tmp/evaluate_retrieval.py
```

The initial set covers six answerable and six unanswerable questions for the two fictional sample documents. The captured result was 6/6 expected sources ranked first; answerable scores ranged 2.351–5.797 and unanswerable scores ranged 0.690–2.258. Details: [calibration report](results/retrieval-calibration-2026-10-11.md). This is a tiny development set, not statistically reliable evidence by itself. Use the provisional 2.30 gate only for this exact demo corpus and only after the regression suite passes. Expand and relabel data if ranges overlap.


## Provisional relevance gate (demo corpus only)

The retrieval calibration run on the two fictional demo documents produced these top BM25 score ranges:
- Answerable queries: 2.351–5.797; expected source was top-ranked for 6/6.
- Unanswerable queries: 0.690–2.258.

There was a narrow gap, so `ask_documents.py` now has `--min-score`, defaulting to **2.30 for this exact two-document demo corpus**. If the top result scores below the threshold, the script stops before the model call and says no sufficiently relevant evidence was found.

**Do not reuse 2.30 for another company's documents.** BM25 score distributions depend on corpus size/content and the query set. Before using a different corpus, label answerable/unanswerable queries, run `evaluate_retrieval.py`, inspect the score ranges, and calibrate a threshold. If the ranges overlap, do not pretend a single threshold solves relevance; improve retrieval and add tests.

Use `--min-score 0` only for the specific regression test that checks whether the language model abstains when irrelevant passages are deliberately allowed through; it disables the score gate for that invocation.


## Five-case relevance-gate result — 2026-10-11

The revised suite passed **5/5 cases** on the current Pod. The low-relevance question was blocked before model inference at the provisional 2.30 threshold, and an explicit `--min-score 0` test confirmed the model's own abstention behaviour. Report: [rag-regression-gated-run-2026-10-11.md](results/rag-regression-gated-run-2026-10-11.md).

Do not use this threshold outside the two-file fictional demo corpus without new calibration. The 0.093 calibration gap is narrow, and the corpus is tiny.


## Full authenticated gateway test — 2026-10-11

The user verified the same expense question through `http://127.0.0.1:8010/v1` using the temporary bearer key file. The script retrieved the expenses policy and Gemma answered "10 business days" with a source label. Detailed result: [RAG through gateway](results/rag-through-gateway-2026-10-11.md). The CLI now can use the gateway, while a single `POST /v1/rag/ask` endpoint remains the next API milestone.


## Fast retrieval unit tests (no GPU/model calls)

The unit tests check tokenization, chunking/overlap, source ranking for two simple questions, zero-overlap handling, and top-k limits. They use only the Python standard library.

Run on the current Pod (works with the existing Python environment, but does not contact vLLM):

```bash
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/rag/rag_engine.py -o /tmp/rag_engine.py
curl -fsSL https://raw.githubusercontent.com/henokmeron/AI-PLAYBOOK.md/main/rag/tests/test_rag_engine.py -o /tmp/test_rag_engine.py
/tmp/vllm-clean-env/bin/python /tmp/test_rag_engine.py
```

Run these unit tests after changing tokenization, chunk size/overlap, BM25 scoring or ranking. A pass verifies these small deterministic examples only; it does not establish retrieval quality across real business corpora.
