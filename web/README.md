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
- `POST /api/rag` forwards `question`, optional `collection`, `top_k`, and a bounded validated `history` of prior user/assistant turns to `/v1/rag/ask`
- `GET /api/documents?collection=slug` lists files in a managed collection
- `POST /api/documents` uploads a validated base64-encoded document to the selected managed collection (maximum 10 MiB file)
- `DELETE /api/documents?collection=slug&filename=name` deletes a file after explicit user confirmation in the UI

Chat requests sent upstream use temperature `0.2` and `max_tokens` `512`. The gateway still rejects streaming. Document Q&A is conversational: the transcript keeps prior turns with citations, clears the question box when a request becomes pending, keeps the question box editable while Ask is locked to prevent duplicate concurrent submits, and recovers after success or failure. Clear conversation clears the transcript only (not uploads or the selected collection). History is bounded and validated server-side and framed as untrusted context, not as evidence. The gateway prompt requires spreadsheet calculations when asked (including daily × 7 for a seven-day week), preserves row/column relationships, and forbids inventing missing rates. See [docs/document-qa-conversation.md](../docs/document-qa-conversation.md).

## Checks

From the repository root:

```bash
python -m py_compile web/server.py web/test_server.py api/local_gateway.py api/test_rag_conversation.py
python -m unittest discover -s web -v
python -m unittest discover -s api -p 'test_*.py' -v
```

The web unit tests start a fake loopback gateway. The API conversation tests cover history validation and calculation prompting without contacting RunPod or vLLM.

## Files

- `web/server.py` — loopback server and gateway proxy
- `web/static/index.html` — dashboard shell
- `web/static/app.js` — chat, document Q&A, and status behaviour
- `web/static/styles.css` — layout
- `web/test_server.py` — proxy and page checks
- `web/.env.example` — variable reference


## Managed document upload in the web console

The Document Q&A view includes a document-library section. Enter a collection slug (lowercase letters/numbers/hyphens/underscores), choose a supported file, and upload. The browser sends the file through the loopback web server; the web server adds the gateway key server-side; the gateway validates and stores the document under `/workspace/rag-managed-docs/<collection>/`. The console can list and delete files in that collection. The file is not added to GitHub.

Supported extensions are TXT, Markdown, CSV, HTML/HTM, DOCX, text-based PDF and XLSX. The per-file limit is 10 MiB. Scanned PDFs without extractable text are rejected. Duplicate filenames are rejected by default; delete the old file first before re-uploading. The upload feature requires a deployed gateway version that supports `/v1/rag/documents`; the current repository gateway source has that API, but the running Pod must be verified after deployment.

To ask about uploaded documents, use the same collection name in Document Q&A. Leaving the collection blank uses the demo corpus. Uploading is for authorized, non-sensitive test documents only: this prototype has no user login or tenant-level access control, so do not upload confidential/customer documents.
