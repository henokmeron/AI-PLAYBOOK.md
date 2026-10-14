"""Built-in tool tests: calculator, authorised-root files, tables, search, schema, redaction."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from agents.adapters.rag_library import GatewayDocumentQABackend, RagLibrarySearchBackend
from agents.builtin import default_registry
from agents.builtin.calculator import evaluate
from agents.builtin.files import AuthorisedRoot, read_text
from agents.builtin.structured import structured_output_tool
from agents.builtin.tables import analyse
from agents.model import ScriptedModel, OpenAICompatibleClient, parse_chat_completion, strip_reasoning, validate_endpoint
from agents.redaction import redact, redact_text
from agents.runtime import AgentRunner
from agents.schema import SchemaError, ValidationError, check_schema, validate
from agents.state import TaskState
from agents.tools import ToolInputError, ToolPermissionError, ToolTransientError

REPO = Path(__file__).resolve().parents[2]


class CalculatorTests(unittest.TestCase):
    def test_exact_decimal(self) -> None:
        self.assertEqual(str(evaluate("99.498 * 7")), "696.486")
        self.assertEqual(str(evaluate("0.1 + 0.2")), "0.3")
        self.assertEqual(str(evaluate("round(696.486, 2)")), "696.49")
        self.assertEqual(str(evaluate("max(1, 2, 3) + abs(-2) - sqrt(16)")), "1")

    def test_rejects_non_arithmetic(self) -> None:
        for expression in [
            "__import__('os')", "a + 1", "(1).real", "[1, 2]", "'a' * 3", "lambda: 1",
            "1 if 1 else 2", "open('x')", "True + 1", "1j * 2", "round(1.5, ndigits=1)",
        ]:
            with self.subTest(expression=expression), self.assertRaises(ToolInputError):
                evaluate(expression)

    def test_resource_limits(self) -> None:
        for expression in ["9 ** 9 ** 9", "10 ** 65", "2 ** 0.5", "1/0", "sqrt(-1)", "1+" * 200 + "1"]:
            with self.subTest(expression=expression[:20]), self.assertRaises(ToolInputError):
                evaluate(expression)


class AuthorisedRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root_dir = base / "docs"
        (self.root_dir / "sub").mkdir(parents=True)
        (self.root_dir / "a.txt").write_text("alpha " * 10, encoding="utf-8")
        (self.root_dir / "sub" / "b.md").write_text("# beta", encoding="utf-8")
        (self.root_dir / ".env").write_text("SECRET=1", encoding="utf-8")
        (self.root_dir / "run.sh").write_text("echo", encoding="utf-8")
        (base / "outside.txt").write_text("outside", encoding="utf-8")
        self.root = AuthorisedRoot(self.root_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_reads_inside_root(self) -> None:
        self.assertTrue(read_text(self.root, "a.txt", None).startswith("alpha"))
        self.assertEqual(read_text(self.root, "sub/b.md", None), "# beta")
        self.assertEqual(read_text(self.root, "sub\\b.md", None), "# beta")

    def test_traversal_and_absolute_paths_rejected(self) -> None:
        outside = str(Path(self.tmp.name) / "outside.txt")
        for path in ["../outside.txt", "sub/../../outside.txt", outside, "/etc/passwd",
                     "C:\\Windows\\win.ini", "C:outside.txt", "\\\\server\\share\\x.txt",
                     "~/x.txt", ".env", "sub/.hidden", "a.txt:stream", "a.txt\x00.md"]:
            with self.subTest(path=path), self.assertRaises((ToolPermissionError, ToolInputError)):
                read_text(self.root, path, None)

    def test_disallowed_extension(self) -> None:
        with self.assertRaises(ToolPermissionError):
            read_text(self.root, "run.sh", None)

    def test_symlink_not_followed(self) -> None:
        link = self.root_dir / "link.txt"
        try:
            os.symlink(Path(self.tmp.name) / "outside.txt", link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable (Windows without developer mode)")
        with self.assertRaises(ToolPermissionError):
            read_text(self.root, "link.txt", None)

    def test_listing_hides_dotfiles_and_is_relative(self) -> None:
        files, truncated = self.root.list_files()
        paths = [f["path"] for f in files]
        self.assertEqual(paths, ["a.txt", "run.sh", "sub/b.md"])
        self.assertFalse(truncated)

    def test_read_tool_pages_and_marks_untrusted(self) -> None:
        registry = default_registry(document_root=self.root_dir, use_rag_extractor=False)
        tool = registry.get("read_document")
        result = tool.handler({"path": "a.txt", "offset": 6, "max_chars": 5})
        tool.validate_output(result)
        self.assertEqual(result["text"], "alpha")
        self.assertTrue(result["has_more"])
        self.assertTrue(result["untrusted"])
        self.assertNotIn("write", " ".join(registry.names()))


class TableAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.tmp.name)
        (self.root_dir / "fees.csv").write_text(
            "Council,Age band,Daily rate\n"
            "Surrey,0-4,£99.498\nSurrey,5-10,\"£1,105.50\"\nKent,0-4,88\nKent,5-10,N/A\n",
            encoding="utf-8",
        )
        self.root = AuthorisedRoot(self.root_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_describe(self) -> None:
        out = analyse(self.root, {"path": "fees.csv", "operation": "describe"})
        self.assertEqual(out["columns"], ["Council", "Age band", "Daily rate"])
        self.assertEqual(out["matched_rows"], 4)
        self.assertIn("Daily rate", out["numeric_columns"])

    def test_aggregate_grouped_skips_non_numeric(self) -> None:
        out = analyse(self.root, {"path": "fees.csv", "operation": "aggregate", "column": "Daily rate",
                                  "aggregate": "sum", "group_by": "Council"})
        groups = {g["key"]: g for g in out["groups"]}
        self.assertEqual(groups["Surrey"]["value"], "1204.998")
        self.assertEqual(groups["Kent"]["value"], "88")
        self.assertEqual(groups["Kent"]["skipped_non_numeric"], 1)

    def test_select_with_filters(self) -> None:
        out = analyse(self.root, {"path": "fees.csv", "operation": "select", "columns": ["Age band", "Daily rate"],
                                  "filters": [{"column": "Council", "op": "eq", "value": "surrey"},
                                              {"column": "Daily rate", "op": "gt", "value": 100}]})
        self.assertEqual(out["rows"], [["5-10", "£1,105.50"]])

    def test_unknown_column_and_bad_type(self) -> None:
        with self.assertRaises(ToolInputError):
            analyse(self.root, {"path": "fees.csv", "operation": "aggregate", "column": "Nope", "aggregate": "sum"})
        (self.root_dir / "notes.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(ToolInputError):
            analyse(self.root, {"path": "notes.txt", "operation": "describe"})

    def test_row_limit(self) -> None:
        (self.root_dir / "big.csv").write_text("a\n" + "1\n" * 20_002, encoding="utf-8")
        with self.assertRaises(ToolInputError):
            analyse(self.root, {"path": "big.csv", "operation": "describe"})

    def test_xlsx_if_openpyxl_available(self) -> None:
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl not installed")
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Rates"
        sheet.append(["Band", "Rate"])
        sheet.append(["0-4", 99.498])
        sheet.append(["5-10", 120.0])
        workbook.save(self.root_dir / "rates.xlsx")
        out = analyse(self.root, {"path": "rates.xlsx", "sheet": "Rates", "operation": "aggregate",
                                  "column": "Rate", "aggregate": "sum"})
        self.assertEqual(out["result"]["value"], "219.498")
        with self.assertRaises(ToolInputError):
            analyse(self.root, {"path": "rates.xlsx", "sheet": "Missing", "operation": "describe"})

    def test_xlsx_zip_bomb_guard(self) -> None:
        import zipfile
        bomb = self.root_dir / "bomb.xlsx"
        with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("xl/worksheets/sheet1.xml", b"0" * (31 * 1024 * 1024))
        with self.assertRaises(ToolInputError):
            analyse(self.root, {"path": "bomb.xlsx", "operation": "describe"})


class RagAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.managed = Path(self.tmp.name)
        for collection, text in [("tenant-a", "Annual leave is 25 days for employees."),
                                 ("tenant-b", "Tenant B secret pricing: 999 per unit.")]:
            (self.managed / collection).mkdir()
            (self.managed / collection / "policy.md").write_text(text, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_search_uses_rag_library_and_respects_grant(self) -> None:
        backend = RagLibrarySearchBackend(self.managed, ["tenant-a"], rag_dir=REPO / "rag")
        hits = backend.search("annual leave days", "tenant-a", 3)
        self.assertEqual(hits[0]["file"], "policy.md")
        self.assertIn("25 days", hits[0]["text"])
        with self.assertRaises(ToolPermissionError):
            backend.search("pricing", "tenant-b", 3)

    def test_agent_search_then_answer(self) -> None:
        backend = RagLibrarySearchBackend(self.managed, ["tenant-a"], rag_dir=REPO / "rag")
        registry = default_registry(search_backend=backend)
        model = ScriptedModel([
            json.dumps({"action": "tool", "tool": "document_search",
                        "arguments": {"query": "annual leave", "collection": "tenant-a"}}),
            json.dumps({"action": "tool", "tool": "document_search",
                        "arguments": {"query": "pricing", "collection": "tenant-b"}}),
            json.dumps({"action": "final", "answer": "25 days [policy.md]"}),
        ])
        runner = AgentRunner(model, registry)
        task = runner.run(runner.new_task("How much annual leave?"))
        self.assertEqual(task.state, TaskState.FINAL)
        self.assertIn("25 days", model.calls[1][-1]["content"])
        self.assertIn("permission_denied", model.calls[2][-1]["content"])
        blob = json.dumps(task.messages)
        self.assertNotIn("secret pricing", blob)
        self.assertNotIn("999 per unit", blob)

    def test_gateway_backend_requires_loopback_and_grant(self) -> None:
        with self.assertRaises(ValueError):
            GatewayDocumentQABackend("http://example.com:8010", lambda: "k" * 40, ["a"])
        backend = GatewayDocumentQABackend("http://127.0.0.1:1", lambda: "k" * 40, ["a"], timeout=0.5)
        with self.assertRaises(ToolPermissionError):
            backend.ask("q?", "b", 4)
        with self.assertRaises(ToolTransientError):
            backend.ask("q?", "a", 4)


class ModelClientTests(unittest.TestCase):
    def test_endpoint_validation(self) -> None:
        self.assertEqual(validate_endpoint("http://127.0.0.1:8010/v1/"), "http://127.0.0.1:8010/v1")
        for bad in ["http://10.0.0.5:8010/v1", "http://127.0.0.1/v1", "https://x.example/v1",
                    "http://user:pw@127.0.0.1:8010/v1", "file:///etc/passwd", "http://127.0.0.1:8010@evil.com/v1"]:
            with self.subTest(url=bad), self.assertRaises(ValueError):
                validate_endpoint(bad)
        self.assertEqual(validate_endpoint("https://x.example/v1", allow_remote_https=True), "https://x.example/v1")

    def test_parse_completion_and_strip_think(self) -> None:
        raw = json.dumps({"choices": [{"message": {"content": "<think>secret plan</think>\n{\"a\":1}"},
                                       "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
        reply = parse_chat_completion(raw)
        self.assertEqual(reply.content, '{"a":1}')
        self.assertEqual(reply.total_tokens, 15)
        self.assertEqual(strip_reasoning("partial</think> ok"), "ok")

    def test_repr_hides_key(self) -> None:
        client = OpenAICompatibleClient("http://127.0.0.1:8010/v1", lambda: "secret-key-value-123456")
        self.assertNotIn("secret", repr(client))

    def test_client_sends_bearer_without_proxy(self) -> None:
        captured = {}

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode()

        class FakeOpener:
            def open(self, request, timeout):
                captured["auth"] = request.get_header("Authorization")
                captured["body"] = json.loads(request.data)
                return FakeResponse()

        client = OpenAICompatibleClient("http://127.0.0.1:8010/v1", lambda: "k" * 40, model="qwen3.5-27b",
                                        opener=FakeOpener())
        reply = client.complete([{"role": "user", "content": "x"}], max_tokens=10, timeout=1)
        self.assertEqual(reply.content, "hi")
        self.assertEqual(captured["auth"], "Bearer " + "k" * 40)
        self.assertEqual(captured["body"]["model"], "qwen3.5-27b")
        self.assertFalse(captured["body"]["stream"])


class SchemaTests(unittest.TestCase):
    def test_unknown_keyword_rejected(self) -> None:
        with self.assertRaises(SchemaError):
            check_schema({"type": "object", "propertes": {}})

    def test_core_keywords(self) -> None:
        schema = {"type": "object", "properties": {"n": {"type": "integer", "minimum": 1},
                                                  "tags": {"type": "array", "items": {"enum": ["a", "b"]}}},
                  "required": ["n"], "additionalProperties": False}
        validate({"n": 2, "tags": ["a"]}, schema)
        for bad in [{"n": 0}, {"n": True}, {"tags": []}, {"n": 1, "x": 1}, {"n": 1, "tags": ["c"]}]:
            with self.subTest(value=bad), self.assertRaises(ValidationError):
                validate(bad, schema)

    def test_structured_output_tool(self) -> None:
        tool = structured_output_tool({"invoice": {"type": "object", "required": ["total"]}})
        self.assertTrue(tool.handler({"schema": "invoice", "value": {"total": 1}})["valid"])
        self.assertFalse(tool.handler({"schema": "invoice", "value": {}})["valid"])


class RedactionTests(unittest.TestCase):
    def test_patterns_and_keys(self) -> None:
        text = redact_text("Authorization: Bearer abcdefghijklmnop and token=hunter2hunter2 rpa_" + "X" * 24)
        self.assertNotIn("abcdefghijklmnop", text)
        self.assertNotIn("hunter2hunter2", text)
        self.assertNotIn("X" * 24, text)
        data = redact({"api_key": "v", "max_tokens": 5, "nested": [{"password": "p"}],
                       "access_token": "t", "note": '{"client_secret": "zzz"}'})
        self.assertEqual(data["api_key"], "[REDACTED]")
        self.assertEqual(data["max_tokens"], 5)
        self.assertEqual(data["nested"][0]["password"], "[REDACTED]")
        self.assertEqual(data["access_token"], "[REDACTED]")
        self.assertNotIn("zzz", data["note"])

    def test_known_secret_values(self) -> None:
        self.assertEqual(redact_text("key is abc123456789", {"abc123456789"}), "key is [REDACTED]")


if __name__ == "__main__":
    unittest.main()
