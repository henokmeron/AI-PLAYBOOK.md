# Issue #1 safe-repo handover — 2026-10-13

## Git state (before this commit’s push)
- Branch: `feature/qwen3.5-27b-integration`
- HEAD after sync: `2b319cb19178956ed6bb9aeef6fbe0b5251f3bc6` (includes `AUTONOMOUS_WORK_QUEUE.md`)
- Working tree: only untracked `ops/_*` probes and `__pycache__/` (left untracked)

## Consistency checks
- Model revision `fc05daec18b0a78c049392ed2e771dde82bdf654` aligned across registry, download/start scripts, docs, smoke script.
- Ports `:8002` / `:8013` / `:8083` aligned; Gemma remains `production` in `models/registry.yaml`.
- `ops/start-qwen-isolated.sh` refuses concurrent start when `:8000` is healthy or GPU used memory exceeds threshold.

## Tests
```text
python -m unittest models.tests.test_registry_loader api.test_rag_conversation \
  rag.tests.test_rag_engine rag.tests.test_document_loaders rag.tests.test_document_library
```
- Result: **Ran 69 tests … OK** (exit code 0)

## Live checks
Not run (no billable Pod; prior balance negative; SSH refused).

## Snapshot
Not created (`/workspace` inaccessible without running Pod).
