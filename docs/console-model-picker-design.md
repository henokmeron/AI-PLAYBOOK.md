# Console model picker — design only (not implemented)

**Status:** inspected and designed. **Not shipped** to production/main console.  
**Constraint:** do not change `production` default or main `:8080` without approval.

## Current behaviour (verified by code inspection)

- `web/server.py` injects a single `PLATFORM_MODEL_ID` into every `/api/chat` request.
- The browser UI (`web/static/app.js`) shows that configured model id in status; there is no user-facing model `<select>`.
- Document Q&A can proceed when model id is missing on the web server, but chat refuses with 503 if unset.
- Gateway already supports explicit model ids + `/v1/platform/models` catalog (with `runtime_loaded`, eligibility, listen ports) and returns **409** on cross-runtime mismatch.

## Smallest safe implementation (when approved)

1. **Isolated console `:8083` first** (never main `:8080` initially).
2. Add authenticated proxy route e.g. `GET /api/platform/models` → gateway `GET /v1/platform/models`.
3. UI: dropdown populated from catalog; disable options with `selection_eligible=false` or `runtime_loaded=false`.
4. Chat payload: send selected registry id (`qwen3.5-27b` / `gemma-4-31b-it`) instead of only server env model id.
5. Surface gateway `platform_selection` / 409 errors in the UI without leaking secrets.
6. Keep server-side default = env `PLATFORM_MODEL_ID` when the user has not chosen.
7. Tests in `web/test_server.py` for proxy + validation; no weight paths in HTML/JS.

## Explicitly out of scope until approved

- Changing `models/registry.yaml` `production:`
- Auto-switching GPU processes from the browser
- Cost-based routing
- Main console `:8080` cutover

## Approval needed before coding

Operator approval to implement the picker on **isolated `:8083` only**.
