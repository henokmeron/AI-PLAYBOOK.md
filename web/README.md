# Local web console

A loopback-only dashboard for the existing platform gateway. It provides Chat, Document Q&A, and System Status. It does not replace the gateway, RAG engine, vLLM server, or model files.

The page in the browser calls only this web process. The process adds the gateway bearer token when it forwards `POST /v1/chat/completions` and `POST /v1/rag/ask`. The token is not embedded in HTML, JavaScript, logs, or responses.

Starting this console does not verify a connection to RunPod. A green status means the configured loopback gateway answered.

## Requirements

- Python 3.11 or newer
- No third-party packages
- The existing gateway listening on loopback, when you want live answers

The gateway remains `127.0.0.1:8010`. Do not change `PLATFORM_HOST`, do not bind the gateway to `0.0.0.0`, and do not publish port 8010. This console also refuses to bind to anything except loopback, and it refuses a non-loopback gateway URL.

The console has no login of its own. Anyone who can open it can send prompts. Keep it on loopback and do not attach a public RunPod HTTP proxy to its port.

## Secrets

Supply the gateway key in one of these ways:

1. Preferred: leave `PLATFORM_API_KEY_FILE` at `/tmp/platform-gateway.key`. That is the Pod-local file created by `api/run_gateway_smoke.sh`. It is not in Git.
2. Point `PLATFORM_API_KEY_FILE` at another local file containing only the key. A missing file is not replaced by the environment variable.
3. Set `PLATFORM_API_KEY_FILE` to an empty string and export `PLATFORM_API_KEY` for a local fake gateway. Do not commit that value, paste it into source, or leave it in shell history if you can avoid it.

This process does not read `.env` files. `web/.env.example` is documentation, not a loaded config. `web/.gitignore` ignores `.env` and `*.key`.

The server logs whether a key is configured. It does not log the key, prompts, or answers.

## Install

From a clone of this repository:

```bash
python3 --version
```

There is nothing to install.

## Run on the same machine as the gateway

Use this on the RunPod Pod, in a second terminal, while vLLM and the gateway are already running. Clone the Git repository onto the Pod. Do not copy model weights into the clone.

```bash
cd /path/to/AI-PLAYBOOK.md
export PLATFORM_GATEWAY_URL=http://127.0.0.1:8010
export PLATFORM_MODEL_ID=/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it
export PLATFORM_API_KEY_FILE=/tmp/platform-gateway.key
export WEB_HOST=127.0.0.1
export WEB_PORT=8080
python3 web/server.py
```

Open `http://127.0.0.1:8080` from that same machine. System Status should say the gateway is ready only after `/health` succeeds. Document Q&A shows the `sources` metadata returned by `POST /v1/rag/ask`. Chat uses the model id above, which is the id recorded for the current vLLM server.

An SSH local forward to `127.0.0.1:8080` on the Pod would let a browser on another computer reach the console without publishing it. This repository does not configure that tunnel, and it was not tested from the development machine. Do not forward port 8010.

## Run on a development machine

PowerShell:

```powershell
$env:PLATFORM_GATEWAY_URL = "http://127.0.0.1:8010"
$env:PLATFORM_MODEL_ID = "/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it"
$env:PLATFORM_API_KEY_FILE = ""
$env:PLATFORM_API_KEY = "replace-with-a-local-test-key-of-32-plus-chars"
python web/server.py
```

If the gateway is not on that machine, System Status stays "Gateway unreachable". That is the correct result. Do not treat it as a RunPod connection.

Stop the server with Ctrl+C.

## Development

Static files are read from `web/static/` on each request. Refresh the browser after editing HTML, CSS, or JavaScript. Restart `web/server.py` after changing the server.

The browser routes are:

- `GET /` the dashboard
- `GET /api/status` gateway health, key presence, and model configuration
- `POST /api/chat` forwards a cleaned message list to `/v1/chat/completions`
- `POST /api/rag` forwards `question`, optional `collection`, and `top_k` to `/v1/rag/ask`

Chat requests sent upstream use temperature `0.2` and `max_tokens` `512`. The gateway still rejects streaming. Document answers keep the gateway's own prompt and token limit.

## Checks

From the repository root:

```bash
python -m py_compile web/server.py web/test_server.py
python -m unittest discover -s web -v
```

The unit tests start a fake loopback gateway. They do not contact RunPod, vLLM, or the real gateway.

## Files

- `web/server.py` — loopback server and gateway proxy
- `web/static/index.html` — dashboard shell
- `web/static/app.js` — chat, document Q&A, and status behaviour
- `web/static/styles.css` — layout
- `web/test_server.py` — proxy and page checks
- `web/.env.example` — variable reference
