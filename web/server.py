#!/usr/bin/env python3
"""Loopback web console for the existing platform gateway.

The browser talks only to this process. Chat and document questions are
forwarded to the loopback gateway with a server-side API key. The key is
never written into HTML, JavaScript, logs, or API responses.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_KEY_FILE = "/tmp/platform-gateway.key"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8010"
MAX_BODY_BYTES = 1_048_576
MAX_UPLOAD_BODY_BYTES = 14 * 1024 * 1024
MAX_RESPONSE_BYTES = 2_000_000
MAX_KEY_FILE_BYTES = 4096
MAX_MESSAGES = 40
MAX_MESSAGE_CHARS = 8000
MAX_QUESTION_CHARS = 2000
MAX_RAG_HISTORY_MESSAGES = 12
MAX_RAG_HISTORY_CHARS = 2000
MAX_RAG_HISTORY_TOTAL_CHARS = 12000
COLLECTION_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
SAFE_ERROR_RE = re.compile(r"^[A-Za-z0-9 ,.'():_-]{1,160}$")
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}
SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    (
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'",
    ),
)

class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so the bearer token cannot be sent to another host."""

    def http_error_302(self, req, fp, code, msg, headers):  # type: ignore[override]
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


# Ignore HTTP(S)_PROXY so the gateway bearer token cannot be sent to a proxy.
# RejectRedirects replaces the default redirect handler.
DIRECT_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPHandler(),
    RejectRedirects(),
)


@dataclass
class Config:
    host: str
    port: int
    gateway_url: str
    model_id: str
    api_key: str = field(repr=False, default="")
    api_key_file: str = ""
    static_dir: Path = STATIC_DIR
    upstream_timeout: float = 180.0
    health_timeout: float = 5.0

    def resolve_api_key(self) -> str:
        if self.api_key_file:
            path = Path(self.api_key_file)
            try:
                if not path.is_file() or path.stat().st_size > MAX_KEY_FILE_BYTES:
                    return ""
                return path.read_text(encoding="utf-8").strip().lstrip("\ufeff")
            except OSError:
                return ""
        return self.api_key.strip()


@dataclass
class GatewayResult:
    reachable: bool
    status: int
    payload: dict[str, Any] | None


def validate_bind_host(value: str) -> str:
    host = value.strip().lower()
    if host in {"127.0.0.1", "localhost"}:
        return "127.0.0.1"
    raise ValueError("WEB_HOST must be 127.0.0.1 or localhost so the console is not published")


def validate_gateway_url(value: str) -> str:
    parts = urlsplit(value.strip())
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "http"
        or host not in {"127.0.0.1", "localhost"}
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
        or parts.port is None
    ):
        raise ValueError(
            "PLATFORM_GATEWAY_URL must be an http loopback URL with a port and no path, "
            "for example http://127.0.0.1:8010"
        )
    return f"http://{host}:{parts.port}"


def validate_port(value: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("WEB_PORT must be an integer") from exc
    if port < 0 or port > 65535:
        raise ValueError("WEB_PORT must be between 0 and 65535")
    return port


def validate_timeout(value: str, name: str, default: float) -> float:
    raw = value.strip()
    if not raw:
        return default
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number of seconds") from exc
    if timeout <= 0 or timeout > 600:
        raise ValueError(f"{name} must be between 0 and 600 seconds")
    return timeout


def build_config(env: Mapping[str, str] | None = None) -> Config:
    source = os.environ if env is None else env
    model_id = source.get("PLATFORM_MODEL_ID", "").strip()
    if any(char in model_id for char in "\r\n\x00"):
        raise ValueError("PLATFORM_MODEL_ID must be a single line")
    if "PLATFORM_API_KEY_FILE" in source:
        key_file = source.get("PLATFORM_API_KEY_FILE", "").strip()
    else:
        key_file = DEFAULT_KEY_FILE
    return Config(
        host=validate_bind_host(source.get("WEB_HOST", "127.0.0.1")),
        port=validate_port(source.get("WEB_PORT", "8080")),
        gateway_url=validate_gateway_url(source.get("PLATFORM_GATEWAY_URL", DEFAULT_GATEWAY_URL)),
        model_id=model_id,
        api_key=source.get("PLATFORM_API_KEY", ""),
        api_key_file=key_file,
        static_dir=STATIC_DIR,
        upstream_timeout=validate_timeout(source.get("WEB_UPSTREAM_TIMEOUT", ""), "WEB_UPSTREAM_TIMEOUT", 180.0),
        health_timeout=validate_timeout(source.get("WEB_HEALTH_TIMEOUT", ""), "WEB_HEALTH_TIMEOUT", 5.0),
    )


def scrub(text: str, secret: str) -> str:
    if len(secret) >= 16 and secret in text:
        return text.replace(secret, "[redacted]")
    return text


def safe_error_text(payload: dict[str, Any] | None, status: int, secret: str) -> str:
    message = ""
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        message = scrub(payload["error"].strip(), secret)
    if message and SAFE_ERROR_RE.fullmatch(message) and "[redacted]" not in message:
        return message
    return f"gateway request failed ({status})"


def parse_object(raw: bytes) -> dict[str, Any] | None:
    if len(raw) > MAX_RESPONSE_BYTES:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return value


def public_health(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    public: dict[str, Any] = {}
    if payload.get("status") in {"ok", "degraded"}:
        public["status"] = payload["status"]
    if payload.get("upstream") in {"ok", "unavailable"}:
        public["upstream"] = payload["upstream"]
    count = payload.get("model_count")
    if isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 100:
        public["model_count"] = count
    return public


def validate_rag_history(value: Any) -> list[dict[str, str]]:
    """Validate optional prior Document Q&A turns. Raises ValueError on bad input."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("history must be an array of prior user and assistant turns")
    if len(value) > MAX_RAG_HISTORY_MESSAGES:
        raise ValueError(
            f"history must contain at most {MAX_RAG_HISTORY_MESSAGES} messages"
        )
    cleaned: list[dict[str, str]] = []
    total_chars = 0
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each history item must be an object")
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            raise ValueError("history roles must be user or assistant")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("each history message needs non-empty content")
        stripped = content.strip()
        if len(stripped) > MAX_RAG_HISTORY_CHARS:
            raise ValueError(
                f"history message must not exceed {MAX_RAG_HISTORY_CHARS} characters"
            )
        if cleaned and cleaned[-1]["role"] == role:
            raise ValueError("history roles must alternate between user and assistant")
        total_chars += len(stripped)
        if total_chars > MAX_RAG_HISTORY_TOTAL_CHARS:
            raise ValueError(
                f"history total text must not exceed {MAX_RAG_HISTORY_TOTAL_CHARS} characters"
            )
        cleaned.append({"role": role, "content": stripped})
    if cleaned and cleaned[0]["role"] != "user":
        raise ValueError("history must start with a user turn")
    if cleaned and cleaned[-1]["role"] != "assistant":
        raise ValueError("history must end with an assistant turn")
    return cleaned


def call_gateway(
    config: Config,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    timeout: float,
    include_key: bool,
    max_request_bytes: int = MAX_BODY_BYTES,
) -> GatewayResult:
    key = config.resolve_api_key() if include_key else ""
    if include_key and len(key) < 32:
        return GatewayResult(False, 0, None)
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if data is not None and len(data) > max_request_bytes:
        return GatewayResult(True, 413, {"error": "request body too large"})
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if include_key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(
        f"{config.gateway_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        response = DIRECT_OPENER.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        reachable = True
    except (urllib.error.URLError, TimeoutError, OSError):
        return GatewayResult(False, 0, None)
    else:
        with response:
            status = int(response.getcode())
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            reachable = True
    if len(raw) > MAX_RESPONSE_BYTES:
        return GatewayResult(True, 502, {"error": "gateway response was too large"})
    return GatewayResult(reachable, status, parse_object(raw))


def resolve_static(static_dir: Path, url_path: str) -> Path | None:
    if url_path in {"/", "/index.html"}:
        candidate = (static_dir / "index.html").resolve()
    elif url_path.startswith("/static/"):
        relative = url_path[len("/static/") :]
        if not relative or relative.endswith("/") or "\\" in relative or "\x00" in relative:
            return None
        parts = [part for part in relative.split("/") if part]
        if any(part in {".", ".."} for part in parts):
            return None
        candidate = static_dir.joinpath(*parts).resolve()
    else:
        return None
    try:
        candidate.relative_to(static_dir.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def connection_state(*, reachable: bool, upstream_ok: bool, key_ok: bool, model_ok: bool) -> str:
    if not reachable:
        return "unreachable"
    if not key_ok:
        return "key_missing"
    if not model_ok:
        return "model_missing"
    if not upstream_ok:
        return "degraded"
    return "ready"


class WebServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, config: Config) -> None:
        self.config = config
        super().__init__((config.host, config.port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalPlatformWeb/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"{self.client_address[0]} - {format_string % args}", flush=True)

    @property
    def config(self) -> Config:
        return self.server.config  # type: ignore[attr-defined]

    def send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        secret = self.config.resolve_api_key()
        encoded = scrub(json.dumps(payload, separators=(",", ":")), secret).encode("utf-8")
        self.send_bytes(status, encoded, "application/json; charset=utf-8")

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json(status, {"error": scrub(message, self.config.resolve_api_key())})

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path == "/favicon.ico":
            self.send_bytes(204, b"", "text/plain; charset=utf-8")
            return
        if path == "/api/status":
            self.handle_status()
            return
        if path == "/api/documents":
            self.handle_document_list(parsed)
            return
        static_file = resolve_static(self.config.static_dir, path)
        if static_file is None:
            self.send_error_json(404, "not found")
            return
        content_type = CONTENT_TYPES.get(static_file.suffix.lower())
        if content_type is None:
            self.send_error_json(404, "not found")
            return
        self.send_bytes(200, static_file.read_bytes(), content_type)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.query:
            self.send_error_json(404, "not found")
            return
        path = unquote(parsed.path)
        if path == "/api/chat":
            self.handle_chat()
        elif path == "/api/rag":
            self.handle_rag()
        elif path == "/api/documents":
            self.handle_document_upload()
        else:
            self.send_error_json(404, "not found")

    def do_PUT(self) -> None:
        self.send_error_json(405, "method not allowed")

    def do_DELETE(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path != "/api/documents":
            self.send_error_json(404, "not found")
            return
        self.handle_document_delete(parsed)

    def read_json_object(self, max_bytes: int = MAX_BODY_BYTES) -> dict[str, Any] | None:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self.send_error_json(415, "content type must be application/json")
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error_json(400, "invalid content length")
            return None
        if length <= 0:
            self.send_error_json(400, "request body required")
            return None
        if length > max_bytes:
            self.send_error_json(413, "request body too large")
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error_json(400, "invalid JSON")
            return None
        if not isinstance(payload, dict):
            self.send_error_json(400, "JSON object required")
            return None
        return payload

    def require_key(self) -> str | None:
        key = self.config.resolve_api_key()
        if len(key) < 32:
            self.send_error_json(503, "server-side API key is not configured")
            return None
        return key

    def handle_status(self) -> None:
        config = self.config
        key = config.resolve_api_key()
        key_ok = len(key) >= 32
        result = call_gateway(config, "GET", "/health", None, config.health_timeout, include_key=False)
        health = public_health(result.payload) if result.reachable and result.status == 200 else None
        upstream_ok = bool(health and health.get("status") == "ok" and health.get("upstream") == "ok")
        if result.reachable and not upstream_ok and result.status == 503:
            health = public_health(result.payload) or {"status": "degraded", "upstream": "unavailable"}
        state = connection_state(
            reachable=result.reachable,
            upstream_ok=upstream_ok,
            key_ok=key_ok,
            model_ok=bool(config.model_id),
        )
        key_file_found = False
        if config.api_key_file:
            try:
                key_file_found = Path(config.api_key_file).is_file()
            except OSError:
                key_file_found = False
        if not result.reachable:
            detail = (
                "This web server could not open the configured loopback gateway. "
                "That is expected unless this process is running on the same machine as the gateway. "
                "RunPod connectivity is not verified."
            )
        elif not key_ok:
            detail = (
                "The gateway answered, but this web server does not have a usable API key. "
                "Point PLATFORM_API_KEY_FILE at the gateway key file. RunPod connectivity is not verified."
            )
        elif not config.model_id:
            detail = (
                "The gateway answered. Set PLATFORM_MODEL_ID before using chat. "
                "Document questions can still use the model selected by the gateway. "
                "RunPod connectivity is not verified."
            )
        elif not upstream_ok:
            detail = (
                "The gateway answered, and its model upstream is unavailable. "
                "RunPod connectivity is not verified."
            )
        else:
            detail = (
                "The configured loopback gateway answered and its model upstream is healthy. "
                "This does not by itself verify a RunPod connection."
            )
        self.send_json(200, {
            "ui": "ok",
            "gateway_url": config.gateway_url,
            "gateway_reachable": result.reachable,
            "upstream": "ok" if upstream_ok else ("unavailable" if result.reachable else "unreachable"),
            "health": health,
            "key_configured": key_ok,
            "key_file": config.api_key_file or None,
            "key_file_found": key_file_found,
            "model_configured": bool(config.model_id),
            "model_id": config.model_id or None,
            "connection": state,
            "runpod_verified": False,
            "detail": detail,
        })


    def handle_document_list(self, parsed: Any) -> None:
        from urllib.parse import parse_qs
        values = parse_qs(parsed.query, keep_blank_values=True)
        if set(values) != {"collection"} or len(values.get("collection", [])) != 1:
            self.send_error_json(400, "one collection query parameter is required")
            return
        collection = values["collection"][0]
        if not COLLECTION_RE.fullmatch(collection):
            self.send_error_json(400, "collection must be a lowercase slug")
            return
        if not self.require_key():
            return
        result = call_gateway(
            self.config, "GET", "/v1/rag/documents?collection=" + collection,
            None, self.config.upstream_timeout, include_key=True,
        )
        self.forward_result(result)

    def handle_document_upload(self) -> None:
        payload = self.read_json_object(max_bytes=MAX_UPLOAD_BODY_BYTES)
        if payload is None:
            return
        if not self.require_key():
            return
        collection = payload.get("collection")
        filename = payload.get("filename")
        content_base64 = payload.get("content_base64")
        overwrite = payload.get("overwrite", False)
        if not isinstance(collection, str) or not COLLECTION_RE.fullmatch(collection):
            self.send_error_json(400, "collection must be a lowercase slug")
            return
        if not isinstance(filename, str) or not filename:
            self.send_error_json(400, "filename is required")
            return
        if not isinstance(content_base64, str) or not content_base64:
            self.send_error_json(400, "document content is required")
            return
        if not isinstance(overwrite, bool):
            self.send_error_json(400, "overwrite must be true or false")
            return
        result = call_gateway(
            self.config, "POST", "/v1/rag/documents",
            {"collection": collection, "filename": filename, "content_base64": content_base64, "overwrite": overwrite},
            self.config.upstream_timeout, include_key=True, max_request_bytes=MAX_UPLOAD_BODY_BYTES,
        )
        self.forward_result(result)

    def handle_document_delete(self, parsed: Any) -> None:
        from urllib.parse import parse_qs, quote
        values = parse_qs(parsed.query, keep_blank_values=True)
        if set(values) != {"collection", "filename"} or any(len(values.get(k, [])) != 1 for k in ("collection", "filename")):
            self.send_error_json(400, "one collection and filename parameter are required")
            return
        collection, filename = values["collection"][0], values["filename"][0]
        if not COLLECTION_RE.fullmatch(collection):
            self.send_error_json(400, "collection must be a lowercase slug")
            return
        if not filename or len(filename) > 120 or "/" in filename or "\\" in filename:
            self.send_error_json(400, "invalid filename")
            return
        if not self.require_key():
            return
        result = call_gateway(
            self.config, "DELETE",
            "/v1/rag/documents?collection=" + quote(collection, safe="") + "&filename=" + quote(filename, safe=""),
            None, self.config.upstream_timeout, include_key=True,
        )
        self.forward_result(result)

    def handle_chat(self) -> None:
        payload = self.read_json_object()
        if payload is None:
            return
        if not self.require_key():
            return
        if not self.config.model_id:
            self.send_error_json(503, "PLATFORM_MODEL_ID is not configured on the web server")
            return
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages or len(messages) > MAX_MESSAGES:
            self.send_error_json(400, "messages must contain 1 to 40 items")
            return
        cleaned: list[dict[str, str]] = []
        for item in messages:
            if not isinstance(item, dict):
                self.send_error_json(400, "each message must be an object")
                return
            role = item.get("role")
            content = item.get("content")
            if role not in {"system", "user", "assistant"} or not isinstance(content, str) or not content.strip():
                self.send_error_json(400, "each message needs a role and non-empty content")
                return
            if len(content) > MAX_MESSAGE_CHARS:
                self.send_error_json(413, "a message is too long")
                return
            cleaned.append({"role": role, "content": content})
        if not any(item["role"] == "user" for item in cleaned):
            self.send_error_json(400, "at least one user message is required")
            return
        result = call_gateway(
            self.config,
            "POST",
            "/v1/chat/completions",
            {
                "model": self.config.model_id,
                "messages": cleaned,
                "temperature": 0.2,
                "max_tokens": 512,
            },
            self.config.upstream_timeout,
            include_key=True,
        )
        self.forward_result(result)

    def handle_rag(self) -> None:
        payload = self.read_json_object()
        if payload is None:
            return
        if not self.require_key():
            return
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            self.send_error_json(400, "a non-empty question string is required")
            return
        question = question.strip()
        if len(question) > MAX_QUESTION_CHARS:
            self.send_error_json(413, f"question must not exceed {MAX_QUESTION_CHARS} characters")
            return
        top_k = payload.get("top_k", 4)
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1 or top_k > 10:
            self.send_error_json(400, "top_k must be an integer from 1 to 10")
            return
        try:
            history = validate_rag_history(payload.get("history"))
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        upstream: dict[str, Any] = {"question": question, "top_k": top_k}
        if history:
            upstream["history"] = history
        if "collection" in payload and payload.get("collection") not in {None, ""}:
            collection = payload.get("collection")
            if not isinstance(collection, str) or not COLLECTION_RE.fullmatch(collection):
                self.send_error_json(400, "collection must be a lowercase slug")
                return
            upstream["collection"] = collection
        result = call_gateway(
            self.config,
            "POST",
            "/v1/rag/ask",
            upstream,
            self.config.upstream_timeout,
            include_key=True,
        )
        self.forward_result(result)

    def forward_result(self, result: GatewayResult) -> None:
        if not result.reachable:
            self.send_error_json(502, "gateway unreachable")
            return
        if 300 <= result.status < 400:
            self.send_error_json(502, "gateway request failed")
            return
        if result.status == 413 and result.payload and result.payload.get("error") == "request body too large":
            self.send_error_json(413, "request body too large")
            return
        if 200 <= result.status < 300 and isinstance(result.payload, dict):
            self.send_json(result.status, result.payload)
            return
        self.send_error_json(result.status or 502, safe_error_text(result.payload, result.status or 502, self.config.resolve_api_key()))


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("ERROR: this server does not take arguments; set environment variables instead.", flush=True)
        return 2
    try:
        config = build_config()
    except ValueError as exc:
        print(f"ERROR: {exc}", flush=True)
        return 2
    try:
        httpd = WebServer(config)
    except OSError as exc:
        print(f"ERROR: could not bind web UI to {config.host}:{config.port}: {exc}", flush=True)
        return 2
    host, port = httpd.server_address[:2]
    print(f"Local web UI listening on http://{host}:{port}", flush=True)
    print(f"Gateway target: {config.gateway_url}", flush=True)
    print(f"API key file: {config.api_key_file or '(not set)'}", flush=True)
    print(f"API key configured: {'yes' if len(config.resolve_api_key()) >= 32 else 'no'}", flush=True)
    print(f"Model id configured: {'yes' if config.model_id else 'no'}", flush=True)
    print("RunPod connectivity is not verified by starting this process.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
