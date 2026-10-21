# Named-operator authentication (Phase 0)

Local console authentication for individually identified operators. This document describes the **source implementation**. It does not claim the change is deployed, live-tested on the Pod, or that Microsoft Entra sign-in replaces these local accounts.

## Purpose

The loopback web console previously relied on network isolation (loopback bind / SSH tunnel) and a server-side gateway bearer key. Anyone who could open the console could use every privileged browser API. Phase 0 adds:

- Named operator accounts (hashed passwords, no plaintext storage)
- Roles: `admin`, `operator`, `viewer`
- HttpOnly session cookies with idle and absolute expiry
- CSRF protection on mutating requests
- Host / Origin checks
- Fail-closed behaviour when no operators are provisioned
- Audit events through Ops Centre (`component=auth`)

The gateway bearer key remains **server-side only** and is separate from operator login.

## Provisioning

Use the local CLI (passwords from `OPERATOR_PASSWORD` or stdin — never argv):

```bash
export OPERATOR_AUTH_DIR=/tmp/console-operators
python3 scripts/provision_console_operator.py create-admin --username alice
```

Additional accounts (requires admin credentials in the environment for this CLI only):

```bash
export OPERATOR_ADMIN_USERNAME=alice
export OPERATOR_ADMIN_PASSWORD='…'
python3 scripts/provision_console_operator.py add --username bob --role operator
python3 scripts/provision_console_operator.py list
python3 scripts/provision_console_operator.py disable --username bob
python3 scripts/provision_console_operator.py set-role --username bob --role viewer
```

Administrators can also manage accounts through authenticated console APIs under `/api/auth/operators*`.

## Roles and permissions

| Permission | viewer | operator | admin |
| --- | --- | --- | --- |
| `ops:view` | yes | yes | yes |
| `ops:alert_write` | | yes | yes |
| `ops:incident_write` | | yes | yes |
| `agent:view` | yes | yes | yes |
| `agent:start` | | yes | yes |
| `agent:approve` | | yes | yes |
| `chat:use` | yes | yes | yes |
| `docs:use` | yes | yes | yes |
| `connectors:view` | yes | yes | yes |
| `connectors:manage` | | yes | yes |
| `admin:operators` | | | yes |

If `OPERATOR_AUTH_DIR` has no active operators, privileged browser APIs return **503** (fail-closed).

## Sessions

| Item | Behaviour |
| --- | --- |
| Cookie | `console_session` — `HttpOnly`, `SameSite=Strict`, `Path=/` |
| Secure flag | Set when `WEB_COOKIE_SECURE=true` (use behind HTTPS tunnels if required) |
| Idle expiry | 8 hours (sliding on activity) |
| Absolute expiry | 24 hours |
| CSRF | `X-CSRF-Token` header required on mutating authenticated requests |
| Rotation | Login issues a new session; `POST /api/auth/rotate` replaces id + CSRF |
| Logout | `POST /api/auth/logout` clears the cookie and revokes the server session |

Password hashing uses stdlib **scrypt** (no third-party crypto dependency).

## Environment variables

| Variable | Purpose |
| --- | --- |
| `OPERATOR_AUTH_DIR` | Directory for `operators.json` / `sessions.json`. Default is `/tmp/console-operators` on Linux and `%LOCALAPPDATA%\AI-PLAYBOOK\console-operators` on Windows. |
| `WEB_COOKIE_SECURE` | When `true`, session cookies include the `Secure` attribute |
| Existing `WEB_*` / `PLATFORM_*` | Unchanged loopback and gateway settings |

## Public vs protected routes

Always reachable without an operator session (still Host-restricted to loopback names):

- Static UI assets
- `GET /api/status`
- `GET /api/auth/status`
- `POST /api/auth/login`
- `GET /api/microsoft/callback` (OAuth return; validates `state` / PKCE server-side)
- `POST /api/devices/enroll` and `POST /api/devices/report` (device secret / enrolment-code auth; loopback client only)

All other browser APIs require a valid session and the matching permission.

### Device enroll / report protections

| Control | Behaviour |
| --- | --- |
| Client | Must be loopback (`127.0.0.1` / `::1`) |
| Enroll auth | One-time high-entropy enrolment code + device secret (≥32 chars); secret stored hashed |
| Report auth | Bearer device secret; secret never returned in public device listings |
| Abuse limits | Failed enroll attempts capped in-process (20 / 15 min); reports min gap 15 s |
| Scope | Fixed diagnostic schema only; no command / path / credential fields |

## Risks and limits

- This is **not** Entra ID / Microsoft 365 SSO. Browser Microsoft sign-in for Graph remains a separate connector flow.
- File-backed sessions under `OPERATOR_AUTH_DIR` are only as safe as the host filesystem and process isolation.
- Loopback / tunnel exposure mistakes (for example a public proxy to `:8080`) remain a deployment risk; operator auth is defence in depth, not a substitute for correct binding.
- Rate limiting is in-process per console instance.
- Unknown and disabled usernames return the same sign-in error. The check still runs scrypt so a missing name is not cheaper than a wrong password.
- On Windows the default directory is inside the user profile (`%LOCALAPPDATA%\AI-PLAYBOOK\console-operators`). POSIX mode `0600` is not applied there. Do not point `OPERATOR_AUTH_DIR` at a shared folder.
- Creating another account requires an active administrator. The last active administrator cannot be demoted or disabled.
- Gateway S2S bearer auth (`PLATFORM_API_KEY_FILE`) remains separate from human operator cookies.

## Deploy / rollback notes

1. **Provision first:** create at least one administrator with `scripts/provision_console_operator.py create-admin` into `OPERATOR_AUTH_DIR` **before** any console restart that includes this code (fail-closed otherwise).
2. `ops/release/deploy-console-only.sh` refuses restart when `operators.json` is missing, and passes `OPERATOR_AUTH_DIR` into the new console process. It does not restart Qwen or the gateway. Its default branch is `main`.
3. Default `OPERATOR_AUTH_DIR=/tmp/console-operators` survives console-only reloads on the same Pod session. A Pod stop deletes `/tmp`. `ops/platform_state.py` keeps a checksummed copy of `operators.json` at `/workspace/platform-state/operator-backups/` and restores it onto local disk with mode 0600. Sessions, the gateway key, and the Microsoft token are not in that backup. There is still no default password. See `docs/release/RECOVERY.md`.
4. Rollback: revert to a console build without `require_operator` gates; remove or ignore `OPERATOR_AUTH_DIR`.
