# Full RAG → authenticated gateway → Gemma test — 2026-10-11

## Outcome

**PASS:** The user's terminal screenshot confirms a RAG question was processed through the authenticated local gateway and answered by Gemma 4 31B-it.

- Query: "How many business days do employees have to submit expense receipts?"
- Input documents: 2 fictional Markdown documents on the Global Volume.
- Retrieval: `expenses-policy.md` first (BM25 score 5.363), `employee-handbook.md` second (0.638).
- Gateway: `http://127.0.0.1:8010/v1`.
- Model ID: `/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it`.
- Client used `--api-key-file /tmp/platform-gateway.key`; key value was not printed or committed.
- Model answer: "Employees must submit expense claims with receipts within 10 business days of the expense [Source 1]."
- Reported model request latency: 0.57 s for this single request (not a throughput benchmark).

## What this confirms

The document Q&A client supports bearer authentication and successfully calls the working gateway instead of addressing vLLM directly. Retrieval, prompting, gateway authentication and model generation completed end to end for this example.

## Limitations

This is still a command-line prototype. The gateway binds to loopback only and uses one temporary shared key. There is no external-client deployment, tenant isolation, user identity, durable audit logging, managed secret rotation, or production security hardening. The BM25 minimum score of 2.30 is calibrated only for the two-file fictional demo corpus. Do not expose port 8010 publicly.

## Next milestone

Move this CLI path behind a single authenticated HTTP endpoint, such as `POST /v1/rag/ask`, so business apps can submit a question and receive an answer plus source metadata without separately running a script. Keep the current vLLM server unchanged while building this API integration.
