# Live Platform and Recovery Preflight — 2026-10-12

## Confirmed user-observed results

### Live API smoke test
The user ran `evaluation/run_live_platform_smoke.py` on the current RunPod Pod. Result: **PASS, 0 failed checks**.

- Gateway health: HTTP 200, status `ok`, upstream `ok`.
- Model API: HTTP 200, model discovered.
- Unauthenticated RAG request: rejected with HTTP 401.
- Answerable RAG question: HTTP 200, status `answered`, expected phrase `10 business days`, expected source `expenses-policy.md`.
- Unanswerable yacht-colour question: HTTP 200, status `abstained`, no sources returned.
- Authenticated chat: HTTP 200, expected phrase found.

This is a smoke test of six specific conditions, not broad answer-quality, security, or production validation.

### Recovery asset preflight
The user ran `ops/preflight-recovery.sh`. Result: **0 failures**.

- Runtime `SHA256SUMS`: all four listed artifacts verified OK.
- Runtime archive integrity: passed; archive size reported as 8,422,993,920 bytes (approximately 7.85 GiB; human-readable `ls` output on the same Pod showed 3.4G, so the archive-size reporting is inconsistent and should be reconciled before planning disk capacity).
- Four timestamped copies exist for each deployed gateway module: `platform_gateway.py`, `rag_engine.py`, `document_loaders.py`, and `document_library.py`.
- Required parser wheels exist: pypdf 6.20.0, openpyxl 3.1.5, et_xmlfile 2.0.0, defusedxml 0.7.1.
- Both parser wheelhouse checksum manifests passed.
- The optional syntax check of `/tmp/AI-PLAYBOOK/ops/start-platform.sh` was skipped because that checkout is absent.

### Startup script check
The user separately downloaded `ops/start-platform.sh`, ran `bash -n /tmp/start-platform.sh` successfully, then ran `bash /tmp/start-platform.sh --check`. It reported model config OK, two weight shards, runtime environment present, vLLM API healthy, gateway healthy, console healthy, and gateway key permissions `600`.

### Retrieval baseline
The six labelled answerable demo questions ranked the expected source first (6/6). Answerable scores: 2.351–5.797. Six unanswerable scores: 0.690–2.258. The minimum positive / maximum negative separation is only 0.093. Keep the 2.30 threshold provisional and scoped to the two-file fictional demo corpus.

## Current limits and next gates

1. Do not stop the current Pod merely to test recovery. A real cold-start recovery drill is not yet completed.
2. Before relying on `ops/start-platform.sh` for recovery, validate timestamp-matched source backup hashes against their manifest, ensure parser wheels are restored into `/tmp/rag-deps`, and verify the gateway starts with those dependencies.
3. Expand live RAG evaluation with paraphrases, unsupported questions, exact expected sources, and answer checks; then add long documents, multi-document questions, conflict handling, and injection cases.
4. Do not describe this small demo as production-ready. No customer corpus or broad quality benchmark has been validated.

## Cost-aware next action

Run the pure-Python retrieval unit tests first (no LLM inference/GPU work). Then run a small, bounded live RAG regression set and record exact per-case results before changing retrieval code or thresholds.
