#!/usr/bin/env python3
"""TLS device gateway for remote Windows endpoints.

This gateway serves ONLY device-side routes over TLS, allowing real Windows
laptops on other machines to reach the device endpoints without exposing
the operator console.
"""
from __future__ import annotations

import os
import ssl
import sys
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

_WEB_DIR = Path(__file__).resolve().parent
if str(_WEB_DIR) not in sys.path:
    sys.path.insert(0, str(_WEB_DIR))

# Max request body size for the gateway (64 KiB)
MAX_GATEWAY_BODY_BYTES = 65536

# Device-side routes that are allowed on the gateway
# Only routes that devices call, not operator-initiated routes
DEVICE_ROUTES = {
    "/api/remote-work/poll",
    "/api/remote-work/claim",
    "/api/remote-work/complete",
    "/api/remote-work/heartbeat",
    "/api/devices/enroll",
    "/api/devices/report",
    "/api/repair/device/jobs",
    "/api/repair/device/result",
    "/api/repair/device/check-in",
}


class RateLimiter:
    """Simple per-client-IP rate limiter."""

    def __init__(self, rate: int, window: int = 60) -> None:
        """
        Args:
            rate: Maximum requests allowed per window
            window: Time window in seconds (default 60)
        """
        self.rate = rate
        self.window = window
        self.clients: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        """Check if a request from client_ip is allowed."""
        now = time.time()
        cutoff = now - self.window

        # Remove old timestamps
        self.clients[client_ip] = [ts for ts in self.clients[client_ip] if ts > cutoff]

        if len(self.clients[client_ip]) >= self.rate:
            return False

        self.clients[client_ip].append(now)
        return True


class DeviceGatewayHandler(BaseHTTPRequestHandler):
    """Handler that only serves device routes and enforces rate limiting."""

    server_version = "DeviceGateway/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[Gateway] {self.client_address[0]} - {format_string % args}", flush=True)

    def _check_rate_limit(self) -> bool:
        """Check rate limit for this client. Returns True if allowed."""
        client_ip = self.client_address[0]
        limiter: RateLimiter = getattr(self.server, "rate_limiter")
        if not limiter.is_allowed(client_ip):
            self.send_error_json(429, "rate limit exceeded")
            return False
        return True

    def _check_body_size(self) -> bool:
        """Check if body size is within gateway limits."""
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > MAX_GATEWAY_BODY_BYTES:
            self.send_error_json(413, "request body too large")
            return False
        return True

    def send_error_json(self, code: int, message: str) -> None:
        """Send a JSON error response."""
        import json
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _is_device_route(self, path: str) -> bool:
        """Check if path is an allowed device route."""
        return path in DEVICE_ROUTES

    def _route_request(self, path: str) -> None:
        """Route the request to the appropriate handler from the console server."""
        # Import server module to access the Handler class
        import server

        # Create a handler instance without triggering __init__'s automatic handling
        # We manually set up the needed attributes
        handler = object.__new__(server.Handler)
        handler.request = self.request
        handler.client_address = self.client_address
        handler.server = self.server.console_server  # type: ignore[attr-defined]
        handler._is_gateway_request = True  # type: ignore[attr-defined]
        
        # Copy request state
        handler.command = self.command
        handler.path = self.path
        handler.request_version = self.request_version
        handler.headers = self.headers
        handler.rfile = self.rfile
        handler.wfile = self.wfile
        handler.close_connection = True
        handler.requestline = f"{self.command} {self.path} {self.request_version}"
        
        # Dispatch to the appropriate method
        try:
            if path == "/api/remote-work/poll":
                handler.handle_remote_work_poll()
            elif path == "/api/remote-work/claim":
                handler.handle_remote_work_claim()
            elif path == "/api/remote-work/complete":
                handler.handle_remote_work_complete()
            elif path == "/api/remote-work/heartbeat":
                handler.handle_remote_work_heartbeat()
            elif path == "/api/devices/enroll":
                handler.handle_device_enroll()
            elif path == "/api/devices/report":
                handler.handle_device_report()
            elif path == "/api/repair/device/jobs":
                handler.handle_repair_device_jobs()
            elif path == "/api/repair/device/result":
                handler.handle_repair_device_result()
            elif path == "/api/repair/device/check-in":
                handler.handle_repair_device_check_in()
        except Exception:
            # If there was an error and no response was sent, send a generic error
            # The handler methods usually send their own error responses
            pass

    def do_GET(self) -> None:
        if not self._check_rate_limit():
            return

        parsed = urlsplit(self.path)
        path = unquote(parsed.path)

        if not self._is_device_route(path):
            self.send_error_json(404, "not found")
            return

        self._route_request(path)

    def do_POST(self) -> None:
        if not self._check_rate_limit():
            return

        if not self._check_body_size():
            return

        parsed = urlsplit(self.path)
        if parsed.query:
            self.send_error_json(404, "not found")
            return

        path = unquote(parsed.path)

        if not self._is_device_route(path):
            self.send_error_json(404, "not found")
            return

        self._route_request(path)

    def do_PUT(self) -> None:
        self.send_error_json(405, "method not allowed")

    def do_DELETE(self) -> None:
        self.send_error_json(405, "method not allowed")


class DeviceGatewayServer(ThreadingHTTPServer):
    """TLS gateway server for device routes."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        host: str,
        port: int,
        cert_file: str,
        key_file: str,
        console_server: Any,
        rate_limit: int = 60,
    ) -> None:
        self.console_server = console_server
        self.rate_limiter = RateLimiter(rate_limit)

        # Create SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert_file, key_file)

        super().__init__((host, port), DeviceGatewayHandler)

        # Wrap the socket with TLS
        self.socket = context.wrap_socket(self.socket, server_side=True)


def validate_gateway_config() -> tuple[str, int, str, str, int]:
    """
    Validate and return gateway configuration from environment.

    Returns:
        Tuple of (host, port, cert_file, key_file, rate_limit)

    Raises:
        ValueError: If configuration is invalid or required files don't exist
    """
    enabled = os.environ.get("DEVICE_GATEWAY_ENABLED", "").strip()
    if enabled != "1":
        raise ValueError("DEVICE_GATEWAY_ENABLED must be set to 1")

    host = os.environ.get("DEVICE_GATEWAY_HOST", "").strip()
    if not host:
        raise ValueError("DEVICE_GATEWAY_HOST must be explicitly set (e.g., 0.0.0.0)")

    port_str = os.environ.get("DEVICE_GATEWAY_PORT", "8443").strip()
    try:
        port = int(port_str)
        if not (1 <= port <= 65535):
            raise ValueError("port out of range")
    except ValueError:
        raise ValueError(f"DEVICE_GATEWAY_PORT must be a valid port number (1-65535), got: {port_str}")

    cert_file = os.environ.get("DEVICE_GATEWAY_CERT", "").strip()
    if not cert_file:
        raise ValueError("DEVICE_GATEWAY_CERT must be set to the path of the TLS certificate")
    if not Path(cert_file).is_file():
        raise ValueError(f"DEVICE_GATEWAY_CERT file does not exist: {cert_file}")

    key_file = os.environ.get("DEVICE_GATEWAY_KEY", "").strip()
    if not key_file:
        raise ValueError("DEVICE_GATEWAY_KEY must be set to the path of the TLS private key")
    if not Path(key_file).is_file():
        raise ValueError(f"DEVICE_GATEWAY_KEY file does not exist: {key_file}")

    rate_limit_str = os.environ.get("DEVICE_GATEWAY_RATE_LIMIT", "60").strip()
    try:
        rate_limit = int(rate_limit_str)
        if rate_limit < 1:
            raise ValueError("rate limit must be positive")
    except ValueError:
        raise ValueError(f"DEVICE_GATEWAY_RATE_LIMIT must be a positive integer, got: {rate_limit_str}")

    return host, port, cert_file, key_file, rate_limit


def create_gateway(console_server: Any) -> DeviceGatewayServer:
    """
    Create and return a configured device gateway server.

    Args:
        console_server: The console WebServer instance to share state with

    Returns:
        DeviceGatewayServer instance

    Raises:
        ValueError: If configuration is invalid
    """
    host, port, cert_file, key_file, rate_limit = validate_gateway_config()
    return DeviceGatewayServer(host, port, cert_file, key_file, console_server, rate_limit)
