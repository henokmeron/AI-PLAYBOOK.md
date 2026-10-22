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

## Operator task types

The Agent page can name a task type. The runtime allowlist follows that type.

| Task type | What it may do | What was run here |
| --- | --- | --- |
| General knowledge | Answer from the model, or call `calculator` and `search_documents` when those tools are registered | Mock-tested with a scripted model. A final answer cannot claim a tool that did not return a result. |
| IT helpdesk | Existing helpdesk tools, including approval for local remediation | Mock-tested. The helpdesk audit records the tool name and the approval decision. It does not store file contents or tokens. |
| Windows repair | Registered read-only collectors, plus an approval record for an elevated procedure | Read-only collectors stay as they were. Privileged repair still needs a second approver and does not run on this PC. Firewall disable, driver install, and credential collection are refused. |
| Mac troubleshooting | Documented disk, network, and crash-report checks | **NOT TESTED** on a live Mac. Tests use fixtures. This host is Windows. There is no remote Mac agent binary. |
| Microsoft 365 documents | Catalog reads, plus `m365_upload_file`, `m365_update_file`, and `m365_delete_file` when those catalog writes are present | Those writes pause for a second approver and call the catalog only. A write name that is not in the catalog returns `not-approved`. Nothing is shelled out. The audit record stores the tool name and the approval decision, not the file contents. |

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
