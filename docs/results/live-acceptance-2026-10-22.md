# Live acceptance on A100 `gom4ualdk47qrj` — 2026-10-22

Pod `gom4ualdk47qrj` (`excessive_gray_crocodile`), A100 SXM 80GB, about $1.80/hr. SSH over exposed TCP `root@154.54.102.41 -p 12572` (read from the RunPod Connect panel; the documented `216.81.245.55:25839` refused). The key was not printed. No pod was created, started, stopped, resized, or terminated. H100 `xx9cjogra5vcwl` was not touched. Qwen (vLLM, `:8002`) was not restarted. Nothing under `/workspace` was deleted, overwritten, or newly written.

All times are UTC.

## Summary

| Item | Result |
| --- | --- |
| Published `main` | `d1e766ebc9afec185c328f279949012447417215` (`git ls-remote`, 18:15Z; both feature branches identical) |
| Pod checkout before | `be9cbd2baf08ee1d9f1bbd192982c94575f57aeb`, no tracked edits |
| Pod checkout after | `d1e766ebc9afec185c328f279949012447417215`, fast-forward, no tracked edits |
| vLLM pid | **1826** before and after (started 15:23:09Z) |
| Gateway pid | 12581 (15:48:43Z) → **53074** (18:17:15Z) |
| Console pid | 12593 (15:48:45Z) → **53091** (18:17:17Z) |
| Inference via gateway | **VERIFIED** (HTTP 200, `gateway works`) |
| RAG | 5 of 6 answerable cases **VERIFIED** with citations and matching text. The train-ticket wording **FAILED** (false abstention; also fails on `be9cbd2`). |
| Abstention | 3 of 3 **VERIFIED** |
| Live scripts | `agents.live_smoke` 0, `run_live_platform_smoke` 0, `run_live_rag_regression` 1 (5/6), `agents.live_async_smoke` 1 (403, no operator session) |
| Microsoft | Console loaded the client id from a `/tmp` file. OAuth status `configured=true`, `connected=false`. Browser sign-in start **BLOCKED** by operator login. Mailbox read **NOT VERIFIED**. |

## 1. Inspection (before any change)

- 18:15:52Z `git -C /tmp/AI-PLAYBOOK rev-parse HEAD` → `be9cbd2baf08ee1d9f1bbd192982c94575f57aeb`. `status --porcelain` shows only untracked `__pycache__` directories. The origin URL is `https://github.com/henokmeron/AI-PLAYBOOK.md.git`.
- `ps -eo pid,lstart,args`:
  - 1826, 15:23:09Z: `/tmp/vllm-qwen-env/bin/python /tmp/vllm-qwen-env/bin/vllm serve /workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654 --host 127.0.0.1 --port 8002 --trust-remote-code --language-model-only --reasoning-parser qwen3 --max-model-len 8192 --max-num-seqs …`
  - 12581, 15:48:43Z: `/tmp/vllm-qwen-env/bin/python /tmp/AI-PLAYBOOK/api/local_gateway.py`. Stdout went to `/workspace/platform-diagnostics/first-release/gateway.log`.
  - 12593, 15:48:45Z: `/usr/bin/python3 /tmp/AI-PLAYBOOK/web/server.py`. Stdout went to `/workspace/platform-diagnostics/first-release/console.log`.
  - nginx 82/83 (RunPod proxy), 15:12:19Z.
- `ss -ltnp`: 127.0.0.1:8002 python 1826; 127.0.0.1:8010 python 12581; 127.0.0.1:8080 python3 12593; nginx on 0.0.0.0:3001/7270/7861/8001/8081/9091; jupyter 8888; sshd 22.
- Health: `:8002/v1/models` 200, `:8010/health` 200, `:8080/api/status` 200.
- Gateway env (names; secret values redacted): `PLATFORM_HOST=127.0.0.1`, `PLATFORM_PORT=8010`, `PLATFORM_API_KEY=<redacted>`, `PLATFORM_API_KEY_FILE=/tmp/platform-gateway.key`, `VLLM_UPSTREAM_URL=http://127.0.0.1:8002/v1`, `PLATFORM_MODEL_REGISTRY=/tmp/AI-PLAYBOOK/models/registry.yaml`, `PLATFORM_DEFAULT_MODEL_ID=qwen3.5-27b`, `RAG_DOCS_DIR=/workspace/rag-demo-docs`, `RAG_MANAGED_DOCS_DIR=/workspace/rag-managed-docs`, `PYTHONPATH=/tmp/AI-PLAYBOOK/api:/tmp/AI-PLAYBOOK/models:/tmp/AI-PLAYBOOK/rag:/tmp/rag-deps`, `TMPDIR=/tmp`, `VLLM_RPC_BASE_PATH=/tmp`, `REPO_ROOT=/tmp/AI-PLAYBOOK`, and `LD_LIBRARY_PATH` set to the `/tmp/vllm-qwen-env/.../nvidia/*/lib` list.
- Console env: `WEB_HOST=127.0.0.1`, `WEB_PORT=8080`, `PLATFORM_GATEWAY_URL=http://127.0.0.1:8010`, `PLATFORM_API_KEY_FILE=/tmp/platform-gateway.key`, `PLATFORM_MODEL_ID=qwen3.5-27b`, `OPERATOR_AUTH_DIR=/tmp/console-operators`, `MICROSOFT_CLIENT_ID=` (empty), `MICROSOFT_CLIENT_ID_FILE=` (empty), `MICROSOFT_TENANT=common`, `MICROSOFT_REDIRECT_URI=http://127.0.0.1:18080/api/microsoft/callback`, `MICROSOFT_TOKEN_FILE=<path, not printed>`, `RAG_DOCS_DIR`, and `RAG_MANAGED_DOCS_DIR` as above, plus the same `TMPDIR`, `VLLM_RPC_BASE_PATH`, `REPO_ROOT`, and `LD_LIBRARY_PATH`.
- Launcher: `/workspace/ai-platform-release/START.sh` fast-forwards `/tmp/AI-PLAYBOOK` and then `exec`s `ops/start-first-release.sh --start`. That script starts the gateway as `nohup env PLATFORM_HOST… "$QWEN_ENV/bin/python" "$REPO_ROOT/api/local_gateway.py" >"$DIAG/gateway.log"` and the console as `nohup env WEB_HOST… MICROSOFT_CLIENT_ID_FILE="${MICROSOFT_CLIENT_ID_FILE:-}" MICROSOFT_TENANT="${MICROSOFT_TENANT:-common}" … /usr/bin/python3 "$REPO_ROOT/web/server.py" >"$DIAG/console.log"`. `DIAG` defaults to `/workspace/platform-diagnostics/first-release`.
- Operator store `/tmp/console-operators/operators.json` exists, mode 0600. No `/tmp/microsoft*` files existed.
- Side note: PowerShell stripped quotes from the first `ps | grep` pipeline, so the remote shell ran the bare word `nginx`. That second nginx failed to bind (`still could not bind()`) and exited. Master pid 82 was unchanged. Every later command was sent as a stdin script.

## 2. Deploy to the gateway and console only

- New-dependency check: `git diff be9cbd2 d1e766e` touches `agents/`, `integrations/`, `rag/retrieval_pipeline.py`, and `web/server.py`. `api/` is unchanged. Every added import is stdlib or in-repo. **No new Python dependency.**
- 18:17:14Z `SOURCE_UPDATE_APPROVED=yes bash /tmp/AI-PLAYBOOK/ops/release/update-source-only.sh` printed `source-only be9cbd2baf08ee1d9f1bbd192982c94575f57aeb -> d1e766ebc9afec185c328f279949012447417215` and `acceptance: HEAD matches origin/main`. Fast-forward, 31 files. No tracked edits afterwards. `safe.directory=/tmp/AI-PLAYBOOK` was added to `/root/.gitconfig`.
- Checkout finished at 18:17:15Z. Mtime of the changed files is epoch `1792693035.11`.
- Client id file: `/tmp/microsoft-client-id`, mode `600`, owner root. It holds only the application id and is not in Git.
- Gateway: 18:17:15Z `kill 12581`, confirmed gone, then the launcher's exact `env` list and command started via `setsid nohup`. The inherited `TMPDIR`, `VLLM_RPC_BASE_PATH`, `REPO_ROOT`, and `LD_LIBRARY_PATH` were copied from the old process. Only change: stdout goes to `/tmp/platform-diagnostics/gateway.log` instead of `/workspace/...`, because writing `/workspace` was not allowed for this session. New pid **53074**, `/health` 200 at 18:17:16Z.
- Console: 18:17:16Z `kill 12593`, confirmed gone, then the launcher's command with `MICROSOFT_CLIENT_ID=` (empty), `MICROSOFT_CLIENT_ID_FILE=/tmp/microsoft-client-id`, and `MICROSOFT_TENANT=d595636e-9ef4-4890-b8a7-bde8dd5cab03`. The other variables were unchanged. Stdout goes to `/tmp/platform-diagnostics/console.log`. New pid **53091**, `/api/status` 200 at 18:17:19Z.
- vLLM pid **1826** before (18:17:14Z) and after (18:17:19Z and 18:21:48Z), still started 15:23:09Z.

### Running-revision evidence

- No status endpoint reports a source SHA. `/health` returns `status, upstream, model_count, default_model_id`. `/api/status` returns `ui, gateway_url, …, connection, runpod_verified, detail` and has no SHA field.
- Start epoch from `/proc/PID/stat`: gateway 53074 = `1792693035.43`, console 53091 = `1792693037.08`. Mtime of the checkout files = `1792693035.11`. Both processes started **after** the tip files were written.
- cmdlines are `/tmp/AI-PLAYBOOK/api/local_gateway.py` and `/tmp/AI-PLAYBOOK/web/server.py`. `/tmp/AI-PLAYBOOK` HEAD was `d1e766e…` at 18:21:43Z with 0 tracked edits.
- The tip's behaviour is live. The console's `/api/microsoft/*` code read `MICROSOFT_CLIENT_ID_FILE` (section 4), and the client-id file path is supported only by code on this checkout.
- `/workspace/platform-diagnostics/first-release/{gateway,console}.pid` still say 12581/12593. Those stale files were left as they were, because this session may not write `/workspace`.

## 3. Live acceptance

### Models and completion

| Time | Call | HTTP | Result |
| --- | --- | --- | --- |
| 18:18:43Z | `GET :8002/v1/models` | 200 | one model, root `…/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654` |
| 18:18:43Z | `GET :8010/v1/platform/models` (Bearer) | 200 | registry ids `gemma-4-31b-it, qwen3.5-27b, mistral-large-4, llama-4`; default `qwen3.5-27b` |
| 18:18:43Z | `POST :8010/v1/chat/completions` `Reply with exactly: gateway works` | 200 | `gateway works`, 0.18 s, model `/workspace/models/Qwen3.5-27B/fc05daec…` |

### RAG through the gateway `POST :8010/v1/rag/ask` (top_k 4)

Source rows contain `chunk, file, label, score` and no excerpt text. Grounding was checked two ways. Every quoted span in the answer had to appear in the cited file. The key fact also had to appear in that file (`grep` on the pod).

| Time | Collection | Question | HTTP | Status | Cited | Text check | Answer (short) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 18:18:45Z | demo | By what deadline must staff submit expense receipts? | 200 | answered | expenses-policy.md | `10 business days` in file (1 hit) | within **10 business days** [Source 1] |
| 18:18:46Z | demo | Who must approve an expense claim over 100 pounds? | 200 | answered | expenses-policy.md | `manager` in file (3) | above £100 requires **manager approval** [Source 1] |
| 18:18:48Z | demo | What are the office hours Monday to Friday? | 200 | answered | employee-handbook.md | `09:00`, `17:30` in file | Monday to Friday 09:00 to 17:30 UK time [Source 1] |
| 18:18:48Z | demo | Which class of train ticket should staff book? | 200 | **abstained (FAIL)** | none | n/a | No sufficiently relevant evidence… |
| 18:18:50Z | `global-canary-1791758676` | What does the global volume canary document say? | 200 | answered | global-volume-canary.md | 2/2 quotes found in file | "Persistent storage verification code: GLOBALVOL-58317" … |
| 18:18:52Z | `upload-smoke-test` | What does the platform upload smoke document say? | 200 | answered | platform-upload-smoke.md | quote "Test Record" and `ORCHID-4729` in file | recovery code **ORCHID-4729** [Source 1] |
| 18:18:52Z | demo | What colour is the CEO's private yacht? | 200 | abstained (OK) | none | — | No sufficiently relevant evidence… |
| 18:18:52Z | demo | What is the company's VAT registration number? | 200 | abstained (OK) | none | — | No sufficiently relevant evidence… |
| 18:18:52Z | `upload-smoke-test` | What is the capital of Mongolia's football league champion in 1987? | 200 | abstained (OK) | none | — | The supplied documents do not appear to cover this question. |

The train failure is not caused by this deploy. The policy text is "book rail travel in standard class" and contains no "train" or "ticket". Offline retrieval with the same corpus (file SHA-256 identical to `rag/sample_docs`) gives top BM25 score 0.77 against the 2.30 floor and coverage 0.025, identical on `be9cbd2` and on `d1e766e`. "Which class of rail travel should employees book?" scores 4.661 and is answered on both. This is a vocabulary gap in lexical retrieval.

Managed collections on the volume: `a100-sxm-check`, `complete-release-check`, `manual-e2e-check`, `my-docs`, and `tonight-qwen-check` are empty. `global-canary-1791758676`, `ui-upload-test`, and `upload-smoke-test` each hold one file of 53–136 bytes. There is no larger managed corpus, so four of the answerable questions used the two-file demo corpus.

### Negative cases

| Time | Call | HTTP | Body / effect |
| --- | --- | --- | --- |
| 18:18:52Z | `rag/ask` collection `does-not-exist-20261022` | 404 | `document collection not found`; no directory created |
| 18:18:52Z | `POST /v1/rag/documents` collection `acceptance-malformed-20261022`, `content_base64` invalid | 400 | `content_base64 is not valid base64`; directory not created |
| 18:18:52Z | `POST /v1/rag/documents` body `{not json` | 400 | `invalid JSON` |
| 18:18:52Z | `POST /v1/rag/documents` collection `../escape` | 400 | collection-name rule message |
| 18:18:52Z | `rag/ask` without Bearer | 401 | — |

Malformed uploads were sent because `store_document` validates the collection, filename, and base64 before any filesystem write. Its parser temp file is under `TMPDIR=/tmp`. No valid upload was sent, because a valid upload writes under `/workspace/rag-managed-docs`.

### Console (loopback `:8080`, Host `127.0.0.1:8080`, 18:19:43Z)

Each response was checked for secret patterns: the first 12 characters of the gateway key, `BEGIN`, `password_hash`, `access_token`, `refresh_token`, and the client id.

| Path | HTTP | Bytes | Secret hits | Note |
| --- | --- | --- | --- | --- |
| `/` | 200 | 20236 | 0 | title `Business AI`; `login-form`, `login-username`, `login-password` present |
| `/api/status` | 200 | 501 | 0 | `connection: ready`, `model_alive: true`, `key_configured: true`; key path shown, key value not |
| `/api/auth/status` | 200 | 166 | 0 | `configured: true, authenticated: false` |
| `/api/connectors` | 401 | 35 | 0 | `authentication required` |
| `/api/microsoft/start` | 401 | 35 | 0 | `authentication required` |
| `/api/ops/director` | 401 | 35 | 0 | `authentication required` |

Authenticated status: **BLOCKED**. An operator exists (`operators.json`, 0600), but this session does not know the password. No operator was created or rotated.

### Live scripts (`ops/test_lanes.py` `LIVE_H100_SCRIPTS`), run on the pod from `/tmp/AI-PLAYBOOK`

Side effects were checked before running. `agents.live_smoke` runs an in-memory agent against the gateway. `run_live_platform_smoke` and `run_live_rag_regression` are read-only gateway calls. `agents.live_async_smoke` posts to the console's `/api/agent`. That route requires an operator session before it creates a task in `/workspace/agent-task-history`. Without a session the request is refused, so nothing is written there; the newest file there is still from 2026-10-15.

| Start | Command | Exit | Counts |
| --- | --- | --- | --- |
| 18:19:31Z | `python3 -m agents.live_smoke --gateway http://127.0.0.1:8010/v1 --key-file /tmp/platform-gateway.key --model qwen3.5-27b` | **0** | state `final`, answer `The cost for 7 days is 696.486.`, 2 iterations, 1 tool call, 1308 tokens |
| 18:19:34Z | `python3 -m agents.live_async_smoke` | **1** | `STATUS_HTTP=200`, `ASYNC_START_HTTP=403` (no operator session or CSRF); this script cannot pass without operator login |
| 18:19:34Z | `env VLLM_BASE_URL=http://127.0.0.1:8002/v1 python3 -m evaluation.run_live_platform_smoke` | **0** | 6/6 PASS. `VLLM_BASE_URL` had to be set because the script defaults to `:8000`. |
| 18:19:36Z | `python3 -m evaluation.run_live_rag_regression` | **1** | 5/6 PASS. P3 "What type of train ticket should employees choose?" abstained. See the train failure note above. |

Gateway-failure behaviour was **not** tested live. vLLM was not killed. Coverage of that path relies on the existing unit tests (`model_engine_dead` cases in `api/test_gateway_reliability.py` and `web/test_server.py`).

## 4. Microsoft sign-in readiness

- Console 53091 environment: `MICROSOFT_CLIENT_ID_FILE=/tmp/microsoft-client-id` (0600), `MICROSOFT_TENANT=d595636e-9ef4-4890-b8a7-bde8dd5cab03`, redirect `http://127.0.0.1:18080/api/microsoft/callback`, token file `/tmp/microsoft-365-token.json` (absent).
- 18:19:43Z, offline, using the deployed code and pid 53091's exact environ: `load_client_id` read the file and matched the expected id. `MicrosoftOAuth.from_env(env).configured()` = `True`. `public_status()` = `configured: true, connected: false, status: disconnected, account: null`. This is configured but not connected.
- Gap found: `integrations.microsoft365.microsoft_configuration(env)` reports `status: NOT CONFIGURED, client_id: absent` for the same environment. It checks only `MICROSOFT_CLIENT_ID` and ignores `MICROSOFT_CLIENT_ID_FILE`. `ops/preflight.py` and `ops_centre/director.py` do the same. Any page that uses those functions will say NOT CONFIGURED while sign-in is actually available. This code was not changed in this session.
- The authorize URL from the same code and environment: host `login.microsoftonline.com`, path `/d595636e-9ef4-4890-b8a7-bde8dd5cab03/oauth2/v2.0/authorize`, `response_type=code`, `redirect_uri=http://127.0.0.1:18080/api/microsoft/callback`, `scope=openid profile email offline_access User.Read Mail.Read`, `code_challenge_method=S256`, 43-character `code_challenge`, `state` present, `prompt=select_account`, no client secret. This was not a browser redirect.
- Tunnel started on this PC: `ssh -N -L 18080:127.0.0.1:8080 -p 12572 root@154.54.102.41` with `ExitOnForwardFailure`. Through it: `/api/status` 200, `/api/auth/status` 200, `/api/microsoft/start` **401**.
- Cursor browser, new tab, `http://127.0.0.1:18080/api/microsoft/start` → `{"error":"authentication required"}`. **BLOCKED**: the route needs an operator session with `CONNECTORS_MANAGE`, and this session has no operator password. No Microsoft page was reached. No password was typed. No token exists. Mailbox read was **not attempted**. END-TO-END is **NOT VERIFIED**.

What the owner must do, with the tunnel running:
1. Open `http://127.0.0.1:18080/` and sign in with the console operator account.
2. Open `http://127.0.0.1:18080/#agent` and click the Microsoft sign-in button, or go to `http://127.0.0.1:18080/api/microsoft/start` in the same tab.
3. On `login.microsoftonline.com`, choose the work account in directory `d595636e-…` and accept the `User.Read` and `Mail.Read` consent.
4. The callback returns to the Agent page. Then one read-only mail search can be run from the Agent page to produce the first live mailbox count.

## 5. Things changed outside Git

- `/tmp/AI-PLAYBOOK` fast-forwarded to `d1e766e`.
- `/tmp/microsoft-client-id` created (0600).
- `/tmp/platform-diagnostics/{gateway,console}.{log,pid}` created.
- `/tmp/acceptance-20261022.json` (raw case output, no secrets).
- `/root/.gitconfig` gained `safe.directory=/tmp/AI-PLAYBOOK`.
- An SSH tunnel on this PC forwards `127.0.0.1:18080` to the pod console.

## Redeploy of d6d3beb (18:33–18:34Z)

- 18:32Z `git ls-remote` main = `d6d3beb8788ccd37b8b8012525674f92ae6c4863`, and both feature branches match. The diff from `d1e766e` adds only stdlib and in-repo imports; `api/` and `rag/` are unchanged.
- 18:33:12Z `SOURCE_UPDATE_APPROVED=yes bash ops/release/update-source-only.sh` printed `source-only d1e766e… -> d6d3beb…`. The gateway and console were restarted with the identical commands and environment, including `MICROSOFT_CLIENT_ID_FILE=/tmp/microsoft-client-id` and `MICROSOFT_TENANT=d595636e-…`.
- Gateway 53074 → **54370** (start epoch 1792693993.24), `/health` 200 at 18:33:14Z. Console 53091 → **54402** (start epoch 1792693994.90), `/api/status` 200 at 18:33:17Z. Mtime of the changed files (`integrations/microsoft_oauth.py`, `integrations/microsoft365.py`) is 1792693992.93, so both processes started after the checkout. vLLM stayed pid **1826**. Pod HEAD was `d6d3beb` with 0 tracked edits at 18:33:17Z and again at 18:34:14Z.

| Time | Check | HTTP | Result |
| --- | --- | --- | --- |
| 18:34:02Z | `:8002/v1/models`, `:8010/health`, `:8080/api/status` | 200 / 200 / 200 | healthy |
| 18:34:02Z | gateway chat completion | 200 | `gateway works` |
| 18:34:02Z | RAG `global-canary-1791758676`: "Quote the persistent storage verification code line…" | 200 | answered, cited `global-volume-canary.md`; quote "Persistent storage verification code: GLOBALVOL-58317." found in file |
| 18:34:04Z | RAG `upload-smoke-test`: "What is the demonstration recovery code in the test record?" | 200 | answered, cited `platform-upload-smoke.md`; `ORCHID-4729` in answer and file |
| 18:34:05Z | RAG demo: receipts deadline | 200 | answered, cited `expenses-policy.md`; `10 business days` in answer and file |
| 18:34:06Z | RAG demo: CEO's yacht | 200 | abstained, no sources |
| 18:34:06Z | RAG demo: VAT number | 200 | abstained, no sources |
| 18:34:06Z | console `/api/connectors`, `/api/ops/director` without login | 401 / 401 | operator login required |
| 18:34:07Z | Microsoft status from console pid 54402's environment | — | `client_id_source=MICROSOFT_CLIENT_ID_FILE`; `microsoft_configuration` = `configured`, client_id `present`, mailbox `NOT CONFIGURED`; OAuth `configured: true, connected: false`; director `microsoft_graph` = `UNKNOWN` (token file missing, `graph_called=false`) |

Microsoft now reports configured and not connected when the id comes from the file. The HTTP routes that show this need an operator session, so the status was read in-process with the console's exact environment.

| Start | Command | Exit | Counts |
| --- | --- | --- | --- |
| 18:34:07Z | `env VLLM_BASE_URL=http://127.0.0.1:8002/v1 python3 -m evaluation.run_live_platform_smoke` | **0** | 6/6 |
| 18:34:08Z | `python3 -m evaluation.run_live_rag_regression` | **1** | 5/6; P3 is the same train/rail gap |

Evidence records were appended to `docs/results/acceptance-evidence.json`; no existing record was removed. For `d6d3beb`: `http_200`, `deployed_sha_read`, `completion_ok`, two `rag_cited_answer_ok`, and two `rag_abstention_ok`. For `d1e766e` (this file's earlier run): one record each of `http_200`, `deployed_sha_read` and `completion_ok`, plus one `rag_cited_answer_ok` and one `rag_abstention_ok`. Nothing was added for mailbox, second endpoint, Blackwell, recovery, or backup.

Local board (Windows, `AI_PLAYBOOK_GIT` set): intended tip `d6d3beb…` from `git HEAD of this checkout`. Live score 4/9 (mandatory 4/8), **NO-GO**. Deployment, health, inference, and RAG gates PASS. Microsoft is NOT CONFIGURED; second endpoint, Blackwell, fresh recovery, and weight backup have NO EVIDENCE.

`python -m unittest ops.test_acceptance_board web.test_server` ran 48 tests and FAILED with 2 deterministic failures. Both are snapshot assertions on the committed evidence file:
- `ops.test_acceptance_board.test_recorded_repo_evidence` expects only `{live_health, inference_completion}` to pass and every timestamp to start with `2026-10-22T15:`.
- `web.test_server.test_acceptance_board_stays_no_go` expects "Deployed commit equals the intended Git tip" in `failing_acceptance`.

With the evidence file from `d6d3beb`, both tests pass. Any accurate new live record breaks them. No gate rule was changed. The tests need their pinned expectations updated outside this docs-only commit. One more test errored on each run, a different one each time (`test_rag_history_is_validated_and_forwarded`, then `test_printer_restart_needs_a_different_approver_and_does_not_run`). Run alone, `test_rag_history_is_validated_and_forwarded` passed, so these errors are flaky local HTTP timing.

## Machine-readable evidence

```json
{
  "recorded_at": "2026-10-22T18:22:00Z",
  "pod": "gom4ualdk47qrj",
  "source_sha": {"value": "d1e766ebc9afec185c328f279949012447417215", "checked_at": "2026-10-22T18:15:30Z", "method": "git ls-remote origin refs/heads/main"},
  "deployed_sha": {"value": "d1e766ebc9afec185c328f279949012447417215", "previous": "be9cbd2baf08ee1d9f1bbd192982c94575f57aeb", "checked_at": "2026-10-22T18:21:43Z", "method": "git -C /tmp/AI-PLAYBOOK rev-parse HEAD; process start after checkout mtime", "status_endpoint_reports_sha": false},
  "deployed_at": {"checkout": "2026-10-22T18:17:15Z", "gateway_start": "2026-10-22T18:17:15Z", "console_start": "2026-10-22T18:17:17Z", "checkout_mtime_epoch": 1792693035.11, "gateway_start_epoch": 1792693035.43, "console_start_epoch": 1792693037.08},
  "pids": {"vllm_before": 1826, "vllm_after": 1826, "gateway_before": 12581, "gateway_after": 53074, "console_before": 12593, "console_after": 53091, "checked_at": "2026-10-22T18:21:48Z"},
  "inference_ok": {"value": true, "http": 200, "model": "qwen3.5-27b", "answer": "gateway works", "at": "2026-10-22T18:18:43Z"},
  "rag_cases": [
    {"id": "demo_receipts", "ok": true, "abstain": false, "cited": ["expenses-policy.md"], "http": 200, "at": "2026-10-22T18:18:45Z"},
    {"id": "demo_signoff", "ok": true, "abstain": false, "cited": ["expenses-policy.md"], "http": 200, "at": "2026-10-22T18:18:46Z"},
    {"id": "demo_hours", "ok": true, "abstain": false, "cited": ["employee-handbook.md"], "http": 200, "at": "2026-10-22T18:18:48Z"},
    {"id": "demo_train_ticket", "ok": false, "abstain": true, "cited": [], "http": 200, "at": "2026-10-22T18:18:48Z", "note": "lexical gap train vs rail; same on be9cbd2"},
    {"id": "managed_global_canary", "ok": true, "abstain": false, "cited": ["global-volume-canary.md"], "quotes_in_doc": true, "http": 200, "at": "2026-10-22T18:18:50Z"},
    {"id": "managed_upload_smoke", "ok": true, "abstain": false, "cited": ["platform-upload-smoke.md"], "quotes_in_doc": true, "http": 200, "at": "2026-10-22T18:18:52Z"},
    {"id": "abstain_yacht", "ok": true, "abstain": true, "cited": [], "http": 200, "at": "2026-10-22T18:18:52Z"},
    {"id": "abstain_vat", "ok": true, "abstain": true, "cited": [], "http": 200, "at": "2026-10-22T18:18:52Z"},
    {"id": "abstain_managed_offtopic", "ok": true, "abstain": true, "cited": [], "http": 200, "at": "2026-10-22T18:18:52Z"},
    {"id": "missing_collection", "ok": true, "http": 404, "at": "2026-10-22T18:18:52Z"},
    {"id": "malformed_upload_bad_base64", "ok": true, "http": 400, "wrote": false, "at": "2026-10-22T18:18:52Z"}
  ],
  "live_scripts": [
    {"command": "python3 -m agents.live_smoke --gateway http://127.0.0.1:8010/v1 --key-file /tmp/platform-gateway.key --model qwen3.5-27b", "exit": 0, "at": "2026-10-22T18:19:31Z"},
    {"command": "python3 -m agents.live_async_smoke", "exit": 1, "reason": "HTTP 403 without operator session", "at": "2026-10-22T18:19:34Z"},
    {"command": "env VLLM_BASE_URL=http://127.0.0.1:8002/v1 python3 -m evaluation.run_live_platform_smoke", "exit": 0, "passed": 6, "total": 6, "at": "2026-10-22T18:19:34Z"},
    {"command": "python3 -m evaluation.run_live_rag_regression", "exit": 1, "passed": 5, "total": 6, "failed": ["P3"], "at": "2026-10-22T18:19:36Z"}
  ],
  "console": {"login_page_http": 200, "status_http": 200, "status_secret_hits": 0, "authenticated_status": "BLOCKED", "at": "2026-10-22T18:19:43Z"},
  "microsoft_status": {"configured": true, "connected": false, "status": "disconnected", "client_id_source": "MICROSOFT_CLIENT_ID_FILE", "tenant": "d595636e-9ef4-4890-b8a7-bde8dd5cab03", "authorize_host_path": "login.microsoftonline.com/d595636e-9ef4-4890-b8a7-bde8dd5cab03/oauth2/v2.0/authorize", "pkce": "S256", "browser_start_http": 401, "browser_start": "BLOCKED: operator login required", "microsoft_configuration_helper": "NOT CONFIGURED (ignores MICROSOFT_CLIENT_ID_FILE)", "at": "2026-10-22T18:20:30Z"},
  "microsoft_mail_read": {"value": false, "reason": "no operator session, no consent, no token", "at": "2026-10-22T18:20:30Z"}
}
```

## Console redeploy of c25c0ac (coordinator, 18:42Z)

- Before: console 54402, gateway 54370, vLLM 1826. `SOURCE_UPDATE_APPROVED=yes bash ops/release/update-source-only.sh` fast-forwarded d6d3beb to `c25c0ac19cb1639376bb2efd268395179f02161b`.
- Changed files: three docs files, `ops/acceptance_board.py`, and two test files. Only the console reads `ops/acceptance_board.py`, so only `web/server.py` was restarted. It reused the old process's own `/proc` environment (29 variables, Microsoft id file and tenant set) and command line. New pid 57562.
- Running revision: console start epoch 1792694566.07 is after the `ops/acceptance_board.py` mtime 1792694565.87. Pod HEAD c25c0ac with 0 tracked edits.
- 18:42:49Z: health 200 on 8002 and 8010, console 200 on 8080. vLLM 1826 and gateway 54370 unchanged.
- Earlier attempt at 18:41Z: a quoting slip in the remote shell stripped characters from the script. It stopped at the first failing command, before the kill line. A read-only check confirmed nothing changed.

## Redeploy of 4eab966 (coordinator, 19:46Z)

- `SOURCE_UPDATE_APPROVED=yes bash ops/release/update-source-only.sh` fast-forwarded the pod to `4eab966f9acc35632fcc2cfe4a5e42565db59e9a`.
- Gateway restarted from pid 54370 to **72553**. Console restarted from pid 64569 to **72560**. vLLM stayed pid **1826**.
- 19:46:42Z: health 200 on 8002 and 8010, console 200 on 8080.
- 19:47:37Z `python3 -m evaluation.run_live_rag_regression` exit 0, **6/6**. P3 `What type of train ticket should employees choose?` was HTTP 200, status answered, the answer contained `standard`, and the source was `expenses-policy.md`. N1 and N2 abstained with no sources.

## Console redeploy of 0a94d36 (20:10Z)

- Pod HEAD `0a94d36387f5d3a1e4ca9343687b6eac7b85f814`. Console restarted from pid 72560 to **76664**. Gateway stayed **72553**. vLLM stayed **1826**.
- 20:10:19Z: health 200 on 8002 and 8010, console 200 on 8080.
- Gateway code did not change, so the 19:47:37Z RAG regression of 6/6 still stands. It was not run again.

## Mailbox read on 326739eb (21:08Z)

- Pod HEAD stayed `326739eb6e04c4f3a1d9853b741a98c659f3f2cd`. vLLM pid **1826**, gateway pid **72553**, and console pid **80688** were not restarted.
- IT Helpdesk showed Microsoft connected, with read-only mail search. The account address is not recorded here.
- Before the search, `/api/connectors` reported `mailbox` **NOT CONFIGURED**. That field stays NOT CONFIGURED until a live Graph mail read returns HTTP 200.
- One `m365_search_mail` search ran from the console. The tool result was `status` ok, message count **0**. No message was opened and no mail was sent.
- After that call, `/api/connectors` reported `mailbox` **read**.
- `/tmp/microsoft-365-token.json` exists, mode `0600`. The file was not read.
- `/tmp/platform-diagnostics/console.log` does not contain a Graph HTTP status. It records `POST /api/agent` as HTTP 200. The Graph status is HTTP 200 because this console sets `mailbox` to read only on that response.
- Second endpoint, Blackwell, fresh recovery, and weight backup were not exercised. Production stays **NO-GO**.
