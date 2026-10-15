# IT Helpdesk (Agent desk)

Status: **implemented in source, mock-tested.** Live Qwen helpdesk run: **NOT TESTED** on this commit until the console is redeployed on a running Pod.

## What it does

The existing Agent page is the IT Helpdesk. A user submits an issue; the agent can:

1. Ask for missing facts (`action: ask`)
2. Classify the issue (`classify_it_issue`)
3. Search the document library (`search_documents`)
4. Check local platform health and run allowlisted diagnostics
5. Pause for approval before any local remediation
6. Verify after changes
7. Return an incident report (`incident_report` in the task view)

## Tools (local, no unrestricted shell)

| Tool | Effect | Notes |
| --- | --- | --- |
| `classify_it_issue` | read | Category, severity, desired outcome |
| `check_platform_health` | read | Loopback Qwen / gateway / console probes |
| `read_approved_log` | read | Allowlisted log names only; secrets redacted |
| `run_safe_diagnostic` | read | `local_disk_space`, `platform_ports`, `python_runtime`, `temp_cache` |
| `apply_safe_remediation` | consequential | Requires approval: `clear_temp_cache`, `set_maintenance_flag`, `clear_maintenance_flag` |
| `compose_incident_report` | read | Assembles report fields before `final` |

Microsoft 365 mail and enrolled-device diagnostics remain separate catalog tools. They stay hidden until connected. No Entra app is created by this work. No remote shell or password reset tool exists.

## UI

- Nav label: **IT Helpdesk**
- Live status, tool activity, cancel, history (unchanged async desk)
- Approval panel shows what / why / system / risks / verification plan
- Incident report panel when `final` output matches the incident schema

## Tests

```
python -m unittest agents.tests.test_helpdesk agents.tests.test_it_support agents.tests.test_workspace
```

All mocked (scripted model + fake health probes). Not a live Graph or live Qwen check.

## Blockers for “live business integrations”

- Microsoft Entra application id not configured (`MICROSOFT_CLIENT_ID` unset)
- Enrolled endpoint worker optional; no device until the operator enrols one
- Remote control / password reset deliberately out of scope
