#!/usr/bin/env python3
"""Named-operator authentication and authorization checks for the console."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server
from auth.permissions import Permission, Role, permissions_for
from auth.service import AuthError, AuthService, COOKIE_NAME, CSRF_HEADER

KEY = "unit-test-only-not-a-gateway-secret-0123456789"
MODEL = "qwen3.5-27b"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPHandler())
ADMIN_PASSWORD = "unit-test-admin-password"
VIEWER_PASSWORD = "unit-test-viewer-password"


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.servers: list[ThreadingHTTPServer] = []
        self._auth_dirs: list[tempfile.TemporaryDirectory] = []
        self._prev = os.environ.get("OPERATOR_AUTH_DIR")
        self.cookie = ""
        self.csrf = ""

    def tearDown(self) -> None:
        for item in self.servers:
            item.shutdown()
        for item in self.servers:
            item.server_close()
        for tmp in self._auth_dirs:
            tmp.cleanup()
        if self._prev is None:
            os.environ.pop("OPERATOR_AUTH_DIR", None)
        else:
            os.environ["OPERATOR_AUTH_DIR"] = self._prev

    def _auth_dir(self) -> str:
        tmp = tempfile.TemporaryDirectory(prefix="auth-test-")
        self._auth_dirs.append(tmp)
        os.environ["OPERATOR_AUTH_DIR"] = tmp.name
        return tmp.name

    def start_console(self, *, provision: bool = True) -> tuple[str, AuthService]:
        directory = self._auth_dir()
        service = AuthService(directory)
        if provision:
            service.create_operator("admin", ADMIN_PASSWORD, "admin", allow_first_admin=True, actor="test")
        httpd = server.WebServer(server.Config(
            host="127.0.0.1",
            port=0,
            gateway_url="http://127.0.0.1:9",
            model_id=MODEL,
            api_key=KEY,
            upstream_timeout=5,
            health_timeout=1,
        ))
        self.servers.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{httpd.server_address[1]}", service

    def call(
        self,
        base: str,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        cookie: str | None = None,
        csrf: str | None = None,
        origin: str | None = None,
        headers: dict | None = None,
        follow_redirects: bool = True,
    ) -> tuple[int, dict, dict[str, str]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        hdrs = dict(headers or {})
        if data is not None:
            hdrs.setdefault("Content-Type", "application/json")
        if cookie:
            hdrs["Cookie"] = cookie
        if csrf:
            hdrs[CSRF_HEADER] = csrf
        if origin is not None:
            hdrs["Origin"] = origin
        elif method in {"POST", "PUT", "DELETE", "PATCH"}:
            hdrs.setdefault("Origin", base)
        request = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
        opener = OPENER
        if not follow_redirects:
            class _NoRedirect(urllib.request.HTTPErrorProcessor):
                def http_response(self, request, response):  # type: ignore[no-untyped-def]
                    return response

                https_response = http_response

            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        try:
            with opener.open(request, timeout=5) as response:
                raw = response.read()
                body = json.loads(raw.decode("utf-8") or "{}") if raw else {}
                return int(response.getcode()), body, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                body = {"error": raw.decode("utf-8", errors="replace")}
            return exc.code, body, dict(exc.headers.items()) if exc.headers else {}

    def login(self, base: str, username: str = "admin", password: str = ADMIN_PASSWORD) -> tuple[str, str]:
        status, body, headers = self.call(
            base, "POST", "/api/auth/login",
            {"username": username, "password": password},
            origin=base,
        )
        self.assertEqual(status, 200, body)
        cookie = (headers.get("Set-Cookie") or "").split(";", 1)[0]
        self.assertTrue(cookie.startswith(COOKIE_NAME + "="))
        csrf = str(body["csrf_token"])
        self.cookie, self.csrf = cookie, csrf
        return cookie, csrf

    def test_anonymous_privileged_api_denied(self) -> None:
        base, _ = self.start_console()
        status, body, _ = self.call(base, "GET", "/api/ops/overview")
        self.assertEqual(status, 401)
        self.assertEqual(body.get("error"), "authentication required")

    def test_fail_closed_without_operators(self) -> None:
        base, _ = self.start_console(provision=False)
        status, body, _ = self.call(base, "GET", "/api/ops/overview")
        self.assertEqual(status, 503)
        self.assertIn("not configured", body.get("error", ""))

    def test_bad_login_no_enumeration(self) -> None:
        base, _ = self.start_console()
        status_a, body_a, _ = self.call(
            base, "POST", "/api/auth/login",
            {"username": "admin", "password": "wrong-password-12"},
            origin=base,
        )
        status_b, body_b, _ = self.call(
            base, "POST", "/api/auth/login",
            {"username": "nosuchuser", "password": "wrong-password-12"},
            origin=base,
        )
        self.assertEqual(status_a, 401)
        self.assertEqual(status_b, 401)
        self.assertEqual(body_a.get("error"), body_b.get("error"))

    def test_disabled_login_matches_unknown_user(self) -> None:
        directory = self._auth_dir()
        service = AuthService(directory)
        service.create_operator("admin", ADMIN_PASSWORD, "admin", allow_first_admin=True, actor="test")
        service.create_operator("tempops", VIEWER_PASSWORD, "operator", actor="admin")
        service.set_disabled("tempops", True, actor="admin")
        with self.assertRaises(AuthError) as disabled:
            service.login("tempops", VIEWER_PASSWORD, peer_ip="127.0.0.1")
        with self.assertRaises(AuthError) as missing:
            service.login("nosuchuser", VIEWER_PASSWORD, peer_ip="127.0.0.1")
        self.assertEqual(disabled.exception.status, 401)
        self.assertEqual(disabled.exception.message, missing.exception.message)

    def test_create_refused_when_no_active_admin_remains(self) -> None:
        directory = self._auth_dir()
        service = AuthService(directory)
        service.create_operator("admin", ADMIN_PASSWORD, "admin", allow_first_admin=True, actor="test")
        admin = service.store.by_username("admin")
        assert admin is not None
        admin.disabled = True
        with self.assertRaises(AuthError) as exc:
            service.create_operator("other", VIEWER_PASSWORD, "operator", actor="admin")
        self.assertIn("active administrator", exc.exception.message)

    def test_session_cookie_and_me_status(self) -> None:
        base, _ = self.start_console()
        cookie, csrf = self.login(base)
        status, body, _ = self.call(base, "GET", "/api/auth/status", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["username"], "admin")
        self.assertEqual(body["role"], "admin")
        self.assertEqual(body["csrf_token"], csrf)
        self.assertIn(Permission.ADMIN_OPERATORS.value, body["permissions"])

    def test_session_rotation(self) -> None:
        base, _ = self.start_console()
        cookie, csrf = self.login(base)
        old_id = cookie.split("=", 1)[1]
        status, body, headers = self.call(
            base, "POST", "/api/auth/rotate", {}, cookie=cookie, csrf=csrf, origin=base,
        )
        self.assertEqual(status, 200)
        new_cookie = (headers.get("Set-Cookie") or "").split(";", 1)[0]
        new_id = new_cookie.split("=", 1)[1]
        self.assertNotEqual(old_id, new_id)
        self.assertNotEqual(csrf, body["csrf_token"])
        status_old, _, _ = self.call(base, "GET", "/api/ops/coverage", cookie=cookie)
        self.assertEqual(status_old, 401)
        status_new, _, _ = self.call(base, "GET", "/api/ops/coverage", cookie=new_cookie)
        self.assertEqual(status_new, 200)

    def test_logout_revokes_session(self) -> None:
        base, _ = self.start_console()
        cookie, csrf = self.login(base)
        status, _, _ = self.call(
            base, "POST", "/api/auth/logout", {}, cookie=cookie, csrf=csrf, origin=base,
        )
        self.assertEqual(status, 200)
        status, body, _ = self.call(base, "GET", "/api/ops/overview", cookie=cookie)
        self.assertEqual(status, 401)

    def test_idle_expiry(self) -> None:
        directory = self._auth_dir()
        clock = {"now": 1_000_000.0}

        def now() -> float:
            return clock["now"]

        service = AuthService(directory, idle_seconds=300, absolute_seconds=3600, clock=now)
        service.create_operator("admin", ADMIN_PASSWORD, "admin", allow_first_admin=True, actor="test")
        session = service.login("admin", ADMIN_PASSWORD, peer_ip="127.0.0.1")
        self.assertIsNotNone(service.validate_session(session.session_id))
        clock["now"] += 301
        self.assertIsNone(service.validate_session(session.session_id))

    def test_rbac_viewer_cannot_manage_connectors(self) -> None:
        directory = self._auth_dir()
        service = AuthService(directory)
        service.create_operator("admin", ADMIN_PASSWORD, "admin", allow_first_admin=True, actor="test")
        service.create_operator("viewer1", VIEWER_PASSWORD, "viewer", actor="admin")
        httpd = server.WebServer(server.Config(
            host="127.0.0.1",
            port=0,
            gateway_url="http://127.0.0.1:9",
            model_id=MODEL,
            api_key=KEY,
            upstream_timeout=5,
            health_timeout=1,
        ))
        self.servers.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        cookie, csrf = self.login(base, "viewer1", VIEWER_PASSWORD)
        status, body, _ = self.call(
            base, "POST", "/api/microsoft/disconnect", {}, cookie=cookie, csrf=csrf, origin=base,
        )
        self.assertEqual(status, 403)
        self.assertEqual(body.get("error"), "permission denied")
        status_ok, _, _ = self.call(base, "GET", "/api/connectors", cookie=cookie)
        self.assertEqual(status_ok, 200)

    def test_foreign_origin_is_rejected(self) -> None:
        base, _service = self.start_console()
        status, body, _headers = self.call(
            base,
            "POST",
            "/api/auth/login",
            {"username": "admin", "password": ADMIN_PASSWORD},
            origin="https://evil.example",
        )
        self.assertEqual(status, 403)
        self.assertIn("origin", body.get("error", ""))

    def test_foreign_host_is_rejected(self) -> None:
        base, _service = self.start_console()
        status, body, _headers = self.call(
            base, "GET", "/api/auth/status", headers={"Host": "evil.example"},
        )
        self.assertEqual(status, 403)
        self.assertIn("host not allowed", body.get("error", ""))
        status, body, _headers = self.call(
            base, "GET", "/api/auth/status", headers={"Host": "localhost:evil"},
        )
        self.assertEqual(status, 403)
        self.assertIn("host not allowed", body.get("error", ""))
        status, _body, _headers = self.call(
            base, "GET", "/api/auth/status", headers={"Host": "127.0.0.1:18080"},
        )
        self.assertEqual(status, 200)

    def test_microsoft_start_rejects_other_port_browser(self) -> None:
        """Another process on this machine must not start Microsoft sign-in with the operator cookie."""
        base, _service = self.start_console()
        cookie, _csrf = self.login(base)
        status, body, headers = self.call(
            base,
            "GET",
            "/api/microsoft/start",
            cookie=cookie,
            headers={"Sec-Fetch-Site": "same-site"},
            follow_redirects=False,
        )
        self.assertEqual(status, 403, body)
        self.assertNotIn("location", {key.casefold() for key in headers})
        allowed, allowed_body, _allowed_headers = self.call(
            base,
            "GET",
            "/api/microsoft/start",
            cookie=cookie,
            headers={"Sec-Fetch-Site": "same-origin"},
            follow_redirects=False,
        )
        self.assertNotEqual(allowed, 403, allowed_body)
        self.assertIn(allowed, {302, 400, 409})

    def test_ops_overview_rejects_cross_site_fetch(self) -> None:
        """Health, overview, and director GETs write audit state and must not run for a foreign fetch."""
        previous = os.environ.get("OPS_CENTRE_DIR")
        isolated = tempfile.TemporaryDirectory(prefix="ops-fetch-")
        os.environ["OPS_CENTRE_DIR"] = isolated.name
        try:
            base, _service = self.start_console()
            cookie, _csrf = self.login(base)
            ops = self.servers[-1].ops  # type: ignore[attr-defined]
            ops.health.snapshot = lambda: {
                "overall": "unavailable",
                "verification": "observed",
                "verified_at": "2026-10-22T12:00:00Z",
                "services": [{
                    "name": "disk",
                    "state": "unavailable",
                    "detail": "unit",
                    "check_kind": "local",
                    "latency_ms": 1,
                    "http_status": 0,
                }],
            }
            before = [event.event_id for event in ops.events.list(limit=500)]
            self.assertTrue(before)
            for path in ("/api/ops/overview", "/api/ops/health", "/api/ops/director"):
                for site in ("cross-site", "same-site"):
                    status, body, _headers = self.call(
                        base,
                        "GET",
                        path,
                        cookie=cookie,
                        headers={"Sec-Fetch-Site": site},
                    )
                    self.assertEqual(status, 403, (path, site, body))
                    self.assertEqual(body.get("error"), "this action must start from this console")
            self.assertEqual([event.event_id for event in ops.events.list(limit=500)], before)
            allowed, allowed_body, _allowed_headers = self.call(
                base,
                "GET",
                "/api/ops/overview",
                cookie=cookie,
                headers={"Sec-Fetch-Site": "same-origin"},
            )
            self.assertEqual(allowed, 200, allowed_body)
            after = ops.events.list(limit=500)
            self.assertGreater(len(after), len(before))
            self.assertIn("health.probe", [event.event_type for event in after])
        finally:
            if previous is None:
                os.environ.pop("OPS_CENTRE_DIR", None)
            else:
                os.environ["OPS_CENTRE_DIR"] = previous
            isolated.cleanup()

    def test_csrf_required_on_mutating(self) -> None:
        base, _ = self.start_console()
        cookie, _csrf = self.login(base)
        status, body, _ = self.call(
            base, "POST", "/api/ops/refresh", {}, cookie=cookie, csrf="", origin=base,
        )
        self.assertEqual(status, 403)
        self.assertIn("CSRF", body.get("error", ""))

    def test_login_rate_limit(self) -> None:
        base, _ = self.start_console()
        for _ in range(10):
            self.call(
                base, "POST", "/api/auth/login",
                {"username": "admin", "password": "wrong-password-12"},
                origin=base,
            )
        status, body, _ = self.call(
            base, "POST", "/api/auth/login",
            {"username": "admin", "password": "wrong-password-12"},
            origin=base,
        )
        self.assertEqual(status, 429)
        self.assertIn("Try again later", body.get("error", ""))

    def test_audit_actor_on_login(self) -> None:
        events: list[dict] = []

        def record(**kwargs):  # type: ignore[no-untyped-def]
            events.append(kwargs)

        directory = self._auth_dir()
        service = AuthService(directory, record_event=record)
        service.create_operator("admin", ADMIN_PASSWORD, "admin", allow_first_admin=True, actor="provision")
        service.login("admin", ADMIN_PASSWORD, peer_ip="127.0.0.1")
        successes = [e for e in events if e.get("event_type") == "auth.login_succeeded"]
        self.assertEqual(len(successes), 1)
        self.assertEqual(successes[0]["actor"], "admin")

    def test_ops_actor_comes_from_session_not_json(self) -> None:
        from ops_centre.models import Alert

        base, _service = self.start_console()
        cookie, csrf = self.login(base)
        ops = self.servers[-1].ops  # type: ignore[attr-defined]
        alert = Alert(
            alert_id="alert-actor-test",
            rule_id="unit.test",
            rule_version="1",
            title="actor check",
            severity="low",
            status="new",
            created_at="2026-10-17T00:00:00Z",
            updated_at="2026-10-17T00:00:00Z",
            fingerprint="unit-actor",
        )
        ops.alerts._alerts[alert.alert_id] = alert  # noqa: SLF001 — test fixture
        status, body, _ = self.call(
            base,
            "POST",
            "/api/ops/alerts/transition",
            {
                "alert_id": alert.alert_id,
                "status": "acknowledged",
                "actor": "spoofed-json-actor",
                "note": "should ignore json actor",
            },
            cookie=cookie,
            csrf=csrf,
            origin=base,
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body.get("owner"), "admin")
        timeline = ops.timeline(limit=40, event_type="ops.alert_transition")
        rows = timeline.get("events") if isinstance(timeline, dict) else []
        actors = [row.get("actor") for row in rows if isinstance(row, dict)]
        self.assertIn("admin", actors)
        self.assertNotIn("spoofed-json-actor", actors)

    def test_protected_api_with_session(self) -> None:
        base, _ = self.start_console()
        cookie, _ = self.login(base)
        status, body, _ = self.call(base, "GET", "/api/ops/coverage", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn("coverage", body)

    def test_health_status_public(self) -> None:
        base, _ = self.start_console()
        status, body, _ = self.call(base, "GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertIn("connection", body)
        status_auth, auth_body, _ = self.call(base, "GET", "/api/auth/status")
        self.assertEqual(status_auth, 200)
        self.assertFalse(auth_body["authenticated"])
        self.assertTrue(auth_body["configured"])

    def test_oauth_callback_remains_public(self) -> None:
        base, _ = self.start_console()
        request = urllib.request.Request(base + "/api/microsoft/callback?error=access_denied")
        with OPENER.open(request, timeout=5) as response:
            self.assertEqual(response.getcode(), 200)
            text = response.read().decode("utf-8")
        self.assertIn("cancelled", text.lower())

    def test_role_permission_matrix(self) -> None:
        viewer = permissions_for(Role.VIEWER)
        operator = permissions_for(Role.OPERATOR)
        admin = permissions_for(Role.ADMIN)
        self.assertIn(Permission.OPS_VIEW, viewer)
        self.assertNotIn(Permission.OPS_ALERT_WRITE, viewer)
        self.assertIn(Permission.OPS_ALERT_WRITE, operator)
        self.assertNotIn(Permission.ADMIN_OPERATORS, operator)
        self.assertIn(Permission.ADMIN_OPERATORS, admin)

    def test_viewer_cannot_execute_a_repair(self) -> None:
        directory = self._auth_dir()
        bootstrap = AuthService(directory)
        bootstrap.create_operator("admin", ADMIN_PASSWORD, "admin", allow_first_admin=True, actor="test")
        bootstrap.create_operator("viewer", VIEWER_PASSWORD, "viewer", actor="admin")
        httpd = server.WebServer(server.Config(
            host="127.0.0.1", port=0, gateway_url="http://127.0.0.1:9",
            model_id=MODEL, api_key=KEY, upstream_timeout=5, health_timeout=1,
        ))
        self.servers.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        cookie, csrf = self.login(base, "viewer", VIEWER_PASSWORD)
        status, body, _ = self.call(
            base, "POST", "/api/repair/execute",
            {"procedure_id": "net.firewall.disable"},
            cookie=cookie, csrf=csrf, origin=base,
        )
        self.assertEqual(status, 403)
        self.assertIn("permission", body.get("error", ""))

    def test_disabled_operator_session_rejected(self) -> None:
        directory = self._auth_dir()
        bootstrap = AuthService(directory)
        bootstrap.create_operator("admin", ADMIN_PASSWORD, "admin", allow_first_admin=True, actor="test")
        bootstrap.create_operator("tempops", VIEWER_PASSWORD, "operator", actor="admin")
        httpd = server.WebServer(server.Config(
            host="127.0.0.1",
            port=0,
            gateway_url="http://127.0.0.1:9",
            model_id=MODEL,
            api_key=KEY,
            upstream_timeout=5,
            health_timeout=1,
        ))
        self.servers.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        cookie, csrf = self.login(base, "tempops", VIEWER_PASSWORD)
        httpd.auth.set_disabled("tempops", True, actor="admin")
        status, _, _ = self.call(base, "GET", "/api/ops/overview", cookie=cookie)
        self.assertEqual(status, 401)
        self.call(base, "POST", "/api/auth/logout", {}, cookie=cookie, csrf=csrf, origin=base)


if __name__ == "__main__":
    unittest.main()
