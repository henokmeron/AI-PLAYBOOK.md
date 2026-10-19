# AI Operations Director

The Director is an on-demand status report inside the existing Operations Centre. It does not start the model, does not call Microsoft, and does not run a scheduler.

## What it does

- Reads fresh health probes and stored events.
- Labels each area **HEALTHY**, **DEGRADED**, **UNKNOWN**, or **NOT CONFIGURED**.
- Lists facts with timestamps and event or probe evidence.
- Leaves hypotheses empty. It does not invent an explanation.
- Recommends next checks. It does **not** perform them (`executed` is always false).
- Appends one `director.report` audit event. It cannot delete or rewrite history.

A failed probe is **DEGRADED** or **UNKNOWN**. It is never described as healthy.

## What it cannot do

The allowlist is read-only Operations Centre tools: overview, health, event search, alerts, and incident reports.

It has no shell, no arbitrary Python, no SQL, no secret-reading tool, and no way to disable monitoring, grant permissions, change security policy, or skip approvals.

The event hash chain only detects some edits to the local file. A person with access to the host can replace the file. That is not tamper-proof storage. There is no external log export yet.

## How to run it (beginner)

From the repository root, with Python 3.11 or newer:

```bash
python -m ops_centre.director
```

Expected: one JSON document. On a laptop where Qwen, the gateway, and the console are not running, `model`, `gateway`, and `console` should be **DEGRADED** or **UNKNOWN**. That result is correct. Do not treat it as a live Pod check.

Console route, only after the console process is running and an operator is signed in:

`GET /api/ops/director`

The caller needs the `ops:view` permission. The gateway key stays on the server. The report includes `operator_auth`: **NOT CONFIGURED** when `operators.json` is missing, **DEGRADED** when no active administrator is present, and **HEALTHY** only when at least one active administrator is provisioned. The report does not include password hashes.

## Scheduling

There is no cron or job runner in this repository. Do not assume a report runs by itself. The missing piece is a separate scheduled runner that calls `build_report` and stores the JSON. Until that exists, run the command above when you want a report.

## Operator sign-in

Named operator login is **not in this `main` snapshot**. It is on GitHub pull request 4 (`cursor/operator-auth-phase0-787e`) and was not merged or deployed from this session. Until that code is running, anyone who can reach the console port can call ops routes, including this report.
