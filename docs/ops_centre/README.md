# Security & Operations Centre

Beginner entry point: **`docs/ops_centre/GAP_AND_ARCHITECTURE.md`**.

## What you get in the console

New sidebar page: **Operations** (`#ops`).

- Executive overview with fresh probes
- Service health (gateway live/ready, Qwen, console, disk)
- Alerts with acknowledge / open-incident
- Incidents (security/ops — separate from IT Helpdesk tickets)
- Searchable activity timeline
- Detection coverage text and event hash-chain integrity

## Local data

| Env | Default |
| --- | --- |
| `OPS_CENTRE_DIR` | `/workspace/ops-centre` if writable, else `/tmp/ops-centre` |

Files: `events.jsonl`, `alerts.json`, `incidents.json`.

## AI Ops tools (agent)

When the console wires `OpsCentre` into `AgentDesk`, IT Helpdesk / agent tasks can call:

`ops_get_overview`, `ops_get_health`, `ops_search_events`, `ops_list_alerts`, `ops_get_alert`, `ops_get_incident_report`, `ops_compose_investigation`

These are allowlisted, mostly read-only. They do **not** disable monitoring or run a shell.

## Honest limits

- Does not start RunPod or Qwen.
- Does not claim complete attack detection.
- Hash chain ≠ forensic WORM storage.
- Console still has no login (known baseline risk); keep loopback + tunnel.
