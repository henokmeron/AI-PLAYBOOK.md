# Power Automate

Live Power Automate is **NOT TESTED**. This checkout has no webhook URL and does not call Microsoft.

## Boundary

`integrations/automation.py` stores a durable task. A sensitive action, including `power_automate.run`, stays at `awaiting_approval` until a person approves it. The same idempotency key returns the existing task and does not run the action again. A non-idempotent failure is not retried. An idempotent failure may be retried up to three attempts.

`POWER_AUTOMATE_WEBHOOK_URL` is the only configuration value. Leave it unset. When it is unset, an approved `power_automate.run` task is recorded as `not_tested` and no HTTP request is made. Setting the variable does not by itself prove a flow ran. A live run still needs a least-privilege webhook, a recorded HTTP status, and a person confirming the flow. None of that has been done.

Do not put a webhook URL, a signature secret, or a token in git or in a task payload.
