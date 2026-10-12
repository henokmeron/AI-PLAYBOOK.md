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
        path = self.root / "policy.exe"
        path.write_bytes(b"unsupported file type")
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


    def make_pdf(self, path: Path, text: str | None) -> None:
        """Create a minimal valid one-page text PDF without third-party PDF writers."""
        stream = b"" if text is None else (
            b"BT /F1 12 Tf 72 720 Td (" + text.encode("ascii") + b") Tj ET"
        )
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
            + stream + b"\nendstream",
        ]
        data = bytearray(b"%PDF-1.4\n%Test PDF\n")
        offsets = [0]
        for number, obj in enumerate(objects, start=1):
            offsets.append(len(data))
            data.extend(f"{number} 0 obj\n".encode("ascii"))
            data.extend(obj)
            data.extend(b"\nendobj\n")
        xref_offset = len(data)
        data.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        data.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        data.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
        )
        path.write_bytes(bytes(data))

    def test_pdf_text_is_extracted_with_page_marker(self) -> None:
        path = self.root / "expense-policy.pdf"
        self.make_pdf(path, "PDF receipt deadline is 10 business days.")
        text = read_document(path)
        self.assertIn("[Page 1]", text)
        self.assertIn("10 business days", text)

    def test_pdf_without_text_is_rejected_with_ocr_message(self) -> None:
        path = self.root / "scanned.pdf"
        self.make_pdf(path, None)
        with self.assertRaisesRegex(DocumentLoadError, "require OCR"):
            read_document(path)

    def test_malformed_pdf_is_rejected(self) -> None:
        path = self.root / "broken.pdf"
        path.write_bytes(b"not a PDF document")
        with self.assertRaises(DocumentLoadError):
            read_document(path)

    def test_rag_engine_indexes_pdf_and_preserves_source_name(self) -> None:
        path = self.root / "deadline.pdf"
        self.make_pdf(path, "Receipts must be submitted within 10 business days.")
        chunks = load_chunks(self.root)
        self.assertTrue(any(chunk.source == "deadline.pdf" for chunk in chunks))
        ranked = retrieve("When must receipts be submitted in business days?", chunks, top_k=1)
        self.assertTrue(ranked)
        self.assertEqual(ranked[0][1].source, "deadline.pdf")


    def make_xlsx(self, path: Path, rows: list[list[object]], sheet_name: str = "Budget") -> None:
        import openpyxl
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = sheet_name
        for row in rows:
            sheet.append(row)
        workbook.save(path)
        workbook.close()

    def test_xlsx_extracts_sheet_names_and_cell_values(self) -> None:
        path = self.root / "department-budget.xlsx"
        self.make_xlsx(
            path,
            [["Department", "Budget type", "Q4 budget"],
             ["Marketing", "planned amount", 27500]],
        )
        text = read_document(path)
        self.assertIn("Sheet: Budget", text)
        self.assertIn("Marketing", text)
        self.assertIn("27500", text)
        self.assertIn("C2/Q4 budget=27500", text)
        self.assertIn("A2/Department=Marketing", text)

    def test_xlsx_keeps_headers_with_row_values_for_rate_tables(self) -> None:
        path = self.root / "placement-rates.xlsx"
        self.make_xlsx(
            path,
            [
                ["Age band", "Placement type", "Daily rate"],
                ["0-4", "foster", 100],
                ["5-10", "residential", 150],
            ],
            sheet_name="Rates",
        )
        text = read_document(path)
        self.assertIn("Sheet: Rates | Row 2:", text)
        self.assertIn("B2/Placement type=foster", text)
        self.assertIn("C2/Daily rate=100", text)
        self.assertIn("C3/Daily rate=150", text)
        self.assertNotIn("C2/Daily rate=150", text)

    def test_xlsx_stacks_multi_row_headers_for_age_band_tables(self) -> None:
        path = self.root / "carer-fees.xlsx"
        self.make_xlsx(
            path,
            [
                [None, None, "Carer fee 2026/27", None, None],
                [None, "Aged 0-4 Years", "Aged 5-10 Years", "Aged 11-15 Years", "Aged 16-17 Years"],
                [
                    "Placement Type",
                    "New Daily Rate Excl. Respite",
                    "New Daily Rate Excl. Respite",
                    "New Daily Rate Excl. Respite",
                    "New Daily Rate Excl. Respite",
                ],
                ["Standard Placements", 66.3, 70.8, 76.5, 83],
                ["Complex Placements", 99.49800000000002, 106.2, 114.75, 124.5],
                ["Parent and Child Placements", 122.6, "N/A", "N/A", "N/A"],
            ],
            sheet_name="Sheet1",
        )
        text = read_document(path)
        self.assertIn("Aged 0-4 Years", text.split("B4/", 1)[1].split("=", 1)[0])
        self.assertRegex(text, r"B4/.*=66\.3")
        self.assertIn("B5/", text)
        self.assertIn("=99.498", text)
        self.assertNotIn("99.49800000000002", text)
        self.assertIn("N/A", text)
        # Every placement/data row remains present and retrievable as its own line.
        for row_number in (4, 5, 6):
            self.assertIn(f"Sheet: Sheet1 | Row {row_number}:", text)
        chunks = load_chunks(self.root)
        ranked = retrieve(
            "List every age band and placement type with daily rates",
            chunks,
            top_k=4,
        )
        self.assertTrue(ranked)
        joined = "\n".join(chunk.text for _, chunk in ranked)
        self.assertIn("Standard Placements", joined)
        self.assertIn("Complex Placements", joined)
        self.assertIn("Parent and Child Placements", joined)
        self.assertIn("Aged 16-17 Years", joined)

    def test_xlsx_float_artefacts_and_money_helpers(self) -> None:
        from decimal import Decimal

        from document_loaders import (
            format_money_gbp,
            render_xlsx_cell_value,
            sanitize_excel_float,
            weekly_from_daily,
        )

        stored = sanitize_excel_float(99.49800000000002)
        self.assertEqual(stored, Decimal("99.498"))
        self.assertEqual(render_xlsx_cell_value(99.49800000000002), "99.498")
        self.assertIn(
            "workbook displays £99.50",
            render_xlsx_cell_value(99.49800000000002, '"£"#,##0.00'),
        )
        weekly = weekly_from_daily(stored, days=7)
        self.assertEqual(weekly, Decimal("696.486"))
        self.assertEqual(format_money_gbp(weekly), "£696.49")
        self.assertEqual(render_xlsx_cell_value("N/A"), "N/A")

    def test_rag_engine_indexes_xlsx_and_preserves_source_name(self) -> None:
        path = self.root / "quarterly-results.xlsx"
        self.make_xlsx(
            path,
            [["Product", "Quarter", "Revenue"],
             ["Falcon", "Q3", 125000]],
            sheet_name="Sales",
        )
        chunks = load_chunks(self.root)
        self.assertTrue(any(chunk.source == "quarterly-results.xlsx" for chunk in chunks))
        ranked = retrieve("What was Falcon revenue in Q3?", chunks, top_k=1)
        self.assertTrue(ranked)
        self.assertEqual(ranked[0][1].source, "quarterly-results.xlsx")
        self.assertIn("Sheet: Sales", ranked[0][1].text)

    def test_malformed_xlsx_is_rejected(self) -> None:
        path = self.root / "broken.xlsx"
        path.write_bytes(b"not an Excel workbook")
        with self.assertRaises(DocumentLoadError):
            read_document(path)

    def test_xlsx_without_searchable_cells_is_rejected(self) -> None:
        path = self.root / "blank.xlsx"
        self.make_xlsx(path, [])
        with self.assertRaisesRegex(DocumentLoadError, "no searchable worksheet cell values"):
            read_document(path)




if __name__ == "__main__":
    unittest.main(verbosity=2)
