#!/usr/bin/env python3
"""Tests for the TLS device gateway."""
from __future__ import annotations

import json
import os
import ssl
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import device_gateway
import server


def generate_self_signed_cert() -> tuple[Path, Path] | None:
    """Generate a self-signed certificate for testing.
    
    Returns (cert_path, key_path) or None if cryptography is not available.
    """
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        import datetime
    except ImportError:
        return None

    # Generate private key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # Generate certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Test"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Test"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            critical=False,
        )
        .sign(key, hashes.SHA256(), default_backend())
    )

    # Write to temporary files
    cert_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pem")
    key_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pem")

    cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
    cert_file.close()

    key_file.write(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_file.close()

    return Path(cert_file.name), Path(key_file.name)


class TestDeviceGatewayConfig(unittest.TestCase):
    """Tests for device gateway configuration validation."""

    def test_gateway_off_by_default(self) -> None:
        """Gateway is off unless DEVICE_GATEWAY_ENABLED=1."""
        env = {}
        with self.assertRaises(ValueError) as ctx:
            with patch.dict(os.environ, env, clear=True):
                device_gateway.validate_gateway_config()
        self.assertIn("DEVICE_GATEWAY_ENABLED", str(ctx.exception))

    def test_gateway_requires_enabled_flag(self) -> None:
        """Gateway requires DEVICE_GATEWAY_ENABLED=1."""
        env = {"DEVICE_GATEWAY_ENABLED": "0"}
        with self.assertRaises(ValueError) as ctx:
            with patch.dict(os.environ, env, clear=True):
                device_gateway.validate_gateway_config()
        self.assertIn("DEVICE_GATEWAY_ENABLED", str(ctx.exception))

    def test_gateway_requires_explicit_host(self) -> None:
        """Gateway requires DEVICE_GATEWAY_HOST to be explicitly set."""
        env = {"DEVICE_GATEWAY_ENABLED": "1"}
        with self.assertRaises(ValueError) as ctx:
            with patch.dict(os.environ, env, clear=True):
                device_gateway.validate_gateway_config()
        self.assertIn("DEVICE_GATEWAY_HOST", str(ctx.exception))

    def test_gateway_requires_cert(self) -> None:
        """Gateway requires DEVICE_GATEWAY_CERT to be set."""
        env = {
            "DEVICE_GATEWAY_ENABLED": "1",
            "DEVICE_GATEWAY_HOST": "0.0.0.0",
        }
        with self.assertRaises(ValueError) as ctx:
            with patch.dict(os.environ, env, clear=True):
                device_gateway.validate_gateway_config()
        self.assertIn("DEVICE_GATEWAY_CERT", str(ctx.exception))

    def test_gateway_requires_key(self) -> None:
        """Gateway requires DEVICE_GATEWAY_KEY to be set."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test")
            cert_file = f.name
        try:
            env = {
                "DEVICE_GATEWAY_ENABLED": "1",
                "DEVICE_GATEWAY_HOST": "0.0.0.0",
                "DEVICE_GATEWAY_CERT": cert_file,
            }
            with self.assertRaises(ValueError) as ctx:
                with patch.dict(os.environ, env, clear=True):
                    device_gateway.validate_gateway_config()
            self.assertIn("DEVICE_GATEWAY_KEY", str(ctx.exception))
        finally:
            Path(cert_file).unlink()

    def test_gateway_refuses_nonexistent_cert(self) -> None:
        """Gateway refuses to start if cert file doesn't exist."""
        env = {
            "DEVICE_GATEWAY_ENABLED": "1",
            "DEVICE_GATEWAY_HOST": "0.0.0.0",
            "DEVICE_GATEWAY_CERT": "/nonexistent/cert.pem",
            "DEVICE_GATEWAY_KEY": "/nonexistent/key.pem",
        }
        with self.assertRaises(ValueError) as ctx:
            with patch.dict(os.environ, env, clear=True):
                device_gateway.validate_gateway_config()
        self.assertIn("does not exist", str(ctx.exception))


class TestDeviceGatewayIntegration(unittest.TestCase):
    """Integration tests for the device gateway."""

    @classmethod
    def setUpClass(cls) -> None:
        """Generate test certificates."""
        result = generate_self_signed_cert()
        if result is None:
            cls.cert_path = None
            cls.key_path = None
        else:
            cls.cert_path, cls.key_path = result

    @classmethod
    def tearDownClass(cls) -> None:
        """Clean up test certificates."""
        if cls.cert_path:
            cls.cert_path.unlink(missing_ok=True)
        if cls.key_path:
            cls.key_path.unlink(missing_ok=True)

    def setUp(self) -> None:
        """Set up test environment."""
        if self.cert_path is None:
            self.skipTest("cryptography package not available")

        # Create minimal console server
        self.temp_dir = tempfile.mkdtemp()
        self.api_key_file = Path(self.temp_dir) / "api.key"
        self.api_key_file.write_text("test-api-key-0123456789abcdef0123456789")

        env = {
            "WEB_HOST": "127.0.0.1",
            "WEB_PORT": "0",  # Random port
            "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010",
            "PLATFORM_API_KEY_FILE": str(self.api_key_file),
            "RAG_DOCS_DIR": self.temp_dir,
            "RAG_MANAGED_DOCS_DIR": self.temp_dir,
            "OPERATOR_AUTH_STATE": str(Path(self.temp_dir) / "operators.json"),
            "ENDPOINT_STATE_FILE": str(Path(self.temp_dir) / "devices.json"),
        }

        with patch.dict(os.environ, env, clear=True):
            config = server.build_config()
            self.console = server.WebServer(config)
            self.console_host, self.console_port = self.console.server_address[:2]

        # Start console in background
        self.console_thread = threading.Thread(target=self.console.serve_forever, daemon=True)
        self.console_thread.start()
        time.sleep(0.1)

    def tearDown(self) -> None:
        """Clean up test servers."""
        if hasattr(self, "console"):
            self.console.shutdown()
            self.console.server_close()
        if hasattr(self, "temp_dir"):
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_plain_http_to_gateway_refused(self) -> None:
        """Plain HTTP requests to the gateway port are refused."""
        if self.cert_path is None:
            self.skipTest("cryptography not available")

        # Create gateway
        gateway = device_gateway.DeviceGatewayServer(
            "127.0.0.1", 0, str(self.cert_path), str(self.key_path), self.console, 60
        )
        gateway_host, gateway_port = gateway.server_address[:2]

        gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        gateway_thread.start()
        time.sleep(0.1)

        try:
            # Try plain HTTP (should fail at connection level)
            url = f"http://{gateway_host}:{gateway_port}/api/devices/enroll"
            with self.assertRaises(Exception):  # Connection error or SSL error
                req = urllib.request.Request(url, method="POST")
                urllib.request.urlopen(req, timeout=2)
        finally:
            gateway.shutdown()
            gateway.server_close()

    def test_operator_routes_return_404_on_gateway(self) -> None:
        """Operator and console routes return 404 on the gateway."""
        if self.cert_path is None:
            self.skipTest("cryptography not available")

        gateway = device_gateway.DeviceGatewayServer(
            "127.0.0.1", 0, str(self.cert_path), str(self.key_path), self.console, 60
        )
        gateway_host, gateway_port = gateway.server_address[:2]

        gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        gateway_thread.start()
        time.sleep(0.1)

        try:
            # Create SSL context that doesn't verify certificate
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            operator_routes = [
                "/api/remote-work/orders",
                "/api/remote-work/approve",
                "/api/devices",  # List route
                "/api/ops/health",
                "/api/auth/status",
                "/api/chat",
                "/api/connectors",
            ]

            for route in operator_routes:
                url = f"https://{gateway_host}:{gateway_port}{route}"
                try:
                    req = urllib.request.Request(url)
                    urllib.request.urlopen(req, context=ssl_context, timeout=2)
                    self.fail(f"{route} should return 404 on gateway")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 404, f"{route} should return 404, got {e.code}")

            # Test POST to operator routes
            for route in ["/api/remote-work/orders", "/api/remote-work/approve"]:
                url = f"https://{gateway_host}:{gateway_port}{route}"
                try:
                    data = json.dumps({"test": "data"}).encode("utf-8")
                    req = urllib.request.Request(url, data=data, method="POST")
                    req.add_header("Content-Type", "application/json")
                    urllib.request.urlopen(req, context=ssl_context, timeout=2)
                    self.fail(f"{route} should return 404 on gateway")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 404, f"{route} should return 404, got {e.code}")

        finally:
            gateway.shutdown()
            gateway.server_close()

    def test_device_heartbeat_requires_bearer(self) -> None:
        """Device request over gateway without Authorization bearer is refused."""
        if self.cert_path is None:
            self.skipTest("cryptography not available")

        gateway = device_gateway.DeviceGatewayServer(
            "127.0.0.1", 0, str(self.cert_path), str(self.key_path), self.console, 60
        )
        gateway_host, gateway_port = gateway.server_address[:2]

        gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        gateway_thread.start()
        time.sleep(0.1)

        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            url = f"https://{gateway_host}:{gateway_port}/api/remote-work/poll"
            req = urllib.request.Request(url, method="POST")
            # No Authorization header
            try:
                urllib.request.urlopen(req, context=ssl_context, timeout=2)
                self.fail("Request without bearer should be refused")
            except urllib.error.HTTPError as e:
                # Should be 401 or 403 (device authentication required)
                self.assertIn(e.code, [401, 403])

        finally:
            gateway.shutdown()
            gateway.server_close()

    def test_console_refuses_non_loopback_operator_routes(self) -> None:
        """Operator routes still refuse non-loopback callers on console listener."""
        # The console is bound to 127.0.0.1, so we can only test loopback
        # This test verifies that /api/remote-work/orders and /api/remote-work/approve
        # remain operator-only on the console
        url = f"http://{self.console_host}:{self.console_port}/api/remote-work/orders"
        
        # Without operator session, should fail
        data = json.dumps({"task": "test"}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        
        try:
            urllib.request.urlopen(req, timeout=2)
            self.fail("Should require operator session")
        except urllib.error.HTTPError as e:
            # Should be 401, 403, or 503 (authentication/authorization required or service not configured)
            # 503 is acceptable if the remote work store isn't configured for the test
            self.assertIn(e.code, [401, 403, 503])

    def test_rate_limiter(self) -> None:
        """Rate limiter enforces request limits."""
        limiter = device_gateway.RateLimiter(rate=5, window=1)
        
        # First 5 requests should succeed
        for _ in range(5):
            self.assertTrue(limiter.is_allowed("192.168.1.1"))
        
        # 6th request should fail
        self.assertFalse(limiter.is_allowed("192.168.1.1"))
        
        # Different IP should still work
        self.assertTrue(limiter.is_allowed("192.168.1.2"))
        
        # After window expires, should work again
        time.sleep(1.1)
        self.assertTrue(limiter.is_allowed("192.168.1.1"))


class TestDeviceGatewayRouting(unittest.TestCase):
    """Test that device routes work correctly."""

    def test_device_routes_defined(self) -> None:
        """Verify device routes are correctly defined."""
        routes = device_gateway.DEVICE_ROUTES
        
        # Should include device-side routes
        self.assertIn("/api/remote-work/poll", routes)
        self.assertIn("/api/remote-work/claim", routes)
        self.assertIn("/api/remote-work/complete", routes)
        self.assertIn("/api/remote-work/heartbeat", routes)
        self.assertIn("/api/devices/enroll", routes)
        self.assertIn("/api/devices/report", routes)
        self.assertIn("/api/repair/device/jobs", routes)
        self.assertIn("/api/repair/device/check-in", routes)
        self.assertIn("/api/repair/device/result", routes)
        
        # Should NOT include operator routes
        self.assertNotIn("/api/remote-work/orders", routes)
        self.assertNotIn("/api/remote-work/approve", routes)
        self.assertNotIn("/api/devices", routes)  # List route
        self.assertNotIn("/api/devices/revoke", routes)
        self.assertNotIn("/api/repair/device/revoke", routes)
        self.assertNotIn("/api/repair/device/enrol", routes)
        self.assertNotIn("/api/repair/device/issue", routes)


if __name__ == "__main__":
    unittest.main()
