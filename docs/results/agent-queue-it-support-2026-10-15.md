# Agent queue + IT support playbook

Date: 2026-10-15.

## Built (local)

| Piece | Behaviour |
| --- | --- |
| Serial queue | Second async `AgentDesk.start(wait=False)` returns `execution=queued` until the active task ends |
| Cancel queued | Operator cancel removes a queued task without running the model |
| IT playbook | Helpdesk-like goals add playbook text + required incident `output` schema |
| History path | Console prefers `/workspace/agent-task-history` when `/workspace` is writable |
| UI | Agent page shows tool results, verification checks, errors, and Queued status |
| Live smoke script | `python3 -m agents.live_async_smoke` (needs running console) |

## Tests (local)

```text
python -m unittest discover -s agents/tests -t .   # 95 OK
python -m unittest web.test_server -v              # 23 OK
```

## Live Pod

| Item | Result |
| --- | --- |
| Pod `vx4oe3oyfsqnz8` | Still present, **STOPPED**, volume attached |
| Start | **BLOCKED** — RunPod: “Your Pod's GPUs are no longer available.” |
| Migrate | **Not used** (creates a new Pod machine; needs owner approval) |
| Deploy / live smoke | **NOT TESTED** this session |

## Next step

Approve RunPod migrate for this Pod (keep Global Volume) **or** wait and Start when the A100 is free again. Then restore with `START.sh`, deploy this tip, run live Agent smoke.
