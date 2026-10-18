# Live IT Helpdesk vs Qwen — 2026-10-15

**Label: VERIFIED (live Qwen on Pod `4lvr54b0wmkz6c`)**  
Deployed console tip: **`c069674`** (contains helpdesk `37b6155` + protocol/budget fixes).  
Not a mock test. Model: `qwen3.5-27b` via gateway `:8010` / vLLM `:8002`.

## Fixes required during this live pass

1. **Protocol shortcut** — Qwen often emits `{"action":"classify_it_issue",...}` instead of `{"action":"tool","tool":"classify_it_issue",...}`. Normalized in `agents/protocol.py` (`7b61967`).
2. **Token budget** — full approve → verify → report exhausted 16k tokens. IT budget raised to 48k; HTML health probes compacted (`c069674`).

## Evidence

| Check | Result |
| --- | --- |
| `python3 -m agents.live_async_smoke` | **PASS** FAILS=0 (calculator / history / cancel) |
| `ops/_live_helpdesk_smoke.py` | **PASS** FAILS=0 — tools used, incident report, history |
| Approval smoke (seeded `/tmp/ai-helpdesk-cache`) | **PASS** FAILS=0 — `apply_safe_remediation` approved, cache cleared, incident |
| Web UI (`http://127.0.0.1:18080/#agent` tunnel) | **PASS** — submit → live tool progress → Approve → completed / outcome resolved |

### UI task (live)

- Task id: `9dc32d7f8a774dfeb43573eeab8dc41a`
- Tools: `classify_it_issue`, `run_safe_diagnostic`, `apply_safe_remediation` (approved), re-check diagnostic, `check_platform_health`, `compose_incident_report`
- Harmless only: cleared local `/tmp/ai-helpdesk-cache/ui-stale.tmp`. No customer systems.

## Not claimed

- Microsoft 365 / Entra still **not configured**
- Enrolled-device remote control **not available**
- Connector cards in the UI may still say “mock-tested” for helpdesk tools; that static catalog label was **not** updated in this pass — live evidence above overrides it
