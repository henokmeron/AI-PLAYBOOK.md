"""Remote IT work HTTP routes refuse callers who are not authenticated.

These tests start the loopback console only. They do not set
REMOTE_IT_WORK_LIVE, pass live execution, or contact a laptop.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server

from integrations.remote_work import default_runner_invocations, snapshot

KEY = "unit-test-only-not-a-gateway-secret-0123456789"
SECRET = "unit-test-device-secret-not-live-0123456789abcdef"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPHandler())


class RemoteWorkHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self._live = os.environ.pop("REMOTE_IT_WORK_LIVE", None)
        self._endpoint = os.environ.get("ENDPOINT_STATE_FILE")
        self._auth = os.environ.get("OPERATOR_AUTH_DIR")
        self._dirs: list[tempfile.TemporaryDirectory[str]] = []
        auth_dir = tempfile.TemporaryDirectory(prefix="remote-it-auth-")
        state_dir = tempfile.TemporaryDirectory(prefix="remote-it-devices-")
        self._dirs.extend((auth_dir, state_dir))
        os.environ["OPERATOR_AUTH_DIR"] = auth_dir.name
        os.environ["ENDPOINT_STATE_FILE"] = str(Path(state_dir.name) / "devices.json")
        from auth.service import AuthService

        auth = AuthService(auth_dir.name)
        auth.create_operator(
            "admin", "unit-test-admin-password", "admin", allow_first_admin=True, actor="test",
        )
        # A second operator with the same role approves, because the operator
        # who raised an order may not approve it.
        auth.create_operator("approver", "unit-test-approver-password", "admin", actor="admin")
        self.httpd = server.WebServer(server.Config(
            host="127.0.0.1",
            port=0,
            gateway_url="http://127.0.0.1:9",
            model_id="unit-test-model",
            api_key=KEY,
            upstream_timeout=5,
            health_timeout=1,
        ))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.cookie = ""
        self.csrf = ""
        created = self.httpd.devices.create_enrolment("local-console")
        self.device_id = self.httpd.devices.enrol(created["enrolment_code"], "Lab Laptop", SECRET)

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        for item in self._dirs:
            item.cleanup()
        if self._auth is None:
            os.environ.pop("OPERATOR_AUTH_DIR", None)
        else:
            os.environ["OPERATOR_AUTH_DIR"] = self._auth
        if self._endpoint is None:
            os.environ.pop("ENDPOINT_STATE_FILE", None)
        else:
            os.environ["ENDPOINT_STATE_FILE"] = self._endpoint
        if self._live is None:
            os.environ.pop("REMOTE_IT_WORK_LIVE", None)
        else:
            os.environ["REMOTE_IT_WORK_LIVE"] = self._live

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        auth: bool = False,
        bearer: str | None = None,
    ) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if auth and self.cookie:
            headers["Cookie"] = self.cookie
            headers["Origin"] = self.base
            if self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        elif method == "POST":
            headers["Origin"] = self.base
        if bearer is not None:
            headers["Authorization"] = "Bearer " + bearer
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with OPENER.open(request, timeout=20) as response:
                status = int(response.getcode())
                raw = response.read()
                header_map = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read()
            header_map = dict(exc.headers.items()) if exc.headers else {}
        if path == "/api/auth/login" and status == 200:
            body = json.loads(raw.decode("utf-8") or "{}")
            cookie = header_map.get("Set-Cookie") or header_map.get("set-cookie") or ""
            self.cookie = cookie.split(";", 1)[0]
            self.csrf = str(body.get("csrf_token") or "")
            return status, body
        return status, json.loads(raw.decode("utf-8") or "{}")

    def test_missing_auth_is_refused_and_a_real_secret_is_not_stored(self) -> None:
        order_body = {
            "device_id": self.device_id,
            "action": "repair.service.restart",
            "target": "Spooler",
            "params": {"start_type": "automatic", "status": "stopped"},
        }
        for path in ("/api/remote-work/orders", "/api/remote-work/approve"):
            status, body = self.request("POST", path, order_body if path.endswith("orders") else {"order_id": "missing"})
            self.assertEqual(status, 401, path)
            self.assertEqual(body["error"], "authentication required")
        for path, payload in (
            ("/api/remote-work/poll", {}),
            ("/api/remote-work/claim", {"order_id": "missing"}),
            ("/api/remote-work/complete", {"order_id": "missing", "outcome": "succeeded"}),
            ("/api/remote-work/heartbeat", {"utc": "2026-10-23T23:00:00Z", "worker_version": "2026.10.23"}),
        ):
            status, body = self.request("POST", path, payload)
            self.assertEqual(status, 401, path)
            self.assertEqual(body["error"], "device authentication required")
        self.assertEqual(self.httpd.remote_work_store.orders, {})

        status, logged_in = self.request(
            "POST", "/api/auth/login",
            {"username": "admin", "password": "unit-test-admin-password"},
        )
        self.assertEqual(status, 200, logged_in)
        status, created = self.request("POST", "/api/remote-work/orders", order_body, auth=True)
        self.assertEqual(status, 200, created)
        self.assertEqual(created["state"], "pending_approval")
        self.assertNotIn(SECRET, json.dumps(created))
        self.assertNotIn(SECRET, json.dumps(snapshot(self.httpd.remote_work_store)))

        status, rejected = self.request(
            "POST", "/api/remote-work/orders",
            {**order_body, "device_secret": SECRET},
            auth=True,
        )
        self.assertEqual(status, 400, rejected)
        self.assertEqual(rejected["state"], "refused")
        self.assertNotIn(SECRET, json.dumps(snapshot(self.httpd.remote_work_store)))

        wrong, wrong_body = self.request("POST", "/api/remote-work/poll", {}, bearer="f" * 40)
        self.assertEqual(wrong, 401)
        self.assertEqual(wrong_body["state"], "refused")
        self.assertEqual(wrong_body["error"], "device secret was rejected")
        backdoor, backdoor_body = self.request("POST", "/api/remote-work/poll", {}, bearer=KEY)
        self.assertEqual(backdoor, 401)
        self.assertEqual(backdoor_body["state"], "refused")

        status, own = self.request(
            "POST", "/api/remote-work/approve",
            {"order_id": created["id"]},
            auth=True,
        )
        self.assertEqual(status, 403, own)
        self.assertEqual(own["state"], "refused")
        self.assertEqual(own["error"], "the operator who raised an order cannot approve it")

        status, _ = self.request(
            "POST", "/api/auth/login",
            {"username": "approver", "password": "unit-test-approver-password"},
        )
        self.assertEqual(status, 200)
        status, approved = self.request(
            "POST", "/api/remote-work/approve",
            {"order_id": created["id"]},
            auth=True,
        )
        self.assertEqual(status, 200, approved)
        self.assertEqual(approved["state"], "approved")
        status, polled = self.request("POST", "/api/remote-work/poll", {}, bearer=SECRET)
        self.assertEqual(status, 200, polled)
        self.assertEqual([item["id"] for item in polled["jobs"]], [created["id"]])
        self.assertNotIn(SECRET, json.dumps(polled))
        report = self.httpd.devices.public_report("local-console", self.device_id)
        self.assertEqual(report["status"], "none")

        status, beat = self.request(
            "POST", "/api/remote-work/heartbeat",
            {"utc": "2026-10-23T23:00:00Z", "worker_version": "2026.10.23"},
            bearer=SECRET,
        )
        self.assertEqual(status, 200, beat)
        self.assertEqual(set(beat), {"device_id", "utc", "worker_version"})
        self.assertEqual(beat["device_id"], self.device_id)
        self.assertNotIn(SECRET, json.dumps(snapshot(self.httpd.remote_work_store)))
        self.assertNotEqual(os.environ.get("REMOTE_IT_WORK_LIVE"), "1")
        self.assertEqual(default_runner_invocations(), 0)


if __name__ == "__main__":
    unittest.main()
