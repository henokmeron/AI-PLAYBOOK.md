#!/usr/bin/env python3
"""Focused tests for supported business document loaders; no GPU or model calls."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from document_loaders import DocumentLoadError, read_document
from rag_engine import load_chunks, retrieve


class DocumentLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="rag-document-loader-test-")
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_docx(self, path: Path, paragraph_text: list[str]) -> None:
        paragraphs = "".join(
            "<w:p><w:r><w:t>" + text + "</w:t></w:r></w:p>"
            for text in paragraph_text
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>" + paragraphs + "</w:body></w:document>"
        )
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", xml)

    def test_plain_text_is_read(self) -> None:
        path = self.root / "policy.txt"
        path.write_text("Expense receipts are due in 10 business days.", encoding="utf-8")
        self.assertIn("10 business days", read_document(path))

    def test_csv_becomes_searchable_rows(self) -> None:
        path = self.root / "expenses.csv"
        path.write_text("type,rule\nrail,manager approval above 100 pounds\n", encoding="utf-8")
        text = read_document(path)
        self.assertIn("Row 2", text)
        self.assertIn("manager approval above 100 pounds", text)

    def test_html_excludes_script_and_style_text(self) -> None:
        path = self.root / "policy.html"
        path.write_text(
            "<html><head><style>style_secret</style><script>script_secret</script></head>"
            "<body><h1>Travel policy</h1><p>Book standard class rail.</p></body></html>",
            encoding="utf-8",
        )
        text = read_document(path)
        self.assertIn("Travel policy", text)
        self.assertIn("standard class rail", text)
        self.assertNotIn("style_secret", text)
        self.assertNotIn("script_secret", text)

    def test_docx_paragraphs_are_extracted(self) -> None:
        path = self.root / "policy.docx"
        self.make_docx(path, ["Expense deadline is 10 business days.", "Manager approval is required above 100 pounds."])
        text = read_document(path)
        self.assertIn("10 business days", text)
        self.assertIn("Manager approval", text)

    def test_unknown_extension_is_rejected(self) -> None:
        path = self.root / "policy.pdf"
        path.write_bytes(b"not a PDF")
        with self.assertRaises(DocumentLoadError):
            read_document(path)

    def test_invalid_docx_is_rejected(self) -> None:
        path = self.root / "invalid.docx"
        path.write_bytes(b"not a ZIP-based Word document")
        with self.assertRaises(DocumentLoadError):
            read_document(path)

    def test_input_size_limit_is_applied(self) -> None:
        path = self.root / "too-large.txt"
        path.write_bytes(b"x" * (10 * 1024 * 1024 + 1))
        with self.assertRaises(DocumentLoadError):
            read_document(path)

    def test_rag_index_preserves_docx_and_csv_source_names(self) -> None:
        csv_path = self.root / "approval.csv"
        csv_path.write_text("type,rule\nexpense,manager approval above 100 pounds\n", encoding="utf-8")
        docx_path = self.root / "deadline.docx"
        self.make_docx(docx_path, ["Receipts must be submitted within 10 business days."])
        chunks = load_chunks(self.root)
        self.assertEqual({chunk.source for chunk in chunks}, {"approval.csv", "deadline.docx"})
        ranked = retrieve("When must receipts be submitted in business days?", chunks, top_k=2)
        self.assertTrue(ranked)
        self.assertEqual(ranked[0][1].source, "deadline.docx")


if __name__ == "__main__":
    unittest.main(verbosity=2)
