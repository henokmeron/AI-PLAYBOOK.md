#!/usr/bin/env python3
"""Local authenticated gateway for a vLLM OpenAI-compatible chat API.

Standard-library only. Defaults to loopback so the prototype is not exposed to
external networks. This is a development boundary, not a production gateway.
"""
from __future__ import annotations

import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HOST = os.environ.get("PLATFORM_HOST", "127.0.0.1")
PORT = int(os.environ.get("PLATFORM_PORT", "8010"))
API_KEY = os.environ.get("PLATFORM_API_KEY", "")
UPSTREAM = os.environ.get("VLLM_UPSTREAM_URL", "http://127.0.0.1:8000/v1").rstrip("/")
MAX_BODY_BYTES = 1_048_576
UPSTREAM_TIMEOUT = 180
RATE_LIMIT_PER_MINUTE = 30
rate_lock = threading.Lock()
request_times: dict[str, list[float]] = {}


def json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalPlatformGateway/0.1"

    def log_message(self, format_string: str, *args: Any) -> None:
        # Log route/status only, never message bodies, API keys, or prompts.
        print(f"{self.client_address[0]} - {format_string % args}", flush=True)

    def send_json(self, status: int, value: dict[str, Any]) -> None:
        body = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def authorised(self) -> bool:
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return False
        supplied = header[len(prefix):]
        return bool(API_KEY) and hmac.compare_digest(supplied, API_KEY)

    def within_rate_limit(self) -> bool:
        now = time.monotonic()
        peer = self.client_address[0]
        cutoff = now - 60.0
        with rate_lock:
            times = [t for t in request_times.get(peer, []) if t >= cutoff]
            if len(times) >= RATE_LIMIT_PER_MINUTE:
                request_times[peer] = times
                return False
            times.append(now)
            request_times[peer] = times
            return True

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_json(404, {"error": "not found"})
            return
        try:
            req = urllib.request.Request(f"{UPSTREAM}/models", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            entries = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(entries, list):
                entries = []
            self.send_json(200, {"status": "ok", "upstream": "ok", "model_count": len(entries)})
        except Exception:
            self.send_json(503, {"status": "degraded", "upstream": "unavailable"})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_json(404, {"error": "not found"})
            return
        if not self.authorised():
            self.send_json(401, {"error": "authentication required"})
            return
        if not self.within_rate_limit():
            self.send_json(429, {"error": "rate limit exceeded"})
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self.send_json(415, {"error": "content type must be application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "invalid content length"})
            return
        if length <= 0:
            self.send_json(400, {"error": "request body required"})
            return
        if length > MAX_BODY_BYTES:
            self.send_json(413, {"error": "request body too large"})
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "invalid JSON"})
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            self.send_json(400, {"error": "JSON object with a messages array required"})
            return
        if payload.get("stream") is True:
            self.send_json(400, {"error": "streaming is not supported by this prototype gateway"})
            return

        upstream_req = urllib.request.Request(
            f"{UPSTREAM}/chat/completions",
            data=json_bytes(payload),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(upstream_req, timeout=UPSTREAM_TIMEOUT) as response:
                response_body = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            response_body = exc.read(MAX_BODY_BYTES)
            status = exc.code
        except Exception:
            self.send_json(502, {"error": "inference upstream unavailable"})
            return

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(response_body)


def main() -> int:
    if len(API_KEY) < 32:
        print("ERROR: set PLATFORM_API_KEY to a random secret of at least 32 characters.", flush=True)
        return 2
    if not UPSTREAM.startswith(("http://127.0.0.1:", "http://localhost:")):
        print("ERROR: this local prototype only allows a loopback vLLM upstream.", flush=True)
        return 2
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        print(f"ERROR: could not bind gateway to {HOST}:{PORT}: {exc}", flush=True)
        return 2
    print(f"Local gateway listening on http://{HOST}:{PORT}; upstream={UPSTREAM}", flush=True)
    print("Prototype warning: loopback only; not production-hardened.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
