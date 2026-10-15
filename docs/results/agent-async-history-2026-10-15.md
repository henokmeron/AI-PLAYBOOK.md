# Agent async progress and auditable history

Date: 2026-10-15. Built on the verified CUDA-13 Pod stack; no weights or archives changed.

## Feature

| Piece | Behaviour |
| --- | --- |
| Async start | `AgentDesk.start(..., wait=False)` returns immediately with `running=true` |
| Progress | `AgentRunner.on_progress` snapshots the public view on each status change |
| Poll API | `GET /api/agent?task_id=…` |
| History API | `GET /api/agent/history?limit=N` |
| Persist | `TaskHistoryStore` under `AGENT_HISTORY_DIR` (default `/tmp/agent-task-history`) |
| Cancel | Cooperative `CancellationToken` while a background thread is active |
| UI | Agent page polls while working; shows recent tasks; cancel visible when cancellable |

Console POST uses `{ "task": "…", "wait": false }`. Omitting `wait` keeps the previous synchronous behaviour (`wait=true`) for scripts and tests.

## Tests (local)

```text
python -m unittest agents.tests.test_history -v   # 4 OK
python -m unittest discover -s agents/tests -t .  # 90 OK
python -m unittest web.test_server -v             # 23 OK
```

## Live Pod (cheap verify only)

| Item | Result |
| --- | --- |
| Pod | `vx4oe3oyfsqnz8` @ `154.54.102.49:18454` |
| Driver | 580.126.16 |
| `:8002` / `:8010` / `:8080` | HTTP 200 |
| Model | `qwen3.5-27b` |
| Expensive agent/E2E re-run | **Not repeated** (prior `_pod_e2e_verify.py` FAILS:NONE still stands) |

## E2E script scope (reference)

`ops/_pod_e2e_verify.py` hits **real** loopback gateway/console: chat completion, model picker 409 for Gemma, RAG upload/ask/delete. It does **not** exercise the Agent desk, async progress, or task history. No mocks inside that script.

## Non-goals held

- No new paid resources, no Entra, no weight re-download, no volume delete.
- Pod should be **stopped** (not terminated) when idle to limit $1.79/hr spend; Global Volume kept.
