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
