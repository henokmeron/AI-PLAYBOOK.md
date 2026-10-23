# Remote work gate fix (Endpoint, 2026-10-24)

Base: main `c10719c7`. Files: `integrations/remote_work.py`, `integrations/tests/test_remote_work.py`, `web/test_remote_work_http.py` (test only, added to scope by the Director), this note.

## Changes
- The operator who raised an order can no longer approve it (case-insensitive match). The order stays `pending_approval` and has no approval.
- Live execution now needs `REMOTE_IT_WORK_LIVE=1` even when a runner is injected. Without it, an approved live call is refused with "live execution is disabled" and the runner is not called.
- The delete-plan test uses a Windows-shaped target when it runs off Windows. It still proves the real temp file is untouched.
- In tests, real OS commands are blocked, so only injected fakes can run.

## Not changed
- No action was added, widened or switched on. Creating, disabling or deleting user accounts, deleting files, clearing print queues, download and install all remain not approved by the Founder.
- `LIVE_REPAIR_ENABLED`, `REMOTE_IT_WORK_LIVE` and `repair_authority` stay off. `remote_control` stays false.
- `web/server.py` was not edited. The only `web/` change is the test file: a second operator approves, and `admin` approving its own order gets 403 `refused`.
- Download, install and the `/api/remote-work/*` routes are not approved by the Founder; this change does not use or switch them on.

## Evidence
- `python3 -m unittest web.test_remote_work_http integrations.tests.test_remote_work integrations.tests.test_endpoint`: 55 run, OK (2 skipped), on Linux.
- `python3 -m unittest discover -t . -s .`: 474 run, OK (10 skipped). `web/` discover: 66 run, OK.
- Nothing was run on Windows. Live behaviour is UNVERIFIED.

Production NO-GO.
