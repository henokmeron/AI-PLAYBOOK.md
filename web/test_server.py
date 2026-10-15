#!/usr/bin/env python3
"""Checks for the loopback web console and its gateway proxy."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server

KEY = "unit-test-only-not-a-gateway-secret-0123456789"
MODEL = "/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPHandler())


class FakeGatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format_string: str, *args: object) -> None:
        return

    def _record(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        entry = {
            "method": self.command,
            "path": urlsplit(self.path).path,
            "authorization": self.headers.get("Authorization") or "",
            "body": raw.decode("utf-8"),
        }
        with self.server.lock:
            self.server.hits.append(entry)
        return entry

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        entry = self._record()
        if urlsplit(self.path).path == "/v1/rag/documents":
            if entry["authorization"] != f"Bearer {self.server.key}":
                self._json(401, {"error": "authentication required"})
                return
            self._json(200, {"collection": "my-docs", "documents": [{"filename": "policy.md", "size_bytes": 22, "extension": ".md"}]})
            return
        path = urlsplit(self.path).path
        if path == "/v1/platform/models":
            if entry["authorization"] != f"Bearer {self.server.key}":
                self._json(401, {"error": "authentication required"})
                return
            self._json(200, {
                "models": [
                    {
                        "id": "qwen3.5-27b",
                        "selection_eligible": True,
                        "runtime_loaded": True,
                        "is_production_default": True,
                        "is_active_default": True,
                        "listen_port": 8002,
                    },
                    {
                        "id": "gemma-4-31b-it",
                        "selection_eligible": True,
                        "runtime_loaded": False,
                        "is_production_default": False,
                        "is_active_default": False,
                        "listen_port": 8000,
                    },
                ],
                "upstream_port": 8002,
            })
            return
        if path != "/health":
            self._json(404, {"error": "not found"})
            return
        if self.server.health_code == 503:
            self._json(503, {"status": "degraded", "upstream": "unavailable"})
            return
        self._json(200, {"status": "ok", "upstream": "ok", "model_count": 1, "secret": self.server.key})

    def do_DELETE(self) -> None:
        entry = self._record()
        if entry["authorization"] != f"Bearer {self.server.key}":
            self._json(401, {"error": "authentication required"})
            return
        if entry["path"] == "/v1/rag/documents":
            self._json(200, {
                "deleted": True,
                "removed_from_index": True,
                "indexed_sources": [],
            })
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        entry = self._record()
        if self.server.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", self.server.redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if entry["authorization"] != f"Bearer {self.server.key}":
            self._json(401, {"error": "authentication required"})
            return
        if self.server.mode == "reflect-key":
            self._json(500, {"error": f"boom {self.server.key}"})
            return
        if entry["path"] == "/v1/chat/completions":
            payload = json.loads(entry["body"])
            self._json(200, {
                "model": payload.get("model"),
                "choices": [{"message": {"role": "assistant", "content": "gateway works"}}],
            })
            return
        if entry["path"] == "/v1/rag/documents":
            payload = json.loads(entry["body"])
            self._json(201, {
                "status": "stored",
                "document": {
                    "collection": payload["collection"],
                    "filename": payload["filename"],
                    "size_bytes": 12,
                    "extension": ".md",
                    "searchable": True,
                    "chunk_count": 1,
                    "indexed_sources": [payload["filename"]],
                },
            })
            return
        if entry["path"] == "/v1/rag/ask":
            payload = json.loads(entry["body"])
            history = payload.get("history") or []
            if "yacht" in payload.get("question", "").lower():
                self._json(200, {
                    "status": "abstained",
                    "answer": "No sufficiently relevant evidence was found in the supplied documents.",
                    "sources": [],
                    "retrieval": {"matched": True, "reason": "below_min_score", "top_score": 0.1, "minimum_score": 2.3},
                })
                return
            if "outage" in payload.get("question", "").lower():
                self._json(502, {
                    "error": "document answer generation failed",
                    "reason": "upstream_timeout",
                    "error_id": "0123456789abcdef",
                })
                return
            if "where" in payload.get("question", "").lower():
                self._json(200, {
                    "status": "answered",
                    "answer": "Rate is 66.30 [Source 1].",
                    "model": MODEL,
                    "collection": payload.get("collection"),
                    "sources": [{
                        "label": "Source 1", "file": "fees.xlsx", "chunk": 1, "score": 9.1,
                        "location": {"sheet": "Rates", "row_start": 3, "row_end": 6},
                        "flags": ["instruction_like_text"],
                    }],
                    "retrieval": {"matched": True, "citations": {"cited": ["Source 1"], "invalid": []}},
                })
                return
            answer = "Employees have 10 business days [Source 1]."
            if history:
                answer = "Follow-up: weekly fee is daily × 7 = 700 (derived) [Source 1]."
            self._json(200, {
                "status": "answered",
                "answer": answer,
                "model": MODEL,
                "collection": payload.get("collection"),
                "sources": [{"label": "Source 1", "file": "expenses-policy.md", "chunk": 2, "score": 4.2}],
                "retrieval": {"matched": True, "top_score": 4.2, "minimum_score": 2.3},
            })
            return
        self._json(404, {"error": "not found"})


class FakeGateway(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, key: str = KEY) -> None:
        self.key = key
        self.hits: list[dict[str, str]] = []
        self.lock = threading.Lock()
        self.health_code = 200
        self.mode = "ok"
        self.redirect_to = ""
        super().__init__(("127.0.0.1", 0), FakeGatewayHandler)


class RecorderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format_string: str, *args: object) -> None:
        return

    def _hit(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            self.rfile.read(length)
        with self.server.lock:
            self.server.hits.append(self.path)
        body = b'{"error":"proxy received a request"}'
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._hit()

    def do_POST(self) -> None:
        self._hit()


class Recorder(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self) -> None:
        self.hits: list[str] = []
        self.lock = threading.Lock()
        super().__init__(("127.0.0.1", 0), RecorderHandler)


class ConsoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.servers: list[ThreadingHTTPServer] = []

    def tearDown(self) -> None:
        for item in self.servers:
            item.shutdown()
        for item in self.servers:
            item.server_close()

    def start(self, instance: ThreadingHTTPServer) -> ThreadingHTTPServer:
        self.servers.append(instance)
        threading.Thread(target=instance.serve_forever, daemon=True).start()
        return instance

    def web(
        self,
        gateway: FakeGateway | None,
        *,
        api_key: str = KEY,
        api_key_file: str = "",
        model_id: str = MODEL,
        gateway_url: str | None = None,
    ) -> str:
        if gateway is not None:
            self.start(gateway)
            gateway_url = f"http://127.0.0.1:{gateway.server_address[1]}"
        httpd = self.start(server.WebServer(server.Config(
            host="127.0.0.1",
            port=0,
            gateway_url=gateway_url or "http://127.0.0.1:9",
            model_id=model_id,
            api_key=api_key,
            api_key_file=api_key_file,
            upstream_timeout=5,
            health_timeout=1,
        )))
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    def request(self, base: str, method: str, path: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, bytes]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = dict(headers or {})
        if data is not None:
            request_headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(base + path, data=data, headers=request_headers, method=method)
        try:
            with OPENER.open(request, timeout=5) as response:
                return int(response.getcode()), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_config_rejects_public_targets_and_hides_key(self) -> None:
        with self.assertRaises(ValueError):
            server.build_config({"PLATFORM_GATEWAY_URL": "http://example.com:8010", "PLATFORM_API_KEY_FILE": ""})
        with self.assertRaises(ValueError):
            server.build_config({"WEB_HOST": "0.0.0.0", "PLATFORM_API_KEY_FILE": ""})
        with self.assertRaises(ValueError):
            server.build_config({"PLATFORM_GATEWAY_URL": f"http://user:{KEY}@127.0.0.1:8010", "PLATFORM_API_KEY_FILE": ""})
        with self.assertRaises(ValueError):
            server.build_config({"PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010/v1", "PLATFORM_API_KEY_FILE": ""})
        config = server.build_config({"PLATFORM_API_KEY": KEY, "PLATFORM_API_KEY_FILE": "", "PLATFORM_MODEL_ID": MODEL})
        self.assertNotIn(KEY, repr(config))
        self.assertEqual(config.host, "127.0.0.1")

    def test_pages_do_not_contain_the_key_or_gateway_calls(self) -> None:
        base = self.web(FakeGateway())
        status, body = self.request(base, "GET", "/")
        text = body.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertIn("Chat", text)
        self.assertIn("Document Q&amp;A", text)
        self.assertIn("System Status", text)
        self.assertIn(">Agent<", text)
        self.assertIn('id="agent-task"', text)
        self.assertIn("not indexed", text)
        self.assertEqual(
            server.redact_request_log("GET /api/microsoft/callback?code=secret-code&state=abc HTTP/1.1"),
            "GET /api/microsoft/callback [query redacted] HTTP/1.1",
        )
        self.assertIn('id="rag-log"', text)
        self.assertIn('id="rag-clear"', text)
        self.assertIn("Clear conversation", text)
        self.assertNotIn('id="rag-result"', text)
        self.assertNotIn(KEY, text)
        self.assertNotIn("/v1/chat", text)
        status, script = self.request(base, "GET", "/static/app.js")
        script_text = script.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertNotIn(KEY, script_text)
        self.assertNotIn("Authorization", script_text)
        self.assertNotIn("/v1/", script_text)
        self.assertIn("historyPayload", script_text)
        self.assertIn("ragQuestion.value = \"\"", script_text)
        self.assertIn("setRagBusy(false)", script_text)
        self.assertIn("ragTurns", script_text)
        self.assertIn("ragSend.disabled = isBusy", script_text)
        self.assertIn("ragQuestion.disabled = false", script_text)
        self.assertIn("Keep collection, top_k, and uploaded docs", script_text)
        self.assertIn("syncCollectionFields", script_text)
        self.assertIn("removed_from_index", script_text)
        self.assertIn("searchable !== true", script_text)
        self.assertIn('value="my-docs"', text)
        self.assertIn("upload-form", text)
        self.assertIn("document-list", text)
        status, css = self.request(base, "GET", "/static/styles.css")
        self.assertEqual(status, 200)
        self.assertIn("@media (max-width: 800px)", css.decode("utf-8"))
        status, _ = self.request(base, "GET", "/favicon.ico")
        self.assertEqual(status, 204)
        status, _ = self.request(base, "GET", "/static/%2e%2e/server.py")
        self.assertEqual(status, 404)

    def test_status_reports_ready_without_leaking_health_extras(self) -> None:
        gateway = FakeGateway()
        base = self.web(gateway)
        status, body = self.request(base, "GET", "/api/status")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["connection"], "ready")
        self.assertTrue(payload["gateway_reachable"])
        self.assertEqual(payload["health"]["model_count"], 1)
        self.assertNotIn("secret", payload["health"])
        self.assertFalse(payload["runpod_verified"])
        self.assertNotIn(KEY, body.decode("utf-8"))

    def test_status_reports_unreachable_degraded_and_missing_key(self) -> None:
        base = self.web(None, gateway_url="http://127.0.0.1:9")
        payload = json.loads(self.request(base, "GET", "/api/status")[1])
        self.assertEqual(payload["connection"], "unreachable")
        self.assertFalse(payload["runpod_verified"])

        degraded = FakeGateway()
        degraded.health_code = 503
        base = self.web(degraded)
        payload = json.loads(self.request(base, "GET", "/api/status")[1])
        self.assertEqual(payload["connection"], "degraded")
        self.assertEqual(payload["upstream"], "unavailable")

        gateway = FakeGateway()
        base = self.web(gateway, api_key="")
        payload = json.loads(self.request(base, "GET", "/api/status")[1])
        self.assertEqual(payload["connection"], "key_missing")
        status, body = self.request(base, "POST", "/api/chat", {"messages": [{"role": "user", "content": "hello"}]})
        self.assertEqual(status, 503)
        self.assertNotIn(KEY, body.decode("utf-8"))
        self.assertFalse(any(hit["path"] == "/v1/chat/completions" for hit in gateway.hits))

    def test_key_file_is_read_and_missing_file_does_not_fall_back(self) -> None:
        gateway = FakeGateway()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "platform-gateway.key"
            path.write_text(KEY + "\n", encoding="utf-8")
            base = self.web(gateway, api_key="env-key-should-not-be-used-0123456789", api_key_file=str(path))
            status, body = self.request(base, "POST", "/api/chat", {"messages": [{"role": "user", "content": "hello"}]})
        self.assertEqual(status, 200)
        self.assertEqual(gateway.hits[-1]["authorization"], f"Bearer {KEY}")
        self.assertNotIn(KEY, body.decode("utf-8"))

        gateway = FakeGateway()
        base = self.web(gateway, api_key=KEY, api_key_file=str(Path(tempfile.gettempdir()) / "missing-platform-gateway.key"))
        payload = json.loads(self.request(base, "GET", "/api/status")[1])
        self.assertFalse(payload["key_configured"])

    def test_chat_uses_registry_model_id_and_ignores_client_credentials(self) -> None:
        gateway = FakeGateway()
        base = self.web(gateway, model_id="qwen3.5-27b")
        status, body = self.request(
            base,
            "POST",
            "/api/chat",
            {
                "model": "qwen3.5-27b",
                "messages": [{"role": "user", "content": "Reply with exactly: gateway works"}],
            },
            headers={"Authorization": "Bearer client-supplied-token"},
        )
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["choices"][0]["message"]["content"], "gateway works")
        forwarded = json.loads(gateway.hits[-1]["body"])
        self.assertEqual(forwarded["model"], "qwen3.5-27b")
        self.assertEqual(gateway.hits[-1]["authorization"], f"Bearer {KEY}")
        self.assertNotIn(KEY, body.decode("utf-8"))

        # Filesystem-like overrides from the browser are rejected.
        status, body = self.request(
            base,
            "POST",
            "/api/chat",
            {
                "model": "/workspace/secret-path",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("registry id", body.decode("utf-8").casefold())

        stdout = sys.stdout
        captured: list[str] = []

        class Capture:
            def write(self, text: str) -> int:
                captured.append(text)
                return len(text)

            def flush(self) -> None:
                return

        sys.stdout = Capture()
        try:
            self.request(base, "POST", "/api/chat", {"messages": [{"role": "user", "content": "hello again"}]})
        finally:
            sys.stdout = stdout
        self.assertNotIn(KEY, "".join(captured))

    def test_platform_models_proxy_requires_key(self) -> None:
        gateway = FakeGateway()
        base = self.web(gateway)
        status, body = self.request(base, "GET", "/api/platform/models")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        ids = {item["id"] for item in payload["models"]}
        self.assertIn("qwen3.5-27b", ids)
        self.assertIn("gemma-4-31b-it", ids)
        self.assertNotIn("/workspace", body.decode("utf-8"))
        self.assertEqual(gateway.hits[-1]["authorization"], f"Bearer {KEY}")

    def test_chat_validation_and_missing_model(self) -> None:
        gateway = FakeGateway()
        base = self.web(gateway)
        status, _ = self.request(base, "POST", "/api/chat", {"messages": []})
        self.assertEqual(status, 400)
        status, _ = self.request(base, "POST", "/api/chat", {"messages": [{"role": "assistant", "content": "hi"}]})
        self.assertEqual(status, 400)

        gateway = FakeGateway()
        base = self.web(gateway, model_id="")
        status, body = self.request(base, "POST", "/api/chat", {"messages": [{"role": "user", "content": "hello"}]})
        self.assertEqual(status, 503)
        self.assertIn("PLATFORM_MODEL_ID", body.decode("utf-8"))
        self.assertFalse(any(hit["path"] == "/v1/chat/completions" for hit in gateway.hits))

    def test_console_does_not_auto_select_a_non_default_model(self) -> None:
        script = (Path(__file__).resolve().parent / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("item.is_active_default && modelUsable(item)", script)
        self.assertNotIn("return modelUsable(item); })[0]", script)
        self.assertIn("Another model is not selected automatically.", script)

    def test_rag_returns_sources_and_abstention(self) -> None:
        gateway = FakeGateway()
        base = self.web(gateway)
        status, body = self.request(base, "POST", "/api/rag", {
            "question": "How many business days do employees have to submit expense receipts?",
            "collection": "finance",
            "top_k": 4,
            "ignore": "do not forward",
        })
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "answered")
        self.assertEqual(payload["sources"][0]["file"], "expenses-policy.md")
        self.assertEqual(payload["sources"][0]["chunk"], 2)
        forwarded = json.loads(gateway.hits[-1]["body"])
        self.assertEqual(forwarded["collection"], "finance")
        self.assertNotIn("ignore", forwarded)
        self.assertNotIn("history", forwarded)

        status, body = self.request(base, "POST", "/api/rag", {"question": "What colour is the CEO private yacht?"})
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "abstained")
        self.assertEqual(payload["sources"], [])

        before = len(gateway.hits)
        status, _ = self.request(base, "POST", "/api/rag", {"question": "hello", "collection": "../secrets"})
        self.assertEqual(status, 400)
        self.assertEqual(len(gateway.hits), before)

    def test_rag_source_locations_and_gateway_error_ids_pass_through(self) -> None:
        gateway = FakeGateway()
        base = self.web(gateway)
        status, body = self.request(base, "POST", "/api/rag", {"question": "Where is the standard rate?"})
        self.assertEqual(status, 200)
        source = json.loads(body)["sources"][0]
        self.assertEqual(source["location"], {"sheet": "Rates", "row_start": 3, "row_end": 6})
        self.assertEqual(source["flags"], ["instruction_like_text"])
        status, body = self.request(base, "POST", "/api/rag", {"question": "Simulate an outage"})
        self.assertEqual(status, 502)
        payload = json.loads(body)
        self.assertEqual(payload["error_id"], "0123456789abcdef")
        self.assertEqual(payload["error"], "document answer generation failed")

    def test_managed_document_list_upload_and_delete_proxy(self) -> None:
        gateway = FakeGateway()
        base = self.web(gateway)
        status, body = self.request(base, "GET", "/api/documents?collection=my-docs")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["documents"][0]["filename"], "policy.md")
        self.assertEqual(gateway.hits[-1]["authorization"], f"Bearer {KEY}")
        self.assertEqual(gateway.hits[-1]["path"], "/v1/rag/documents")

        status, body = self.request(base, "POST", "/api/documents", {
            "collection": "my-docs", "filename": "policy.md", "content_base64": "UG9saWN5IHRleHQ=",
            "overwrite": False,
        })
        self.assertEqual(status, 201)
        uploaded = json.loads(body)["document"]
        self.assertEqual(uploaded["filename"], "policy.md")
        self.assertTrue(uploaded["searchable"])
        self.assertEqual(uploaded["chunk_count"], 1)
        forwarded = json.loads(gateway.hits[-1]["body"])
        self.assertEqual(forwarded["content_base64"], "UG9saWN5IHRleHQ=")
        self.assertEqual(gateway.hits[-1]["authorization"], f"Bearer {KEY}")

        status, body = self.request(base, "DELETE", "/api/documents?collection=my-docs&filename=policy.md")
        self.assertEqual(status, 200)
        deleted = json.loads(body)
        self.assertTrue(deleted["deleted"])
        self.assertTrue(deleted["removed_from_index"])
        self.assertEqual(gateway.hits[-1]["method"], "DELETE")

    def test_managed_document_upload_rejects_invalid_collection(self) -> None:
        gateway = FakeGateway()
        base = self.web(gateway)
        before = len(gateway.hits)
        status, _ = self.request(base, "POST", "/api/documents", {
            "collection": "../private", "filename": "policy.md", "content_base64": "UG9saWN5IHRleHQ=",
        })
        self.assertEqual(status, 400)
        self.assertEqual(len(gateway.hits), before)

    def test_rag_history_is_validated_and_forwarded(self) -> None:
        gateway = FakeGateway()
        base = self.web(gateway)
        history = [
            {"role": "user", "content": "What is the daily fee?"},
            {"role": "assistant", "content": "The daily fee is 100 [Source 1]."},
        ]
        status, body = self.request(base, "POST", "/api/rag", {
            "question": "What is the weekly fee?",
            "collection": "finance",
            "top_k": 3,
            "history": history,
            "extra": "drop-me",
        })
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIn("weekly fee is daily × 7", payload["answer"])
        self.assertEqual(payload["sources"][0]["file"], "expenses-policy.md")
        forwarded = json.loads(gateway.hits[-1]["body"])
        self.assertEqual(forwarded["question"], "What is the weekly fee?")
        self.assertEqual(forwarded["collection"], "finance")
        self.assertEqual(forwarded["history"], history)
        self.assertNotIn("extra", forwarded)

        before = len(gateway.hits)
        bad_cases = [
            {"question": "follow up", "history": "nope"},
            {"question": "follow up", "history": [{"role": "assistant", "content": "alone"}]},
            {"question": "follow up", "history": [{"role": "user", "content": "only"}]},
            {"question": "follow up", "history": [{"role": "user", "content": "q"}, {"role": "user", "content": "q2"}]},
        ]
        for case in bad_cases:
            status, err = self.request(base, "POST", "/api/rag", case)
            self.assertEqual(status, 400, case)
            self.assertIn("history", json.loads(err)["error"])
        self.assertEqual(len(gateway.hits), before)

    def test_validate_rag_history_helper(self) -> None:
        self.assertEqual(server.validate_rag_history(None), [])
        with self.assertRaises(ValueError):
            server.validate_rag_history([{"role": "user", "content": "q"}])
        with self.assertRaises(ValueError):
            server.validate_rag_history([
                {"role": "user", "content": "u" * 2000},
                {"role": "assistant", "content": "a" * 2000},
            ] * 4)

    def test_rag_without_history_still_works(self) -> None:
        gateway = FakeGateway()
        base = self.web(gateway)
        status, body = self.request(base, "POST", "/api/rag", {
            "question": "How many business days?",
            "top_k": 2,
        })
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "answered")
        forwarded = json.loads(gateway.hits[-1]["body"])
        self.assertNotIn("history", forwarded)
    def test_gateway_errors_do_not_reflect_the_key_or_follow_redirects(self) -> None:
        gateway = FakeGateway()
        gateway.mode = "reflect-key"
        base = self.web(gateway)
        status, body = self.request(base, "POST", "/api/chat", {"messages": [{"role": "user", "content": "hello"}]})
        text = body.decode("utf-8")
        self.assertEqual(status, 500)
        self.assertNotIn(KEY, text)

        target = self.start(Recorder())
        gateway = FakeGateway()
        gateway.mode = "redirect"
        gateway.redirect_to = f"http://127.0.0.1:{target.server_address[1]}/stolen"
        base = self.web(gateway)
        status, body = self.request(base, "POST", "/api/chat", {"messages": [{"role": "user", "content": "hello"}]})
        self.assertGreaterEqual(status, 300)
        self.assertEqual(target.hits, [])
        self.assertNotIn(KEY, body.decode("utf-8"))

    def test_requests_do_not_honor_http_proxy(self) -> None:
        proxy = self.start(Recorder())
        gateway = FakeGateway()
        base = self.web(gateway)
        previous = {name: os.environ.get(name) for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")}
        os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{proxy.server_address[1]}"
        os.environ["http_proxy"] = os.environ["HTTP_PROXY"]
        try:
            status, _ = self.request(base, "POST", "/api/chat", {"messages": [{"role": "user", "content": "hello"}]})
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.assertEqual(status, 200)
        self.assertEqual(proxy.hits, [])
        self.assertTrue(any(hit["path"] == "/v1/chat/completions" for hit in gateway.hits))

    def test_agent_page_lists_microsoft_as_disconnected_and_does_not_leak_the_key(self) -> None:
        previous = os.environ.pop("MICROSOFT_CLIENT_ID", None)
        gateway = FakeGateway()
        try:
            base = self.web(gateway)
        finally:
            if previous is not None:
                os.environ["MICROSOFT_CLIENT_ID"] = previous
        status, body = self.request(base, "GET", "/api/connectors")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["connectors"][0]["connector_id"], "microsoft365")
        self.assertFalse(payload["connectors"][0]["connected"])
        self.assertFalse(payload["connectors"][0]["sign_in"]["configured"])
        self.assertNotIn("access_token", body.decode("utf-8"))
        page_status, page = self.request(base, "GET", "/")
        self.assertEqual(page_status, 200)
        self.assertIn(b"Sign in with a work or school account", page)
        self.assertIn(b"Sign in with a personal Microsoft account", page)
        self.assertNotIn(b"Mail.Send", page)
        start_status, start_body = self.request(base, "GET", "/api/microsoft/start")
        self.assertEqual(start_status, 409)
        self.assertIn(b"MICROSOFT_CLIENT_ID", start_body)
        status, body = self.request(base, "POST", "/api/agent", {"task": "What is 2 + 2?"})
        text = body.decode("utf-8")
        self.assertEqual(status, 200)
        view = json.loads(text)
        self.assertEqual(view["state"], "failed")
        self.assertNotIn(KEY, text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("messages", view)

    def test_configured_sign_in_redirects_to_microsoft_without_a_secret(self) -> None:
        previous = os.environ.get("MICROSOFT_CLIENT_ID")
        os.environ["MICROSOFT_CLIENT_ID"] = "11111111-2222-3333-4444-555555555555"
        try:
            base = self.web(None)
            class RefuseRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, request, fp, code, msg, headers, newurl):
                    raise urllib.error.HTTPError(newurl, code, msg, headers, fp)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RefuseRedirect)
            try:
                opener.open(base + "/api/microsoft/start", timeout=5)
                location = ""
                status = 200
            except urllib.error.HTTPError as exc:
                status = exc.code
                location = exc.headers.get("Location") or exc.url
        finally:
            if previous is None:
                os.environ.pop("MICROSOFT_CLIENT_ID", None)
            else:
                os.environ["MICROSOFT_CLIENT_ID"] = previous
        self.assertEqual(status, 302)
        self.assertTrue(location.startswith("https://login.microsoftonline.com/common/"))
        self.assertIn("code_challenge_method=S256", location)
        self.assertNotIn("client_secret", location)
        self.assertNotIn("Mail.Send", location)

    def test_sign_in_account_choice_is_limited_to_microsoft_directories(self) -> None:
        previous = os.environ.get("MICROSOFT_CLIENT_ID")
        os.environ["MICROSOFT_CLIENT_ID"] = "11111111-2222-3333-4444-555555555555"
        try:
            base = self.web(None)

            def location_for(path: str) -> tuple[int, str]:
                class RefuseRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, request, fp, code, msg, headers, newurl):
                        raise urllib.error.HTTPError(newurl, code, msg, headers, fp)
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RefuseRedirect)
                try:
                    opener.open(base + path, timeout=5)
                except urllib.error.HTTPError as exc:
                    return exc.code, exc.headers.get("Location") or ""
                return 200, ""

            work_status, work_location = location_for("/api/microsoft/start?account=work")
            bad_status, bad_body = self.request(base, "GET", "/api/microsoft/start?account=evil.example")
        finally:
            if previous is None:
                os.environ.pop("MICROSOFT_CLIENT_ID", None)
            else:
                os.environ["MICROSOFT_CLIENT_ID"] = previous
        self.assertEqual(work_status, 302)
        self.assertIn("/organizations/", work_location)
        self.assertNotIn("client_secret", work_location)
        self.assertEqual(bad_status, 400)
        self.assertNotIn(b"11111111", bad_body)


if __name__ == "__main__":
    unittest.main()
