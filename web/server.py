#!/usr/bin/env python3
"""Loopback web console for the existing platform gateway.

The browser talks only to this process. Chat and document questions are
forwarded to the loopback gateway with a server-side API key. The key is
never written into HTML, JavaScript, logs, or API responses.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WEB_DIR = Path(__file__).resolve().parent
for _path in (_REPO_ROOT, _WEB_DIR):
    _text = str(_path)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from agents.adapters.rag_library import GroundedDocumentRetriever
from agents.it_support import looks_like_it_support
from agents.model import OpenAICompatibleClient
from agents.workspace import CONSOLE_TENANT, AgentDesk
from auth import AuthService, Permission
from auth.service import COOKIE_NAME, CSRF_HEADER, AuthError, SessionRecord
from ops_centre import OpsCentre
from integrations.endpoint import DeviceRegistry
from integrations.errors import AuthenticationError, InvalidRequest, RateLimited
from integrations.microsoft365 import platform_catalog
from integrations.microsoft_oauth import MicrosoftOAuth

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
# Registry model ids only — never accept filesystem paths from the browser.
MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SAFE_ERROR_RE = re.compile(r"^[A-Za-z0-9 ,.'():_/-]{1,200}$")
ERROR_ID_RE = re.compile(r"\A[0-9a-f]{16}\Z")
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
    cookie_secure: bool = False

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


def _env_flag(source: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = source.get(name, "").strip().casefold()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


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
    cookie_secure = _env_flag(source, "WEB_COOKIE_SECURE", default=False)
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
        cookie_secure=cookie_secure,
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


_CALLBACK_PAGES = {
    "connected": (
        "Microsoft sign-in finished",
        "This server confirmed the account with Microsoft. The Agent page shows a connected account only after that confirmation. Mail access is read-only.",
    ),
    "cancelled": (
        "Microsoft sign-in was cancelled",
        "No account was connected and no mailbox was read.",
    ),
    "failed": (
        "Microsoft sign-in did not finish",
        "The sign-in could not be confirmed. No mailbox was read.",
    ),
}


def callback_document(result: str) -> bytes:
    """Browser page for the OAuth redirect. The result is one of three fixed words."""
    title, detail = _CALLBACK_PAGES[result]
    target = "/?microsoft=" + result + "#agent"
    page = (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{title}</title>"
        f"<meta http-equiv=\"refresh\" content=\"0;url={target}\">"
        "</head><body><h1>" + title + "</h1><p>" + detail + "</p>"
        f"<p><a href=\"{target}\">Continue to the Agent page</a></p></body></html>"
    )
    return page.encode("utf-8")


def redact_request_log(text: str) -> str:
    """Drop query strings that can carry an OAuth code, state, or token."""
    lowered = text.casefold()
    sensitive = any(marker in lowered for marker in ("code=", "access_token", "refresh_token", "client_secret"))
    callback = "/api/microsoft/callback" in lowered and "?" in text
    if not sensitive and not callback:
        return text
    if "?" not in text:
        return "[redacted]"
    head, _, tail = text.partition("?")
    version = ""
    if " HTTP/" in tail:
        version = " HTTP/" + tail.split(" HTTP/", 1)[1]
    return head + " [query redacted]" + version


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
        self.oauth = MicrosoftOAuth.from_env()
        self.devices = DeviceRegistry.from_env()
        catalog, self.microsoft = platform_catalog(self.oauth, self.devices)
        self.microsoft.apply(catalog, CONSOLE_TENANT)
        self.endpoint = catalog.endpoint_service  # type: ignore[attr-defined]
        self.endpoint.apply(catalog)
        documents = GroundedDocumentRetriever(
            Path(os.environ.get("RAG_DOCS_DIR", "/workspace/rag-demo-docs")),
            Path(os.environ.get("RAG_MANAGED_DOCS_DIR", "/workspace/rag-managed-docs")),
        )
        history_dir = os.environ.get("AGENT_HISTORY_DIR")
        if not history_dir:
            volume_history = Path("/workspace/agent-task-history")
            if Path("/workspace").is_dir() and os.access("/workspace", os.W_OK):
                history_dir = str(volume_history)
            else:
                history_dir = "/tmp/agent-task-history"
        self.ops = OpsCentre()
        self.auth = AuthService(record_event=self.ops.record_event)
        self.desk = AgentDesk(
            catalog, documents=documents, history_dir=history_dir, ops_centre=self.ops,
        )
        super().__init__((config.host, config.port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalPlatformWeb/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"{self.client_address[0]} - {redact_request_log(format_string % args)}", flush=True)

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

    def send_error_json(self, status: int, message: str, error_id: str | None = None) -> None:
        body: dict[str, Any] = {"error": scrub(message, self.config.resolve_api_key())}
        if error_id:
            body["error_id"] = error_id
        self.send_json(status, body)

    @property
    def auth(self) -> AuthService:
        return self.server.auth  # type: ignore[attr-defined]

    def _host_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        if not host or "/" in host or "\\" in host or "@" in host:
            return False
        hostname = host.split(":", 1)[0]
        return hostname in {"127.0.0.1", "localhost"}

    def _request_origin_host(self) -> str | None:
        origin = (self.headers.get("Origin") or "").strip()
        if origin:
            hostname = (urlsplit(origin).hostname or "").lower()
            return hostname or None
        referer = (self.headers.get("Referer") or "").strip()
        if referer:
            hostname = (urlsplit(referer).hostname or "").lower()
            return hostname or None
        return None

    def _origin_allowed(self) -> bool:
        hostname = self._request_origin_host()
        if hostname is None:
            return False
        return hostname in {"127.0.0.1", "localhost"}

    def _session_id_from_cookie(self) -> str | None:
        raw = self.headers.get("Cookie") or ""
        if not raw:
            return None
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except CookieError:
            return None
        morsel = jar.get(COOKIE_NAME)
        if morsel is None:
            return None
        value = morsel.value.strip()
        return value or None

    def current_session(self) -> SessionRecord | None:
        return self.auth.validate_session(self._session_id_from_cookie())

    def _cookie_header(self, session_id: str, *, clear: bool = False) -> str:
        parts = [f"{COOKIE_NAME}={'' if clear else session_id}", "Path=/", "HttpOnly", "SameSite=Strict"]
        if clear:
            parts.append("Max-Age=0")
        else:
            parts.append(f"Max-Age={self.auth.absolute_seconds}")
        if self.config.cookie_secure:
            parts.append("Secure")
        return "; ".join(parts)

    def send_json_with_cookies(
        self,
        status: int,
        payload: dict[str, Any],
        *,
        set_session: SessionRecord | None = None,
        clear_session: bool = False,
    ) -> None:
        secret = self.config.resolve_api_key()
        encoded = scrub(json.dumps(payload, separators=(",", ":")), secret).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        if set_session is not None:
            self.send_header("Set-Cookie", self._cookie_header(set_session.session_id))
        if clear_session:
            self.send_header("Set-Cookie", self._cookie_header("", clear=True))
        self.end_headers()
        self.wfile.write(encoded)

    def _csrf_ok(self, session: SessionRecord) -> bool:
        offered = (self.headers.get(CSRF_HEADER) or "").strip()
        if not offered or not session.csrf_token:
            return False
        return hmac.compare_digest(offered, session.csrf_token)

    def require_operator(
        self,
        permission: Permission | None = None,
        *,
        mutating: bool = False,
    ) -> SessionRecord | None:
        if not self.auth.configured():
            self.send_error_json(503, "operator authentication is not configured")
            return None
        if mutating and not self._origin_allowed():
            self.send_error_json(403, "origin not allowed")
            return None
        session = self.current_session()
        if session is None:
            self.send_error_json(401, "authentication required")
            return None
        if mutating and not self._csrf_ok(session):
            self._ops().record_event(
                event_type="auth.csrf_rejected",
                component="auth",
                outcome="denied",
                severity="medium",
                actor=session.username,
                summary="CSRF token missing or invalid",
                detail={},
            )
            self.send_error_json(403, "CSRF token missing or invalid")
            return None
        if permission is not None and not self.auth.has_permission(session, permission):
            self._ops().record_event(
                event_type="auth.authorization_denied",
                component="auth",
                outcome="denied",
                severity="medium",
                actor=session.username,
                summary=f"Missing permission {permission.value}",
                detail={"permission": permission.value, "role": session.role},
            )
            self.send_error_json(403, "permission denied")
            return None
        return session

    def session_actor(self, session: SessionRecord) -> str:
        return session.username

    def do_GET(self) -> None:
        if not self._host_allowed():
            self.send_error_json(403, "host not allowed")
            return
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path == "/favicon.ico":
            self.send_bytes(204, b"", "text/plain; charset=utf-8")
            return
        if path == "/api/status":
            self.handle_status()
            return
        if path == "/api/auth/status":
            self.handle_auth_status()
            return
        if path == "/api/auth/operators":
            self.handle_auth_operators_list()
            return
        if path == "/api/ops/overview":
            self.handle_ops_overview()
            return
        if path == "/api/ops/health":
            self.handle_ops_health()
            return
        if path == "/api/ops/events":
            self.handle_ops_events(parsed)
            return
        if path == "/api/ops/alerts":
            self.handle_ops_alerts(parsed)
            return
        if path == "/api/ops/incidents":
            self.handle_ops_incidents(parsed)
            return
        if path == "/api/ops/integrity":
            self.handle_ops_integrity()
            return
        if path == "/api/ops/coverage":
            self.handle_ops_coverage()
            return
        if path == "/api/platform/models":
            self.handle_platform_models()
            return
        if path == "/api/documents":
            self.handle_document_list(parsed)
            return
        if path == "/api/connectors":
            self.handle_connectors()
            return
        if path == "/api/agent":
            self.handle_agent_get(parsed)
            return
        if path == "/api/agent/history":
            self.handle_agent_history(parsed)
            return
        if path == "/api/microsoft/start":
            self.handle_microsoft_start()
            return
        if path == "/api/microsoft/callback":
            self.handle_microsoft_callback(parsed)
            return
        if path == "/api/devices":
            self.handle_device_list()
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
        if not self._host_allowed():
            self.send_error_json(403, "host not allowed")
            return
        parsed = urlsplit(self.path)
        if parsed.query:
            self.send_error_json(404, "not found")
            return
        path = unquote(parsed.path)
        if path == "/api/auth/login":
            self.handle_auth_login()
        elif path == "/api/auth/logout":
            self.handle_auth_logout()
        elif path == "/api/auth/operators":
            self.handle_auth_operators_create()
        elif path == "/api/auth/operators/role":
            self.handle_auth_operators_role()
        elif path == "/api/auth/operators/disable":
            self.handle_auth_operators_disable()
        elif path == "/api/auth/operators/enable":
            self.handle_auth_operators_enable()
        elif path == "/api/auth/rotate":
            self.handle_auth_rotate()
        elif path == "/api/chat":
            self.handle_chat()
        elif path == "/api/rag":
            self.handle_rag()
        elif path == "/api/documents":
            self.handle_document_upload()
        elif path == "/api/agent":
            self.handle_agent()
        elif path == "/api/agent/decision":
            self.handle_agent_decision()
        elif path == "/api/agent/information":
            self.handle_agent_information()
        elif path == "/api/agent/cancel":
            self.handle_agent_cancel()
        elif path == "/api/ops/alerts/transition":
            self.handle_ops_alert_transition()
        elif path == "/api/ops/incidents":
            self.handle_ops_incident_create()
        elif path == "/api/ops/incidents/transition":
            self.handle_ops_incident_transition()
        elif path == "/api/ops/incidents/note":
            self.handle_ops_incident_note()
        elif path == "/api/ops/refresh":
            self.handle_ops_refresh()
        elif path == "/api/microsoft/disconnect":
            self.handle_microsoft_disconnect()
        elif path == "/api/devices/enrolment":
            self.handle_device_enrolment()
        elif path == "/api/devices/enroll":
            self.handle_device_enroll()
        elif path == "/api/devices/report":
            self.handle_device_report()
        elif path == "/api/devices/revoke":
            self.handle_device_revoke()
        else:
            self.send_error_json(404, "not found")

    def do_PUT(self) -> None:
        if not self._host_allowed():
            self.send_error_json(403, "host not allowed")
            return
        self.send_error_json(405, "method not allowed")

    def do_DELETE(self) -> None:
        if not self._host_allowed():
            self.send_error_json(403, "host not allowed")
            return
        parsed = urlsplit(self.path)
        if parsed.path != "/api/documents":
            self.send_error_json(404, "not found")
            return
        self.handle_document_delete(parsed)

    def handle_auth_status(self) -> None:
        self.send_json(200, self.auth.public_status(self.current_session()))

    def handle_auth_login(self) -> None:
        if not self._origin_allowed():
            self.send_error_json(403, "origin not allowed")
            return
        if not self.auth.configured():
            self.send_error_json(503, "operator authentication is not configured")
            return
        payload = self.read_json_object(max_bytes=4096)
        if payload is None:
            return
        username = payload.get("username")
        password = payload.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            self.send_error_json(400, "username and password are required")
            return
        # Session rotation: invalidate any prior cookie before issuing a new one.
        prior = self._session_id_from_cookie()
        if prior:
            self.auth.logout(prior)
        try:
            session = self.auth.login(username, password, peer_ip=self.client_address[0])
        except AuthError as exc:
            self.send_error_json(exc.status, exc.message)
            return
        self.send_json_with_cookies(200, self.auth.public_status(session), set_session=session)

    def handle_auth_logout(self) -> None:
        if not self._origin_allowed():
            self.send_error_json(403, "origin not allowed")
            return
        session = self.current_session()
        if session is not None and not self._csrf_ok(session):
            self.send_error_json(403, "CSRF token missing or invalid")
            return
        self.auth.logout(self._session_id_from_cookie())
        self.send_json_with_cookies(200, self.auth.public_status(None), clear_session=True)

    def handle_auth_rotate(self) -> None:
        session = self.require_operator(None, mutating=True)
        if session is None:
            return
        try:
            rotated = self.auth.rotate_session(session.session_id)
        except AuthError as exc:
            self.send_error_json(exc.status, exc.message)
            return
        self.send_json_with_cookies(200, self.auth.public_status(rotated), set_session=rotated)

    def handle_auth_operators_list(self) -> None:
        if self.require_operator(Permission.ADMIN_OPERATORS) is None:
            return
        self.send_json(200, {"operators": self.auth.list_operators()})

    def handle_auth_operators_create(self) -> None:
        session = self.require_operator(Permission.ADMIN_OPERATORS, mutating=True)
        if session is None:
            return
        payload = self.read_json_object(max_bytes=4096)
        if payload is None:
            return
        username = payload.get("username")
        password = payload.get("password")
        role = payload.get("role")
        if not isinstance(username, str) or not isinstance(password, str) or not isinstance(role, str):
            self.send_error_json(400, "username, password, and role are required")
            return
        try:
            record = self.auth.create_operator(
                username, password, role, actor=self.session_actor(session),
            )
        except AuthError as exc:
            self.send_error_json(exc.status, exc.message)
            return
        self.send_json(201, {"operator": record.public()})

    def handle_auth_operators_role(self) -> None:
        session = self.require_operator(Permission.ADMIN_OPERATORS, mutating=True)
        if session is None:
            return
        payload = self.read_json_object(max_bytes=4096)
        if payload is None:
            return
        username = payload.get("username")
        role = payload.get("role")
        if not isinstance(username, str) or not isinstance(role, str):
            self.send_error_json(400, "username and role are required")
            return
        try:
            record = self.auth.set_role(username, role, actor=self.session_actor(session))
        except AuthError as exc:
            self.send_error_json(exc.status, exc.message)
            return
        self.send_json(200, {"operator": record.public()})

    def handle_auth_operators_disable(self) -> None:
        session = self.require_operator(Permission.ADMIN_OPERATORS, mutating=True)
        if session is None:
            return
        payload = self.read_json_object(max_bytes=4096)
        if payload is None:
            return
        username = payload.get("username")
        if not isinstance(username, str):
            self.send_error_json(400, "username is required")
            return
        try:
            record = self.auth.set_disabled(username, True, actor=self.session_actor(session))
        except AuthError as exc:
            self.send_error_json(exc.status, exc.message)
            return
        self.send_json(200, {"operator": record.public()})

    def handle_auth_operators_enable(self) -> None:
        session = self.require_operator(Permission.ADMIN_OPERATORS, mutating=True)
        if session is None:
            return
        payload = self.read_json_object(max_bytes=4096)
        if payload is None:
            return
        username = payload.get("username")
        if not isinstance(username, str):
            self.send_error_json(400, "username is required")
            return
        try:
            record = self.auth.set_disabled(username, False, actor=self.session_actor(session))
        except AuthError as exc:
            self.send_error_json(exc.status, exc.message)
            return
        self.send_json(200, {"operator": record.public()})

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

    def send_redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        self.end_headers()

    def handle_connectors(self) -> None:
        if self.require_operator(Permission.CONNECTORS_VIEW, mutating=False) is None:
            return
        rows = self.server.desk.connectors()  # type: ignore[attr-defined]
        sign_in = self.server.oauth.public_status()  # type: ignore[attr-defined]
        for row in rows:
            if row.get("connector_id") == "microsoft365":
                row["sign_in"] = sign_in
        self.send_json(200, {"connectors": rows})

    def handle_microsoft_start(self) -> None:
        if self.require_operator(Permission.CONNECTORS_MANAGE, mutating=False) is None:
            return
        account = (parse_qs(urlsplit(self.path).query).get("account") or ["any"])[0]
        try:
            target = self.server.oauth.authorization_url(account)  # type: ignore[attr-defined]
        except InvalidRequest as exc:
            self.send_error_json(400, exc.message)
            return
        except AuthenticationError as exc:
            self.send_error_json(409, exc.message)
            return
        self.send_redirect(target)

    def send_callback_page(self, result: str) -> None:
        self.send_bytes(200, callback_document(result), "text/html; charset=utf-8")

    def handle_microsoft_callback(self, parsed) -> None:
        query = parse_qs(parsed.query)
        error = (query.get("error") or [""])[0]
        if error == "access_denied":
            self.send_callback_page("cancelled")
            return
        if error:
            self.send_callback_page("failed")
            return
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        if not code or not state:
            self.send_callback_page("failed")
            return
        try:
            self.server.oauth.complete(code, state)  # type: ignore[attr-defined]
            self.server.microsoft.apply(self.server.desk.catalog, CONSOLE_TENANT)  # type: ignore[attr-defined]
        except AuthenticationError:
            self.send_callback_page("failed")
            return
        self.send_callback_page("connected")

    def handle_microsoft_disconnect(self) -> None:
        session = self.require_operator(Permission.CONNECTORS_MANAGE, mutating=True)
        if session is None:
            return
        self.server.oauth.disconnect()  # type: ignore[attr-defined]
        self.server.microsoft.apply(self.server.desk.catalog, CONSOLE_TENANT)  # type: ignore[attr-defined]
        self.send_json(200, {"connected": False})

    def _loopback_client(self) -> bool:
        return self.client_address[0] in {"127.0.0.1", "::1"}

    def _refresh_endpoint(self) -> None:
        self.server.endpoint.apply(self.server.desk.catalog)  # type: ignore[attr-defined]

    def handle_device_list(self) -> None:
        if self.require_operator(Permission.CONNECTORS_MANAGE, mutating=False) is None:
            return
        if not self._loopback_client():
            self.send_error_json(403, "device routes are only available on the loopback console")
            return
        if not self.require_key():
            return
        self.send_json(200, {
            "devices": self.server.devices.public_devices(CONSOLE_TENANT),  # type: ignore[attr-defined]
            "remote_control": False,
        })

    def handle_device_enrolment(self) -> None:
        session = self.require_operator(Permission.CONNECTORS_MANAGE, mutating=True)
        if session is None:
            return
        if not self._loopback_client():
            self.send_error_json(403, "device routes are only available on the loopback console")
            return
        if not self.require_key():
            return
        created = self.server.devices.create_enrolment(CONSOLE_TENANT)  # type: ignore[attr-defined]
        self.send_json(200, created)

    def handle_device_enroll(self) -> None:
        if not self._loopback_client():
            self.send_error_json(403, "device routes are only available on the loopback console")
            return
        payload = self.read_json_object(max_bytes=4096)
        if payload is None:
            return
        try:
            device_id = self.server.devices.enrol(  # type: ignore[attr-defined]
                str(payload.get("code", "")),
                str(payload.get("display_name", "")),
                str(payload.get("device_secret", "")),
            )
        except AuthenticationError as exc:
            self.send_error_json(401, exc.message)
            return
        except InvalidRequest as exc:
            self.send_error_json(400, exc.message)
            return
        except RateLimited as exc:
            self.send_error_json(429, exc.message)
            return
        self._refresh_endpoint()
        self.send_json(200, {"device_id": device_id, "remote_control": False})

    def handle_device_report(self) -> None:
        if not self._loopback_client():
            self.send_error_json(403, "device routes are only available on the loopback console")
            return
        header = self.headers.get("Authorization", "")
        secret = header[7:] if header.startswith("Bearer ") else ""
        payload = self.read_json_object(max_bytes=4096)
        if payload is None:
            return
        try:
            result = self.server.devices.submit(secret, payload)  # type: ignore[attr-defined]
        except AuthenticationError as exc:
            self.send_error_json(401, exc.message)
            return
        except InvalidRequest as exc:
            self.send_error_json(400, exc.message)
            return
        except RateLimited as exc:
            self.send_error_json(429, exc.message)
            return
        self._refresh_endpoint()
        self.send_json(200, result)

    def handle_device_revoke(self) -> None:
        session = self.require_operator(Permission.CONNECTORS_MANAGE, mutating=True)
        if session is None:
            return
        if not self._loopback_client():
            self.send_error_json(403, "device routes are only available on the loopback console")
            return
        if not self.require_key():
            return
        payload = self.read_json_object(max_bytes=4096)
        if payload is None:
            return
        try:
            self.server.devices.revoke(CONSOLE_TENANT, str(payload.get("device_id", "")))  # type: ignore[attr-defined]
        except AuthenticationError as exc:
            self.send_error_json(401, exc.message)
            return
        except InvalidRequest as exc:
            self.send_error_json(400, exc.message)
            return
        self._refresh_endpoint()
        self.send_json(200, {"revoked": True, "remote_control": False})

    def _agent_model(self) -> OpenAICompatibleClient:
        model_id = self.config.model_id if MODEL_ID_RE.fullmatch(self.config.model_id or "") else None
        return OpenAICompatibleClient(
            self.config.gateway_url.rstrip("/") + "/v1",
            api_key_provider=self.config.resolve_api_key,
            model=model_id,
        )

    def handle_agent(self) -> None:
        session = self.require_operator(Permission.AGENT_START, mutating=True)
        if session is None:
            return
        if self.require_key() is None:
            return
        payload = self.read_json_object()
        if payload is None:
            return
        goal = payload.get("task")
        wait = payload.get("wait", True)
        if not isinstance(wait, bool):
            self.send_error_json(400, "wait must be a boolean")
            return
        try:
            # Helpdesk workflows need several tool rounds against Qwen; keep
            # non-IT agent tasks on the shorter ceiling.
            wall_cap = 180.0 if isinstance(goal, str) and looks_like_it_support(goal) else 60.0
            view = self.server.desk.start(  # type: ignore[attr-defined]
                goal,
                self._agent_model(),
                wall_seconds=min(wall_cap, self.config.upstream_timeout),
                wait=wait,
            )
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        self.send_json(200, view)

    def handle_agent_get(self, parsed) -> None:  # type: ignore[no-untyped-def]
        if self.require_operator(Permission.AGENT_VIEW, mutating=False) is None:
            return
        if self.require_key() is None:
            return
        query = parse_qs(parsed.query or "")
        task_ids = query.get("task_id") or []
        task_id = task_ids[0] if task_ids else ""
        if not task_id:
            self.send_error_json(400, "task_id is required")
            return
        try:
            view = self.server.desk.get(task_id)  # type: ignore[attr-defined]
        except KeyError:
            self.send_error_json(404, "task not found")
            return
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        self.send_json(200, view)

    def handle_agent_history(self, parsed) -> None:  # type: ignore[no-untyped-def]
        if self.require_operator(Permission.AGENT_VIEW, mutating=False) is None:
            return
        if self.require_key() is None:
            return
        query = parse_qs(parsed.query or "")
        raw_limit = (query.get("limit") or ["20"])[0]
        try:
            limit = int(raw_limit)
        except ValueError:
            self.send_error_json(400, "limit must be an integer")
            return
        try:
            rows = self.server.desk.history_list(limit=limit)  # type: ignore[attr-defined]
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        self.send_json(200, {"tasks": rows, "count": len(rows)})

    def handle_agent_decision(self) -> None:
        session = self.require_operator(Permission.AGENT_APPROVE, mutating=True)
        if session is None:
            return
        if self.require_key() is None:
            return
        payload = self.read_json_object()
        if payload is None:
            return
        task_id = payload.get("task_id")
        approved = payload.get("approved")
        call_id = payload.get("call_id")
        if (
            not isinstance(task_id, str) or not task_id
            or not isinstance(approved, bool)
            or not isinstance(call_id, str) or not call_id
        ):
            self.send_error_json(400, "task_id, call_id and approved are required")
            return
        arguments = payload.get("arguments")
        if arguments is not None and not isinstance(arguments, dict):
            self.send_error_json(400, "approval arguments must be an object")
            return
        try:
            view = self.server.desk.decide(  # type: ignore[attr-defined]
                task_id, approved, self.session_actor(session), call_id, arguments,
            )
        except KeyError:
            self.send_error_json(404, "task not found")
            return
        except RuntimeError as exc:
            self.send_error_json(409, str(exc))
            return
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        self.send_json(200, view)

    def handle_agent_information(self) -> None:
        session = self.require_operator(Permission.AGENT_START, mutating=True)
        if session is None:
            return
        if self.require_key() is None:
            return
        payload = self.read_json_object()
        if payload is None:
            return
        task_id = payload.get("task_id")
        information = payload.get("information")
        if not isinstance(task_id, str) or not task_id or not isinstance(information, str):
            self.send_error_json(400, "task_id and information are required")
            return
        try:
            view = self.server.desk.inform(task_id, information)  # type: ignore[attr-defined]
        except KeyError:
            self.send_error_json(404, "task not found")
            return
        except RuntimeError as exc:
            self.send_error_json(409, str(exc))
            return
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        self.send_json(200, view)

    def handle_agent_cancel(self) -> None:
        session = self.require_operator(Permission.AGENT_START, mutating=True)
        if session is None:
            return
        if self.require_key() is None:
            return
        payload = self.read_json_object()
        if payload is None:
            return
        task_id = payload.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            self.send_error_json(400, "task_id is required")
            return
        try:
            view = self.server.desk.cancel(task_id)  # type: ignore[attr-defined]
        except KeyError:
            self.send_error_json(404, "task not found")
            return
        self.send_json(200, view)

    def require_key(self) -> str | None:
        key = self.config.resolve_api_key()
        if len(key) < 32:
            self.send_error_json(503, "server-side API key is not configured")
            return None
        return key

    def _ops(self) -> OpsCentre:
        return self.server.ops  # type: ignore[attr-defined]

    def handle_ops_overview(self) -> None:
        if self.require_operator(Permission.OPS_VIEW, mutating=False) is None:
            return
        if self.require_key() is None:
            return
        ops = self._ops()
        try:
            ops.collect_agent_snapshot(self.server.desk)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        self.send_json(200, ops.overview())

    def handle_ops_health(self) -> None:
        if self.require_operator(Permission.OPS_VIEW, mutating=False) is None:
            return
        if self.require_key() is None:
            return
        self.send_json(200, self._ops().refresh_health())

    def handle_ops_events(self, parsed) -> None:  # type: ignore[no-untyped-def]
        if self.require_operator(Permission.OPS_VIEW, mutating=False) is None:
            return
        if self.require_key() is None:
            return
        query = parse_qs(parsed.query or "")
        limit_raw = (query.get("limit") or ["100"])[0]
        try:
            limit = int(limit_raw)
        except ValueError:
            self.send_error_json(400, "limit must be an integer")
            return
        self.send_json(200, self._ops().timeline(
            limit=limit,
            event_type=(query.get("event_type") or [None])[0],
            component=(query.get("component") or [None])[0],
            severity=(query.get("severity") or [None])[0],
            q=(query.get("q") or [None])[0],
            correlation_id=(query.get("correlation_id") or [None])[0],
        ))

    def handle_ops_alerts(self, parsed) -> None:  # type: ignore[no-untyped-def]
        if self.require_operator(Permission.OPS_VIEW, mutating=False) is None:
            return
        if self.require_key() is None:
            return
        query = parse_qs(parsed.query or "")
        status = (query.get("status") or [None])[0]
        rows = self._ops().alerts.list(status=status, limit=100)
        self.send_json(200, {"alerts": [a.to_public() for a in rows]})

    def handle_ops_incidents(self, parsed) -> None:  # type: ignore[no-untyped-def]
        if self.require_operator(Permission.OPS_VIEW, mutating=False) is None:
            return
        if self.require_key() is None:
            return
        query = parse_qs(parsed.query or "")
        status = (query.get("status") or [None])[0]
        rows = self._ops().incidents.list(status=status, limit=50)
        self.send_json(200, {"incidents": [i.to_public() for i in rows]})

    def handle_ops_integrity(self) -> None:
        if self.require_operator(Permission.OPS_VIEW, mutating=False) is None:
            return
        if self.require_key() is None:
            return
        self.send_json(200, {
            "event_store": self._ops().events.verify_chain(),
            "limitation": (
                "Hash chaining detects inconsistent rewrites of the event file we control. "
                "A privileged host user can still replace the store. Not forensic-grade WORM."
            ),
        })

    def handle_ops_coverage(self) -> None:
        if self.require_operator(Permission.OPS_VIEW, mutating=False) is None:
            return
        if self.require_key() is None:
            return
        from ops_centre.detections import COVERAGE
        self.send_json(200, {"coverage": COVERAGE.strip()})

    def handle_ops_refresh(self) -> None:
        session = self.require_operator(Permission.OPS_VIEW, mutating=True)
        if session is None:
            return
        if self.require_key() is None:
            return
        ops = self._ops()
        try:
            ops.collect_agent_snapshot(self.server.desk)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        health = ops.refresh_health()
        detections = ops.run_detections()
        self.send_json(200, {"health": health, "detections": detections})

    def handle_ops_alert_transition(self) -> None:
        session = self.require_operator(Permission.OPS_ALERT_WRITE, mutating=True)
        if session is None:
            return
        if self.require_key() is None:
            return
        payload = self.read_json_object()
        if payload is None:
            return
        alert_id = payload.get("alert_id")
        status = payload.get("status")
        actor = self.session_actor(session)
        note = payload.get("note") or ""
        if not isinstance(alert_id, str) or not isinstance(status, str):
            self.send_error_json(400, "alert_id and status are required")
            return
        try:
            alert = self._ops().alerts.transition(
                alert_id, status=status, actor=actor, note=str(note),
            )
        except KeyError:
            self.send_error_json(404, "alert not found")
            return
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        self._ops().record_event(
            event_type="ops.alert_transition",
            component="ops_centre",
            outcome=status,
            severity="info",
            actor=actor[:120],
            summary=f"Alert {alert_id[:12]}… → {status}",
            detail={"alert_id": alert_id, "status": status},
        )
        self.send_json(200, alert.to_public())

    def handle_ops_incident_create(self) -> None:
        session = self.require_operator(Permission.OPS_INCIDENT_WRITE, mutating=True)
        if session is None:
            return
        if self.require_key() is None:
            return
        payload = self.read_json_object()
        if payload is None:
            return
        alert_id = payload.get("alert_id")
        actor = self.session_actor(session)
        if not isinstance(alert_id, str):
            self.send_error_json(400, "alert_id is required")
            return
        alert = self._ops().alerts.get(alert_id)
        if alert is None:
            self.send_error_json(404, "alert not found")
            return
        try:
            incident = self._ops().incidents.create_from_alert(alert, actor=actor)
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        self._ops().record_event(
            event_type="ops.incident_opened",
            component="ops_centre",
            outcome="open",
            severity=alert.severity,
            actor=actor[:120],
            summary=f"Incident opened from alert: {alert.title}"[:400],
            detail={"incident_id": incident.incident_id, "alert_id": alert_id},
        )
        self.send_json(200, incident.to_public())

    def handle_ops_incident_transition(self) -> None:
        session = self.require_operator(Permission.OPS_INCIDENT_WRITE, mutating=True)
        if session is None:
            return
        if self.require_key() is None:
            return
        payload = self.read_json_object()
        if payload is None:
            return
        incident_id = payload.get("incident_id")
        status = payload.get("status")
        actor = self.session_actor(session)
        summary = payload.get("summary") or ""
        if not isinstance(incident_id, str) or not isinstance(status, str):
            self.send_error_json(400, "incident_id and status are required")
            return
        try:
            incident = self._ops().incidents.transition(
                incident_id, status=status, actor=actor, summary=str(summary),
            )
        except KeyError:
            self.send_error_json(404, "incident not found")
            return
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        self.send_json(200, incident.to_public())

    def handle_ops_incident_note(self) -> None:
        session = self.require_operator(Permission.OPS_INCIDENT_WRITE, mutating=True)
        if session is None:
            return
        if self.require_key() is None:
            return
        payload = self.read_json_object()
        if payload is None:
            return
        incident_id = payload.get("incident_id")
        note = payload.get("note")
        kind = payload.get("kind") or "note"
        actor = self.session_actor(session)
        if not isinstance(incident_id, str) or not isinstance(note, str):
            self.send_error_json(400, "incident_id and note are required")
            return
        try:
            incident = self._ops().incidents.add_note(
                incident_id, actor=actor, note=note, kind=str(kind),
            )
        except KeyError:
            self.send_error_json(404, "incident not found")
            return
        except ValueError as exc:
            self.send_error_json(400, str(exc))
            return
        self.send_json(200, incident.to_public())

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
        if self.require_operator(Permission.DOCS, mutating=False) is None:
            return
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
        session = self.require_operator(Permission.DOCS, mutating=True)
        if session is None:
            return
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
        session = self.require_operator(Permission.DOCS, mutating=True)
        if session is None:
            return
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

    def handle_platform_models(self) -> None:
        if self.require_operator(Permission.CHAT, mutating=False) is None:
            return
        if not self.require_key():
            return
        result = call_gateway(
            self.config,
            "GET",
            "/v1/platform/models",
            None,
            self.config.health_timeout,
            include_key=True,
        )
        self.forward_result(result)

    def resolve_requested_model_id(self, payload: dict[str, Any]) -> str | None:
        """Allow only safe registry ids from the browser; default to server config."""
        requested = payload.get("model")
        if requested in {None, ""}:
            return self.config.model_id or None
        if not isinstance(requested, str) or not MODEL_ID_RE.fullmatch(requested.strip()):
            return None
        return requested.strip()

    def handle_chat(self) -> None:
        session = self.require_operator(Permission.CHAT, mutating=True)
        if session is None:
            return
        payload = self.read_json_object()
        if payload is None:
            return
        if not self.require_key():
            return
        model_id = self.resolve_requested_model_id(payload)
        if model_id is None:
            if payload.get("model") not in {None, ""}:
                self.send_error_json(
                    400,
                    "model must be a registry id such as qwen3.5-27b or gemma-4-31b-it",
                )
                return
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
                "model": model_id,
                "messages": cleaned,
                "temperature": 0.2,
                "max_tokens": 512,
            },
            self.config.upstream_timeout,
            include_key=True,
        )
        self.forward_result(result)

    def handle_rag(self) -> None:
        session = self.require_operator(Permission.DOCS, mutating=True)
        if session is None:
            return
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
        top_k = payload.get("top_k", 8)
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1 or top_k > 20:
            self.send_error_json(400, "top_k must be an integer from 1 to 20")
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
        error_id = result.payload.get("error_id") if isinstance(result.payload, dict) else None
        self.send_error_json(
            result.status or 502,
            safe_error_text(result.payload, result.status or 502, self.config.resolve_api_key()),
            error_id if isinstance(error_id, str) and ERROR_ID_RE.fullmatch(error_id) else None,
        )


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
