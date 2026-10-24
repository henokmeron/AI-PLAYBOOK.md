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

    def test_tls_handshake_does_not_block_other_clients(self) -> None:
        """A stalled TLS handshake doesn't block other clients."""
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
            # Create a raw TCP connection that doesn't do TLS handshake
            import socket as sock_mod
            stalled_socket = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_STREAM)
            stalled_socket.connect((gateway_host, gateway_port))
            # Don't send anything - just hold the connection
            
            # Give it a moment
            time.sleep(0.2)
            
            # Now a real TLS client should still work
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            url = f"https://{gateway_host}:{gateway_port}/api/remote-work/orders"
            req = urllib.request.Request(url)
            
            # Should get 404 (not timeout) because gateway handles handshake per-request
            try:
                urllib.request.urlopen(req, context=ssl_context, timeout=5)
                self.fail("Should return 404")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 404)
            
            # Clean up stalled socket
            stalled_socket.close()
        finally:
            gateway.shutdown()
            gateway.server_close()

    def test_enrollment_and_heartbeat_happy_path(self) -> None:
        """Happy path: enroll with valid code, then authenticated heartbeat works."""
        if self.cert_path is None:
            self.fail("cryptography package required for this test")

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

            # Create enrollment code directly via the device registry
            created = self.console.devices.create_enrolment("local-console")
            enrolment_code = created["enrolment_code"]
            self.assertIsNotNone(enrolment_code, "Failed to create enrollment code")

            # Generate a device secret
            import secrets as secrets_mod
            device_secret = secrets_mod.token_urlsafe(32)

            # Enroll via gateway
            gateway_enroll_url = f"https://{gateway_host}:{gateway_port}/api/devices/enroll"
            enroll_payload = json.dumps({
                "code": enrolment_code,
                "display_name": "test-laptop",
                "device_secret": device_secret,
            }).encode()
            
            enroll_req = urllib.request.Request(gateway_enroll_url, data=enroll_payload, method="POST")
            enroll_req.add_header("Content-Type", "application/json")
            
            enroll_resp = urllib.request.urlopen(enroll_req, context=ssl_context, timeout=2)
            self.assertEqual(enroll_resp.status, 200, "Enrollment should succeed")
            enroll_result = json.loads(enroll_resp.read().decode())
            
            device_id = enroll_result.get("device_id")
            self.assertIsNotNone(device_id, "Enrollment should return device_id")
            self.assertIsInstance(device_id, str, "device_id should be string")
            self.assertEqual(len(device_id), 32, f"device_id should be 32 chars, got {len(device_id)}: {device_id}")
            
            # Verify device can be authenticated
            try:
                auth_id = self.console.devices.authenticated_device_id(device_secret)
                self.assertEqual(device_id, auth_id, "Auth ID should match enrolled device_id")
            except Exception as e:
                self.fail(f"Authentication failed: {e}")
            
            # Now send authenticated heartbeat via gateway
            gateway_heartbeat_url = f"https://{gateway_host}:{gateway_port}/api/remote-work/heartbeat"
            import time as time_mod
            heartbeat_payload = json.dumps({
                "utc": time_mod.strftime("%Y-%m-%dT%H:%M:%SZ", time_mod.gmtime()),
                "worker_version": "1.0.0-test"
            }).encode()
            heartbeat_req = urllib.request.Request(gateway_heartbeat_url, data=heartbeat_payload, method="POST")
            heartbeat_req.add_header("Authorization", f"Bearer {device_secret}")
            heartbeat_req.add_header("Content-Type", "application/json")
            
            try:
                heartbeat_resp = urllib.request.urlopen(heartbeat_req, context=ssl_context, timeout=2)
                self.assertEqual(heartbeat_resp.status, 200, "Authenticated heartbeat should succeed")
            except urllib.error.HTTPError as e:
                error_body = e.read().decode()
                self.fail(f"Heartbeat failed with {e.code}: {error_body}")
            
        finally:
            gateway.shutdown()
            gateway.server_close()

    def test_wrong_and_reused_enrollment_code_refused(self) -> None:
        """Wrong and reused enrollment codes are refused over gateway."""
        if self.cert_path is None:
            self.fail("cryptography package required for this test")

        # High rate limit to prevent 429
        gateway = device_gateway.DeviceGatewayServer(
            "127.0.0.1", 0, str(self.cert_path), str(self.key_path), self.console, 1000
        )
        gateway_host, gateway_port = gateway.server_address[:2]

        gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        gateway_thread.start()
        time.sleep(0.1)

        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            gateway_enroll_url = f"https://{gateway_host}:{gateway_port}/api/devices/enroll"

            # Test wrong enrollment code
            import secrets as secrets_mod
            wrong_payload = json.dumps({
                "code": "wrong-code-12345",
                "display_name": "test-laptop",
                "device_secret": secrets_mod.token_urlsafe(32),
            }).encode()
            
            wrong_req = urllib.request.Request(gateway_enroll_url, data=wrong_payload, method="POST")
            wrong_req.add_header("Content-Type", "application/json")
            
            try:
                urllib.request.urlopen(wrong_req, context=ssl_context, timeout=2)
                self.fail("Wrong enrollment code should be refused")
            except urllib.error.HTTPError as e:
                # Should be 400, 401, or 403 (not 429 due to high rate limit)
                self.assertIn(e.code, [400, 401, 403], f"Wrong code should be 400/401/403, got {e.code}")

            # Test reused enrollment code
            created = self.console.devices.create_enrolment("local-console")
            valid_code = created["enrolment_code"]
            
            # First enrollment should succeed
            first_payload = json.dumps({
                "code": valid_code,
                "display_name": "first-laptop",
                "device_secret": secrets_mod.token_urlsafe(32),
            }).encode()
            
            first_req = urllib.request.Request(gateway_enroll_url, data=first_payload, method="POST")
            first_req.add_header("Content-Type", "application/json")
            
            first_resp = urllib.request.urlopen(first_req, context=ssl_context, timeout=2)
            self.assertEqual(first_resp.status, 200, "First enrollment should succeed")
            
            # Reuse the same code - should be refused
            reused_payload = json.dumps({
                "code": valid_code,
                "display_name": "second-laptop",
                "device_secret": secrets_mod.token_urlsafe(32),
            }).encode()
            
            reused_req = urllib.request.Request(gateway_enroll_url, data=reused_payload, method="POST")
            reused_req.add_header("Content-Type", "application/json")
            
            try:
                urllib.request.urlopen(reused_req, context=ssl_context, timeout=2)
                self.fail("Reused enrollment code should be refused")
            except urllib.error.HTTPError as e:
                # Should be 400, 401, or 403 (not 429 due to high rate limit)
                self.assertIn(e.code, [400, 401, 403], f"Reused code should be 400/401/403, got {e.code}")

        finally:
            gateway.shutdown()
            gateway.server_close()


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


class TestDeviceGatewayErrorHandling(unittest.TestCase):
    """Test error handling in the gateway."""

    def test_handler_exception_produces_500(self) -> None:
        """Handler raising an exception produces 500, not a hang."""
        result = generate_self_signed_cert()
        if result is None:
            self.skipTest("cryptography not available")
        
        cert_path, key_path = result
        
        try:
            # Create minimal console
            temp_dir = tempfile.mkdtemp()
            api_key_file = Path(temp_dir) / "api.key"
            api_key_file.write_text("test-key-0123456789abcdef0123456789")
            
            env = {
                "WEB_HOST": "127.0.0.1",
                "WEB_PORT": "0",
                "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010",
                "PLATFORM_API_KEY_FILE": str(api_key_file),
                "RAG_DOCS_DIR": temp_dir,
                "RAG_MANAGED_DOCS_DIR": temp_dir,
                "OPERATOR_AUTH_STATE": str(Path(temp_dir) / "operators.json"),
                "ENDPOINT_STATE_FILE": str(Path(temp_dir) / "devices.json"),
            }
            
            with patch.dict(os.environ, env, clear=True):
                config = server.build_config()
                console = server.WebServer(config)
            
            # Patch a handler to raise
            original_method = server.Handler.handle_remote_work_poll
            def raise_error(self):
                raise RuntimeError("test error")
            
            server.Handler.handle_remote_work_poll = raise_error
            
            try:
                gateway = device_gateway.DeviceGatewayServer(
                    "127.0.0.1", 0, str(cert_path), str(key_path), console, 60
                )
                gateway_host, gateway_port = gateway.server_address[:2]
                
                gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
                gateway_thread.start()
                time.sleep(0.1)
                
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                url = f"https://{gateway_host}:{gateway_port}/api/remote-work/poll"
                req = urllib.request.Request(url, method="POST")
                
                try:
                    urllib.request.urlopen(req, context=ssl_context, timeout=2)
                    self.fail("Should return 500 error")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 500)
                finally:
                    gateway.shutdown()
                    gateway.server_close()
            finally:
                server.Handler.handle_remote_work_poll = original_method
                console.server_close()
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
        finally:
            cert_path.unlink(missing_ok=True)
            key_path.unlink(missing_ok=True)

    def test_invalid_content_length_returns_400(self) -> None:
        """Non-integer or negative Content-Length returns 400."""
        result = generate_self_signed_cert()
        if result is None:
            self.skipTest("cryptography not available")
        
        cert_path, key_path = result
        
        try:
            temp_dir = tempfile.mkdtemp()
            api_key_file = Path(temp_dir) / "api.key"
            api_key_file.write_text("test-key-0123456789abcdef0123456789")
            
            env = {
                "WEB_HOST": "127.0.0.1",
                "WEB_PORT": "0",
                "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010",
                "PLATFORM_API_KEY_FILE": str(api_key_file),
                "RAG_DOCS_DIR": temp_dir,
                "RAG_MANAGED_DOCS_DIR": temp_dir,
                "OPERATOR_AUTH_STATE": str(Path(temp_dir) / "operators.json"),
                "ENDPOINT_STATE_FILE": str(Path(temp_dir) / "devices.json"),
            }
            
            with patch.dict(os.environ, env, clear=True):
                config = server.build_config()
                console = server.WebServer(config)
            
            gateway = device_gateway.DeviceGatewayServer(
                "127.0.0.1", 0, str(cert_path), str(key_path), console, 60
            )
            gateway_host, gateway_port = gateway.server_address[:2]
            
            gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            gateway_thread.start()
            time.sleep(0.1)
            
            try:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                # Test negative Content-Length
                url = f"https://{gateway_host}:{gateway_port}/api/devices/enroll"
                req = urllib.request.Request(url, method="POST")
                req.add_header("Content-Length", "-1")
                
                try:
                    urllib.request.urlopen(req, context=ssl_context, timeout=2)
                    self.fail("Should return 400")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 400)
                
                # Test non-integer Content-Length
                req = urllib.request.Request(url, method="POST")
                req.add_header("Content-Length", "abc")
                
                try:
                    urllib.request.urlopen(req, context=ssl_context, timeout=2)
                    self.fail("Should return 400")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 400)
            finally:
                gateway.shutdown()
                gateway.server_close()
                console.server_close()
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
        finally:
            cert_path.unlink(missing_ok=True)
            key_path.unlink(missing_ok=True)


class TestConsoleSecurityChecks(unittest.TestCase):
    """Test console security against fake gateway requests."""

    def test_console_handler_not_treated_as_gateway_with_headers(self) -> None:
        """Console request cannot fake gateway status with headers or attributes."""
        temp_dir = tempfile.mkdtemp()
        try:
            api_key_file = Path(temp_dir) / "api.key"
            api_key_file.write_text("test-key-0123456789abcdef0123456789")
            
            env = {
                "WEB_HOST": "127.0.0.1",
                "WEB_PORT": "0",
                "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010",
                "PLATFORM_API_KEY_FILE": str(api_key_file),
                "RAG_DOCS_DIR": temp_dir,
                "RAG_MANAGED_DOCS_DIR": temp_dir,
                "OPERATOR_AUTH_STATE": str(Path(temp_dir) / "operators.json"),
                "ENDPOINT_STATE_FILE": str(Path(temp_dir) / "devices.json"),
            }
            
            with patch.dict(os.environ, env, clear=True):
                config = server.build_config()
                httpd = server.WebServer(config)
            
            # Create a handler manually without going through __init__
            from io import BytesIO
            import http.client
            
            handler = server.Handler.__new__(server.Handler)
            handler.request = unittest.mock.MagicMock()
            handler.client_address = ("10.0.0.5", 12345)
            handler.server = httpd
            handler.headers = http.client.HTTPMessage()
            
            # Class attribute should be False
            self.assertFalse(server.Handler._is_gateway_request)
            
            # Instance should also have False (inherited from class)
            self.assertFalse(handler._is_gateway_request)
            
            # _loopback_or_gateway should return False for non-loopback without gateway flag
            self.assertFalse(handler._loopback_or_gateway())
            
            httpd.server_close()
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_console_device_routes_refuse_non_loopback_plain_http(self) -> None:
        """Console device routes refuse non-loopback client over plain HTTP."""
        temp_dir = tempfile.mkdtemp()
        try:
            api_key_file = Path(temp_dir) / "api.key"
            api_key_file.write_text("test-key-0123456789abcdef0123456789")
            
            env = {
                "WEB_HOST": "127.0.0.1",
                "WEB_PORT": "0",
                "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010",
                "PLATFORM_API_KEY_FILE": str(api_key_file),
                "RAG_DOCS_DIR": temp_dir,
                "RAG_MANAGED_DOCS_DIR": temp_dir,
                "OPERATOR_AUTH_STATE": str(Path(temp_dir) / "operators.json"),
                "ENDPOINT_STATE_FILE": str(Path(temp_dir) / "devices.json"),
            }
            
            with patch.dict(os.environ, env, clear=True):
                config = server.build_config()
                httpd = server.WebServer(config)
            
            # Test several device routes
            from io import BytesIO
            import http.client
            
            device_routes = [
                ("/api/devices/enroll", "POST", b'{"enrolment_code":"test","hostname":"test"}'),
                ("/api/devices/report", "POST", b'{"data":"test"}'),
                ("/api/remote-work/poll", "POST", b""),
                ("/api/remote-work/claim", "POST", b'{"order_id":"test"}'),
                ("/api/remote-work/complete", "POST", b'{"order_id":"test","outcome":"success"}'),
                ("/api/remote-work/heartbeat", "POST", b""),
            ]
            
            for path, method, body in device_routes:
                # Create handler with non-loopback address
                mock_socket = unittest.mock.MagicMock()
                request_line = f"{method} {path} HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n"
                mock_socket.makefile = lambda mode: BytesIO(request_line.encode() + body)
                
                handler = server.Handler.__new__(server.Handler)
                handler.request = mock_socket
                handler.client_address = ("192.168.1.100", 54321)  # Non-loopback
                handler.server = httpd
                handler.command = method
                handler.path = path
                handler.request_version = "HTTP/1.1"
                handler.headers = http.client.HTTPMessage()
                handler.headers["Content-Length"] = str(len(body))
                handler.rfile = BytesIO(body)
                handler.wfile = BytesIO()
                handler.close_connection = True
                handler.requestline = f"{method} {path} HTTP/1.1"
                
                # Should refuse with 403
                result_sent = False
                def mock_send_error_json(code, msg, error_id=None):
                    nonlocal result_sent
                    result_sent = True
                    self.assertEqual(code, 403, f"{path} should return 403 for non-loopback")
                
                handler.send_error_json = mock_send_error_json
                
                # Call the handler
                if path == "/api/devices/enroll":
                    handler.handle_device_enroll()
                elif path == "/api/devices/report":
                    handler.handle_device_report()
                elif path == "/api/remote-work/poll":
                    handler.handle_remote_work_poll()
                elif path == "/api/remote-work/claim":
                    handler.handle_remote_work_claim()
                elif path == "/api/remote-work/complete":
                    handler.handle_remote_work_complete()
                elif path == "/api/remote-work/heartbeat":
                    handler.handle_remote_work_heartbeat()
                
                self.assertTrue(result_sent, f"{path} should have refused the request")
            
            httpd.server_close()
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_repair_device_bearer_check_refuses_non_loopback_plain_http(self) -> None:
        """_device_bearer refuses non-loopback plain HTTP, accepts TLS."""
        temp_dir = tempfile.mkdtemp()
        try:
            api_key_file = Path(temp_dir) / "api.key"
            api_key_file.write_text("test-key-0123456789abcdef0123456789")
            
            env = {
                "WEB_HOST": "127.0.0.1",
                "WEB_PORT": "0",
                "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010",
                "PLATFORM_API_KEY_FILE": str(api_key_file),
                "RAG_DOCS_DIR": temp_dir,
                "RAG_MANAGED_DOCS_DIR": temp_dir,
                "OPERATOR_AUTH_STATE": str(Path(temp_dir) / "operators.json"),
                "ENDPOINT_STATE_FILE": str(Path(temp_dir) / "devices.json"),
            }
            
            with patch.dict(os.environ, env, clear=True):
                config = server.build_config()
                httpd = server.WebServer(config)
            
            from io import BytesIO
            import http.client
            
            # Test non-loopback plain HTTP is refused
            handler = server.Handler.__new__(server.Handler)
            handler.request = unittest.mock.MagicMock()
            # No context attribute - simulates plain HTTP
            handler.request.context = None
            handler.client_address = ("192.168.1.100", 54321)
            handler.server = httpd
            handler.headers = http.client.HTTPMessage()
            handler.headers["Authorization"] = "Bearer test-secret-123"
            handler.wfile = BytesIO()
            
            result_sent = False
            def mock_send_error_json(code, msg, error_id=None):
                nonlocal result_sent
                result_sent = True
                self.assertEqual(code, 403)
                self.assertIn("plain HTTP", msg)
            
            handler.send_error_json = mock_send_error_json
            
            # _device_bearer should refuse
            result = handler._device_bearer()
            self.assertIsNone(result)
            self.assertTrue(result_sent)
            
            # Test TLS connection (simulated with ssl_context attribute on request)
            handler2 = server.Handler.__new__(server.Handler)
            mock_request2 = unittest.mock.MagicMock()
            mock_request2.context = unittest.mock.MagicMock()  # Simulates SSL
            handler2.request = mock_request2
            handler2.client_address = ("192.168.1.100", 54321)
            handler2.server = httpd
            handler2.headers = http.client.HTTPMessage()
            handler2.headers["Authorization"] = "Bearer test-secret-456"
            handler2.wfile = BytesIO()
            handler2.send_error_json = lambda *args: None
            
            # Should accept (returns the bearer token)
            result = handler2._device_bearer()
            self.assertEqual(result, "test-secret-456")
            
            httpd.server_close()
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
