# Agent live smoke test against Qwen: 2026-10-14

Result: **VERIFIED**. One calculator task completed through the live gateway with Qwen3.5-27B.

## Setup

- Code: `agents/` from commit `de40330`, copied to the Pod scratch dir `/tmp/agentsmoke`
  (CRLF converted with `/tmp/fresh/_lfconvert.py`). Live services were not restarted or modified.
- Endpoint: existing live gateway `http://127.0.0.1:8010/v1` (upstream Qwen vLLM `:8002`).
  Gemma was not loaded.
- Key: read in-process from `/tmp/platform-gateway.key` (never printed; registered with the trace
  redactor).
- Interpreter: Pod `/usr/bin/python3` (3.12.3), standard library only.

## Command

```
cd /tmp/agentsmoke && timeout 300 /usr/bin/python3 -m agents.live_smoke \
  --gateway http://127.0.0.1:8010/v1 --key-file /tmp/platform-gateway.key --model qwen3.5-27b
```

## Output (verbatim; contains no secrets)

```json
{
  "state": "final",
  "answer": "The cost for 7 days is 696.486.",
  "failure": null,
  "usage": {
    "iterations": 2,
    "tool_calls": 1,
    "total_tokens": 868,
    "elapsed_seconds": 1.3625525049865246,
    "consecutive_errors": 0,
    "parse_failures": 0,
    "output_validation_failures": 0
  },
  "events": [
    "task_created",
    "model_reply",
    "tool_requested",
    "tool_result",
    "model_reply",
    "task_final"
  ]
}
EXIT=0
```

## What this verifies

- Qwen3.5-27B, behind the gateway's default chat path, followed the JSON action protocol on the
  first try (`parse_failures: 0`). It chose the `calculator` tool with valid arguments, read the
  observation, and finished with the exact Decimal result `696.486` (99.498 × 7).
- `OpenAICompatibleClient` works against the live gateway: bearer auth, model id selection via the
  registry, `usage` token accounting, no proxy and no redirects.
- The cost was 2 model calls and 868 total tokens (prompt + completion, as reported by vLLM), in about 1.4 s.

## Not covered by this run

- Document tools (`document_search`, `document_qa`, `read_document`, `table_analysis`) against
  live data, approval pauses with a live model, and longer multi-step tasks. These are covered by
  local unit tests with a scripted model only.
- This run doesn't show whether Qwen respects injected instructions inside tool results; that needs
  an adversarial evaluation set (security review M-4).
