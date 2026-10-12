#!/usr/bin/env python3
"""Unit tests for the pure-Python RAG retrieval engine; no model/API is needed."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# When this file is run from /tmp alongside rag_engine.py, that directory is
# already on sys.path. Also allow callers to point at a checkout's rag folder.
HERE = Path(__file__).resolve().parent
if (HERE / "rag_engine.py").is_file():
    sys.path.insert(0, str(HERE))
else:
    sys.path.insert(0, str(HERE.parent))

from rag_engine import (  # noqa: E402
    Chunk,
    dedupe_ranked_chunks,
    load_chunks,
    retrieve,
    split_chunks,
    tokenize,
)
from collections import Counter  # noqa: E402


class TokenizerTests(unittest.TestCase):
    def test_tokenization_is_case_insensitive(self) -> None:
        self.assertEqual(tokenize("BUSINESS days, Receipts!"), ["business", "days", "receipts"])

    def test_empty_text_has_no_tokens(self) -> None:
        self.assertEqual(tokenize("   \n "), [])


class ChunkingTests(unittest.TestCase):
    def test_short_text_remains_single_chunk(self) -> None:
        self.assertEqual(split_chunks("A short policy."), ["A short policy."])

    def test_long_text_is_split_with_overlap(self) -> None:
        text = ("Line of policy text.\n" * 100)
        chunks = split_chunks(text, max_chars=300, overlap=50)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.strip() for chunk in chunks))
        self.assertTrue(all(len(chunk) <= 300 for chunk in chunks))

    def test_empty_text_has_no_chunks(self) -> None:
        self.assertEqual(split_chunks(" "), [])

    def test_spreadsheet_rows_are_not_split_mid_line(self) -> None:
        rows = [
            "Sheet: Rates (state: visible)",
            "Sheet: Rates | Row 1: A1=Age band | B1=Daily rate",
        ]
        for index in range(2, 40):
            rows.append(
                f"Sheet: Rates | Row {index}: A{index}=band-{index} | B{index}/Daily rate={index}.5"
            )
        text = "\n".join(rows)
        chunks = split_chunks(text, max_chars=220, overlap=40)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            for line in chunk.splitlines():
                if "| Row " in line:
                    self.assertTrue(line.startswith("Sheet:"))
                    self.assertIn("=", line)


class DuplicateEvidenceTests(unittest.TestCase):
    def test_dedupe_keeps_both_filenames_for_identical_rows(self) -> None:
        text = (
            "Sheet: Sheet1 | Row 4: A4=Standard Placements | B4/Aged 0-4 Years=66.3\n"
            "Sheet: Sheet1 | Row 5: A5=Complex Placements | B5/Aged 0-4 Years=99.498"
        )
        left = Chunk("Banya fees.xlsx", 1, text, tokenize(text), Counter(tokenize(text)))
        right = Chunk("Fee to carers.xlsx", 1, text, tokenize(text), Counter(tokenize(text)))
        groups = dedupe_ranked_chunks([(1.2, left), (1.1, right)])
        self.assertEqual(len(groups), 1)
        score, chunk, files = groups[0]
        self.assertEqual(score, 1.2)
        self.assertEqual(chunk.source, "Banya fees.xlsx")
        self.assertEqual(files, ["Banya fees.xlsx", "Fee to carers.xlsx"])

    def test_dedupe_keeps_conflicting_workbook_chunks_separate(self) -> None:
        left_text = "Sheet: Sheet1 | Row 4: A4=Standard | B4=66.3"
        right_text = "Sheet: Sheet1 | Row 4: A4=Standard | B4=70.0"
        left = Chunk("a.xlsx", 1, left_text, tokenize(left_text), Counter(tokenize(left_text)))
        right = Chunk("b.xlsx", 1, right_text, tokenize(right_text), Counter(tokenize(right_text)))
        groups = dedupe_ranked_chunks([(1.0, left), (0.9, right)])
        self.assertEqual(len(groups), 2)
        self.assertEqual({files[0] for _, _, files in groups}, {"a.xlsx", "b.xlsx"})


class RetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="rag-engine-test-")
        self.folder = Path(self.temp_dir.name)
        (self.folder / "expenses-policy.md").write_text(
            "# Expense Policy\n\n"
            "Employees must submit expense claims with receipts within 10 business days.\n"
            "Expenses above 100 pounds require manager approval.\n",
            encoding="utf-8",
        )
        (self.folder / "employee-handbook.md").write_text(
            "# Employee Handbook\n\n"
            "The office is staffed from 09:00 to 17:30 Monday to Friday.\n"
            "Store company documents in approved company systems.\n",
            encoding="utf-8",
        )
        self.chunks = load_chunks(self.folder)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_relevant_expense_policy_is_ranked_first(self) -> None:
        ranked = retrieve("How many business days to submit expense receipts?", self.chunks, top_k=2)
        self.assertTrue(ranked)
        self.assertEqual(ranked[0][1].source, "expenses-policy.md")
        if len(ranked) > 1:
            self.assertGreater(ranked[0][0], ranked[1][0])

    def test_office_hours_ranks_handbook_first(self) -> None:
        ranked = retrieve("What hours is the office staffed Monday to Friday?", self.chunks, top_k=2)
        self.assertTrue(ranked)
        self.assertEqual(ranked[0][1].source, "employee-handbook.md")

    def test_no_overlapping_terms_returns_no_results(self) -> None:
        self.assertEqual(retrieve("zyxwvut quantum payroll quasar", self.chunks, top_k=4), [])

    def test_top_k_limits_result_count(self) -> None:
        self.assertEqual(len(retrieve("expense company policy", self.chunks, top_k=1)), 1)

    def test_empty_or_punctuation_only_question_returns_no_results(self) -> None:
        self.assertEqual(retrieve("!? -- ...", self.chunks, top_k=4), [])


class DocumentLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="rag-loader-test-")
        self.folder = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_csv_is_read_as_searchable_rows(self) -> None:
        from document_loaders import read_document
        path = self.folder / "expenses.csv"
        path.write_text("category,limit\nrail,100 pounds\n", encoding="utf-8")
        text = read_document(path)
        self.assertIn("rail", text)
        self.assertIn("100 pounds", text)
        self.assertIn("Row 2", text)

    def test_html_ignores_script_and_style_content(self) -> None:
        from document_loaders import read_document
        path = self.folder / "policy.html"
        path.write_text(
            "<html><head><style>hidden_style</style><script>ignore_secret</script></head>"
            "<body><h1>Travel policy</h1><p>Book standard class rail.</p></body></html>",
            encoding="utf-8",
        )
        text = read_document(path)
        self.assertIn("Travel policy", text)
        self.assertIn("standard class rail", text)
        self.assertNotIn("hidden_style", text)
        self.assertNotIn("ignore_secret", text)

    def test_docx_extracts_paragraph_text(self) -> None:
        import zipfile
        from document_loaders import read_document
        path = self.folder / "policy.docx"
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Expense deadline is 10 business days.</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Manager approval is required above 100 pounds.</w:t></w:r></w:p>'
            '</w:body></w:document>'
        )
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", document_xml)
        text = read_document(path)
        self.assertIn("10 business days", text)
        self.assertIn("Manager approval", text)

    def test_loader_rejects_unknown_file_type(self) -> None:
        from document_loaders import DocumentLoadError, read_document
        path = self.folder / "policy.pdf"
        path.write_bytes(b"not a pdf")
        with self.assertRaises(DocumentLoadError):
            read_document(path)

    def test_rag_engine_indexes_csv_and_docx_with_source_names(self) -> None:
        import zipfile
        csv_path = self.folder / "approval.csv"
        csv_path.write_text("type,rule\nexpense,manager approval above 100 pounds\n", encoding="utf-8")
        docx_path = self.folder / "deadline.docx"
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Receipts must be submitted within 10 business days.</w:t></w:r></w:p>'
            '</w:body></w:document>'
        )
        with zipfile.ZipFile(docx_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", document_xml)
        chunks = load_chunks(self.folder)
        self.assertEqual({chunk.source for chunk in chunks}, {"approval.csv", "deadline.docx"})
        ranked = retrieve("When must receipts be submitted in business days?", chunks, top_k=2)
        self.assertTrue(ranked)
        self.assertEqual(ranked[0][1].source, "deadline.docx")



if __name__ == "__main__":
    unittest.main(verbosity=2)
