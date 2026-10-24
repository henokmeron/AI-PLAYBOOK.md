# Session playbook — 2026-10-24

Session record for the remote IT work discussed on 24 October 2026. It exists so the next agent can continue without this chat. It does not replace `PLAYBOOK.md`, `docs/coordination/AGENT_HANDOFF.md`, or `docs/coordination/TRANSFER_TO_NEXT_AGENT.md`. Nothing here weakens the acceptance board. Production stays NO-GO. A push is not a deploy.

Checked out from `origin/main` at `7d6a3b24ea72dbd74bc773dcb62be7fd11dca754` ("Merge the repeatable device registration path into main."). Facts below are either that git history or statements from the owner. Branches with no commit of their own are marked in progress.

## What already existed

The repository is `henokmeron/AI-PLAYBOOK.md`. There is no top-level `README.md` and no `guides/` folder.

`PLAYBOOK.md` is the LLM build playbook. It states the commercial platform purpose, model and infrastructure strategy, compliance, and a change log through 2026-10-22. Its latest product notes cover the IT Helpdesk, the agent execution loop, and the RunPod-first Qwen release. It does not record this session's registration script, device monitor dashboard, multi-agent lanes, or mail lane.

`docs/coordination/TRANSFER_TO_NEXT_AGENT.md` (updated 2026-10-23 22:40 UK) is the architecture handoff for the next chat: pod and volume layout, the three machines, the Office PC check-in, and production NO-GO. `docs/coordination/AGENT_HANDOFF.md` CURRENT (updated 2026-10-24 00:26 UK) assigns a Windows remote-support backlog and keeps production NO-GO. Its log records later landings, including the TLS device gateway. `docs/AGENT_HANDOFF.md` is the older 2026-10-22 handoff. The coordination file says live work follows the coordination handoff. Repeat the current board from evidence. Leave the older score in that 2026-10-22 file alone.

Those files do not capture today's full session. Registration on `main` is only the script and `docs/windows-repair/register-device.md`.

## Goal

The owner wants remote IT control of enrolled Windows laptops, the way an IT engineer would work: repair, setup, onboarding, offboarding, monitoring, install, download, delete, and print. Microsoft 365 and mail sign-in are outside that control path. Device registration is the control path. Setup must be easy and replicable. A one-time enrolment code is not committed.

## Registration setup (on origin/main)

`83176c824111ef327dbfeb6fa8c8df7d581367f9` adds `scripts/register-device.ps1`, `docs/windows-repair/register-device.md`, and a short note in `docs/windows-repair/endpoint-agent.md`. Merge `7d6a3b24ea72dbd74bc773dcb62be7fd11dca754` is on `origin/main`.

The script refuses hostname `BANYA-FAMILY-PL`. It also refuses the display names `Office PC`, `BANYA-FAMILY-PL`, `not-the-second-endpoint`, and device id `bead5785f3674aaeb92c189f8c1b5b8c`. The code stays in memory. The script does not write the enrolment code into a file. The commands and the loopback console are in `docs/windows-repair/register-device.md`.

The console sidebar has no Register item. The items are Chat, Document Q&A, IT Helpdesk, Windows repair, Operations, and System Status. The registration control is IT Helpdesk, then Enrolled computers, then Create an enrolment code. Windows repair, Enrol an endpoint, is a different credential for signed jobs. Use the IT Helpdesk button for this registration path.

This PC, hostname `BANYA-FAMILY-PL`, cannot enrol itself. The other Windows computer runs `scripts/register-device.ps1`.

## Device monitor dashboard (in progress)

Branch `feature/device-monitor-dashboard` is a local worktree at `C:\Users\henok\src\AI-PLAYBOOK-device-dashboard`. The owner said agent `b563302c` is building it. It is not merged. `git ls-remote` has no such branch on origin. Local HEAD is `7d6a3b24ea72dbd74bc773dcb62be7fd11dca754`, the same commit as `origin/main`, with a clean worktree and no commits ahead. No dashboard commit is recorded here.

The owner asked the dashboard to show a device list and per-device detail from stored check-ins only. Requested categories:

- Last check-in.
- Nine checks: disk `win.storage.space`, services `win.services.inspect`, Windows updates `win.update.inspect`, device inventory `hw.devices.inventory`, printers `print.diagnose`, network `net.diagnose`, events `win.events.recurring`, startup `win.startup.inspect`, hardware specs `hw.identity.inspect`.
- Failed checks highlighted, and an overall health reading.
- Antivirus, sync, last seen and online, network quality, downloading, uptime, patch and update events, and security posture.
- Disk-space trend, failed logins and security events, backup status, pending reboot, certificate expiry, and thermal or battery health.

Missing data displays as not reported. A missing field is never shown as healthy. These categories are requested. They are not a built dashboard in this commit.

## Multi-agent lanes

Disjoint git worktrees are what keeps the lanes from editing the same checkout.

`feature/agent-lane-mail` is `42dff505ad1c0b0c5817d61b4f1c807236dd82da` on origin and in worktree `C:\Users\henok\src\AI-PLAYBOOK-lane-mail`. That commit is not an ancestor of `origin/main`. It adds one dated note to `docs/coordination/mail-positive-match-waiting.md`: the lane can run beside other lanes, and it does not send mail, search the mailbox, add Microsoft scopes, or change devices or printers. The positive-match gate still waits for one harmless phrase from the owner.

`feature/parallel-agent-lanes` is a local worktree at `C:\Users\henok\src\AI-PLAYBOOK-parallel-lanes`. It is not on origin. HEAD is still `7d6a3b24ea72dbd74bc773dcb62be7fd11dca754`, with untracked `docs/coordination/parallel-agent-lanes.md` and `scripts/new-agent-worktree.ps1`. That lane is in progress. No commit SHA is recorded.

Production stays NO-GO until the written acceptance gates pass. Leave `ops/acceptance_board.py` unchanged.

## Repair jobs and the remote work channel

These commits are on `origin/main`:

- `b24b02bae8c0eb5097ea7bbe150737de40e8466e` merges the approval-gated Windows service and printer fixes. `windows_repair/approval.py` names `win.service.restart_failed` and `print.queue.clear_spool`.
- `c2ccd5d323710f8c47826a209a6e7683281a7237` merges the gated remote IT work channel.
- `c10719c7a7df187de464e62812dccfd5e4554a65` merges the finished remote IT actions.
- `b1a4217619842f922e9a596cf45e14150faea5c1` adds a console session so an enrolled laptop can run one approved IT job.

`integrations/remote_work.py` on this main tip has eight action ids: `monitor.heartbeat`, `repair.service.restart`, `repair.printer.clear_queue`, `setup.onboard.local_user`, `setup.offboard.local_user`, `change.download`, `change.install`, and `change.delete`. The module does not open a shell. The owner stated there is no open remote shell. Creating an order leaves it `pending_approval`. Approval is a separate step, and the operator who raised the order cannot approve it.

`change.download` and `change.install` are plan-only for the default live runner. An injected runner is what the module allows to finish them after the order is claimed. The owner said download and install on the live Office PC worker still returned plan-only. No live repair is claimed.

`feature/approved-repair-jobs` is not on origin and does not appear in `git branch -a`. The owner said that branch was wiring the safe-fix actions into the live remote runner, and making `change.install` and `change.delete` executable only through an injected runner with the existing gates. That work is in progress. No SHA is recorded.

## Still open

- Production stays NO-GO until the written acceptance gates pass.
- The owner stated that Office PC device `bead5785f3674aaeb92c189f8c1b5b8c` (display name Office PC, tenant `local-console`) is the only enrolled device. The same id is the device the registration script refuses to reuse. Its live worker treats download and install as plan-only, so it cannot fetch installers from the web. The owner stated that no HP Smart install and no HP driver download succeeded on that PC. The owner stated the printers there are virtual: OneNote, Microsoft Print to PDF, and Fax. Leave that queue alone.
- `BANYA-FAMILY-PL` stays the development PC. The other Windows computer runs the registration script.
- The owner stated that Qwen and the gateway were left running. The coordination handoff says to leave them running.
- A push updates GitHub. It does not deploy the pod or reload the console.
- Owner stated 2026-10-24 that the second Windows PC is ready, so “no second machine available” is no longer a remaining non-M365 blocker. The live second-endpoint gate is still open: that different physical PC still has to enrol, run the worker, and produce a live report the board accepts. This record does not add `second_endpoint_worker_ok`.

## Discussed next steps

The owner discussed client packaging: the monitoring dashboard, per-device pricing, and a simple onboarding flow. Those are discussed next steps. They are not built product in this record.

## Relayed session context — local device-dashboard look

The caller relayed what another agent said. That other agent's instruction was to open `C:\Users\playbook\device-dashboard\web\statistic\device-dash-manager.html` from the work tree for a local look. After that, because the page stays empty, the other agent said the reason is that it is registered via API device application after this branch is merged, and to look for console service. Those words are the caller's relay, not a claim that that path or filename exists.

Checked read-only in `C:\Users\henok\src\AI-PLAYBOOK-device-dashboard` from this docs job: there is no `web\statistic\` folder and no `device-dash-manager.html`. The page that exists is `C:\Users\henok\src\AI-PLAYBOOK-device-dashboard\web\static\device-monitor.html`. That file, with `web\static\device-monitor.js`, reads enrolled devices from `/api/devices` when the console serves the page. Opening the HTML file alone from the worktree has no console service, so the list stays empty. The live console shows this page only after `feature/device-monitor-dashboard` is merged. That branch is not merged. This record does not claim the dashboard is live on the console.

## 2026-10-24 — Second Windows PC ready (availability only)

Owner stated 2026-10-24 that the second Windows PC is ready. This removes the “no second machine available” blocker from the remaining non-M365 work list.

It does not record `second_endpoint_worker_ok`. The gate still needs that different physical PC to enrol (IT Helpdesk → Create an enrolment code; `scripts/register-device.ps1`; not Windows repair → Enrol an endpoint), run the worker, and produce a live report that the board accepts. `BANYA-FAMILY-PL` cannot enrol itself if that is this Cursor PC.

Office PC `bead5785` remains the only enrolled device until a new enrolment is stored. Production stays NO-GO. Microsoft 365 stays paused.
