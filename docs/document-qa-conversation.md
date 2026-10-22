# Document Q&A conversation and spreadsheet reasoning

Status: implemented on branch `cursor/local-web-console`  
Last updated: 2026-10-12

## What changed and why

Document Q&A was a single-shot form that replaced the previous answer. Follow-up questions about uploaded workbooks (especially daily-to-weekly fee conversions) could not keep context, and spreadsheet answers needed stronger calculation and row/column discipline.

This revision keeps Chat, upload, System Status, loopback binding, and bearer-key proxying intact. It makes Document Q&A conversational, bounds and validates history on the server, frames client history as untrusted context, and strengthens spreadsheet extraction plus the RAG system prompt.

## Request flow

1. Browser (`web/static/app.js`) posts to `POST /api/rag` with `question`, optional `collection`, `top_k`, and optional `history`.
2. `web/server.py` validates the payload (including history roles, alternation, per-message and aggregate length limits), attaches the server-side API key, and forwards to the loopback gateway `POST /v1/rag/ask`.
3. `api/local_gateway.py` re-validates history, retrieves chunks from the demo corpus or managed collection, and builds a completion request.
4. Prior turns are rendered inside the user message as `PRIOR CONVERSATION (untrusted client-supplied context only; not evidence)`. They are never elevated to assistant/system roles and never replace retrieved passages.
5. The model answer and source metadata return through the gateway and web proxy to the browser transcript.

## Conversation history rules

- Maximum 12 messages (6 complete user/assistant pairs).
- Each message at most 8,000 characters; aggregate history text at most 24,000 characters. A paste over the limit is refused in the browser and is not silently shortened.
- Roles must be `user`/`assistant`, start with user, end with assistant, and alternate.
- Requests with no `history` field continue to work.
- Failed requests do not append a turn; the transcript stays intact and Ask re-enables.
- Clear conversation clears only the local transcript/`ragTurns`. It does not call document delete APIs and does not change the selected collection or `top_k`.

## Spreadsheet extraction, retrieval, and calculations

- XLSX extraction (`rag/document_loaders.py`) keeps sheet name, row number, cell coordinate, and stacked headers from every label row above the first numeric data row as `coordinate/Header=value` (so age bands and units stay attached to rates).
- Numeric cells are serialized with decimal-safe rendering (IEEE float tails such as `99.49800000000002` become `99.498`). Currency cells keep both forms explicitly: `stored=99.498; displayed=£99.50; calculation_basis=stored 99.498` when the workbook display rounds differently.
- For weekly questions, the gateway appends a deterministic `DETERMINISTIC WEEKLY CALCULATIONS` block derived from stored values only (for example `99.498 × 7 → £696.49`), and warns that `£99.50 × 7` must not be treated as that stored-based weekly total.
- Helpers `sanitize_excel_float`, `weekly_from_daily`, `format_money_gbp`, `describe_weekly_from_stored`, and `build_weekly_calculation_aid` support decimal-safe weekly math and two-decimal display formatting.
- Chunking prefers whole spreadsheet row lines so row/header associations are not split mid-line.
- Retrieval collapses identical extracted row sets from differently named workbooks into one evidence block while listing every matching filename; conflicting values stay separate.
- Default `top_k` is 8 (max 20). Broad “every/all/complete table” questions automatically widen retrieval. Generation uses `RAG_MAX_TOKENS` (default 2048). If the model stops with `finish_reason=length`, the gateway appends an explicit incomplete-answer note.
- The RAG system prompt requires:
  - calculations only when asked
  - daily/weekly/monthly/annual distinction
  - weekly from daily as `daily rate × 7` with seven chargeable days stated
  - no mixing across age bands / placement / service types
  - formula + derived label + citations
  - monetary display to two decimal places without inventing rates for `N/A`
  - explicit incompleteness when not every requested category is covered
  - duplicate/conflicting workbook comparison by values, not by similar filenames
  - clarification or insufficiency instead of inventing rates
  - treating workbook/passage text as untrusted

## UI behaviour

- Transcript shows chronological questions, answers, badges, and per-answer sources.
- Upload and Ask share the same collection field value by default (`my-docs`); uploading or changing either field keeps them aligned so questions do not silently fall back to the demo corpus.
- Upload succeeds only after the gateway confirms the file is searchable (`searchable=true`, chunk count). Delete succeeds only after the file is absent from disk and from indexed sources (`removed_from_index=true`). Both actions clear the Document Q&A conversation so prior citations cannot linger.
- The question box clears as soon as a request enters the pending flow.
- While a reply is pending, Ask is locked to prevent duplicate concurrent submissions; the question box stays editable so the next question can be drafted.
- Loading text is shown in the transcript; controls recover after success and error.

## Reproduce tests

From the repository root on the RunPod Pod, use the same Python as the isolated parsers (`/tmp/vllm-clean-env/bin/python`) and the pinned wheels extracted to `/tmp/rag-deps`. Do **not** run the RAG suite with bare `python3` and `PYTHONPATH=rag` only — that omits `pypdf` / `openpyxl` and fails the PDF/XLSX loader tests.

```bash
PYTHON=/tmp/vllm-clean-env/bin/python
$PYTHON -m py_compile web/server.py web/test_server.py api/local_gateway.py api/test_rag_conversation.py rag/document_loaders.py
$PYTHON -m unittest discover -s web -v
$PYTHON -m unittest discover -s api -p 'test_*.py' -v
bash rag/run_parser_tests.sh
```

`rag/run_parser_tests.sh` runs `rag/setup_pdf_support.sh` and `rag/setup_xlsx_support.sh` (checksum-pinned wheels from `/workspace/runtime-setup/rag-wheelhouse` into `/tmp/rag-deps`), verifies versions (`pypdf==6.20.0`, `openpyxl==3.1.5`, `et-xmlfile==2.0.0`, `defusedxml==0.7.1`), then runs `unittest discover -s rag/tests` with `PYTHONPATH=/tmp/rag-deps:<repo>/rag`.

These suites use a fake gateway / in-process helpers. They do not contact the live model for generation, and they do not modify the main gateway or console.

## Known limitations

- Live spreadsheet calculation quality still depends on retrieval hitting the right rows and on the model following the prompt. That requires a live gateway + vLLM check on the Pod.
- Concurrent Document Q&A asks are intentionally serialised (Ask disabled while pending) to avoid mis-ordered transcript updates.
- `/tmp` is not durable. Persist recovery snapshots under `/workspace`.
- **Deferred:** advanced manual-guided reasoning across local-authority fee frameworks (operations-manual Process E / framework-tab navigation combined with Fee-to-LA worksheet LA lists and age-band rates). Not in the Document Q&A/recovery milestone; do not treat as shipped.

## Safe test-console deploy (port 8082)

See `web/README.md` and the consolidated command in the commit notes / agent report. Do not restart the main gateway at `:8010` or the main console unless explicitly approved. A separate test gateway on `:8012` plus web console on `:8082` keeps the live main services untouched.

## Roll back the test deployment

1. Stop only the test PIDs if present: `/tmp/web-console-8082.pid` and `/tmp/platform-gateway-8082.pid`.
2. Leave `/tmp/platform-gateway-runtime`, `/tmp/AI-PLAYBOOK`, vLLM, and the main console alone.
3. Restore the previous test checkout commit inside `/tmp/AI-PLAYBOOK-upload-test` with `git checkout <previous-sha>`, or extract the previous dated tarball from `/workspace/runtime-setup/web-console-backups/`.
