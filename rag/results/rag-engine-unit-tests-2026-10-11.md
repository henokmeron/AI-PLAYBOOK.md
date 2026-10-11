# RAG engine unit-test run — 2026-10-11

## Result

**PASS: 10 tests ran, all OK**. The user's terminal screenshot shows `Ran 10 tests in 0.003s` followed by `OK`.

The tests cover:
- Case-insensitive tokenization.
- Empty/punctuation-only input handling.
- Short text and empty text chunking.
- Splitting longer text with overlapping chunks.
- Expected top ranking of the expense policy for an expense-receipt query.
- Expected top ranking of the employee handbook for office-hours questions.
- No-overlap query returns no retrieval results.
- `top_k` constrains returned results.

## Interpretation

These deterministic tests run locally using the Python standard library and do not call vLLM/Gemma or consume GPU inference. They give the shared BM25 retrieval engine a small regression guard for tokenization, chunking and ranking behaviour.

They do not establish quality on large or real business corpora, semantic search quality, complete prompt-injection resistance, access control, tenant isolation, or production readiness.
