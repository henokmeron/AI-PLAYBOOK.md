#!/usr/bin/env python3
"""No-GPU unit tests for safe document collection storage operations."""
from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from document_library import (
    DocumentLibraryError,
    delete_document,
    list_documents,
    sanitize_history_for_collection,
    store_document,
    validate_collection_name,
    validate_filename,
    verify_document_removed,
    verify_document_searchable,
)
from rag_engine import load_chunks, retrieve


class DocumentLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="rag-document-library-test-")
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def encoded(self, text: str) -> str:
        return base64.b64encode(text.encode("utf-8")).decode("ascii")

    def test_valid_collection_name_is_accepted(self) -> None:
        self.assertEqual(validate_collection_name("finance-q4_2026"), "finance-q4_2026")

    def test_collection_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(DocumentLibraryError):
            validate_collection_name("../outside")

    def test_filename_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(DocumentLibraryError):
            validate_filename("../outside.md")
        with self.assertRaises(DocumentLibraryError):
            validate_filename("folder\\outside.md")

    def test_unsupported_extension_is_rejected(self) -> None:
        with self.assertRaises(DocumentLibraryError):
            validate_filename("malware.exe")

    def test_upload_creates_collection_and_returns_metadata(self) -> None:
        result = store_document(self.root, "finance", "budget.md", self.encoded("Budget is 10." ))
        self.assertEqual(result["filename"], "budget.md")
        self.assertEqual(result["collection"], "finance")
        self.assertEqual(result["size_bytes"], len(b"Budget is 10."))
        self.assertEqual((self.root / "finance" / "budget.md").read_text(encoding="utf-8"), "Budget is 10.")

    def test_duplicate_upload_is_refused_by_default(self) -> None:
        store_document(self.root, "finance", "budget.md", self.encoded("One."))
        with self.assertRaises(FileExistsError):
            store_document(self.root, "finance", "budget.md", self.encoded("Two."))
        self.assertEqual((self.root / "finance" / "budget.md").read_text(encoding="utf-8"), "One.")

    def test_overwrite_requires_explicit_true(self) -> None:
        store_document(self.root, "finance", "budget.md", self.encoded("One."))
        store_document(self.root, "finance", "budget.md", self.encoded("Two."), overwrite=True)
        self.assertEqual((self.root / "finance" / "budget.md").read_text(encoding="utf-8"), "Two.")

    def test_list_returns_metadata_not_contents(self) -> None:
        store_document(self.root, "finance", "budget.csv", self.encoded("secret,100"))
        docs = list_documents(self.root, "finance")
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["filename"], "budget.csv")
        self.assertNotIn("secret", str(docs))

    def test_delete_removes_only_requested_document(self) -> None:
        store_document(self.root, "finance", "one.txt", self.encoded("One."))
        store_document(self.root, "finance", "two.txt", self.encoded("Two."))
        result = delete_document(self.root, "finance", "one.txt")
        self.assertTrue(result["deleted"])
        self.assertEqual([item["filename"] for item in list_documents(self.root, "finance")], ["two.txt"])

    def test_delete_missing_document_reports_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            delete_document(self.root, "finance", "missing.txt")

    def test_invalid_base64_is_rejected(self) -> None:
        with self.assertRaises(DocumentLibraryError):
            store_document(self.root, "finance", "budget.md", "not-base64!!!")

    def test_empty_upload_is_rejected(self) -> None:
        with self.assertRaises(DocumentLibraryError):
            store_document(self.root, "finance", "budget.md", "")


    def test_invalid_pdf_is_rejected_before_storage(self) -> None:
        with self.assertRaises(DocumentLibraryError):
            store_document(self.root, "finance", "broken.pdf", self.encoded("not a PDF"))
        self.assertFalse((self.root / "finance" / "broken.pdf").exists())

    def test_document_with_no_extractable_text_is_rejected(self) -> None:
        with self.assertRaisesRegex(DocumentLibraryError, "no extractable text"):
            store_document(self.root, "finance", "blank.md", self.encoded("   "))
        self.assertFalse((self.root / "finance" / "blank.md").exists())

    def test_delete_and_replace_remove_old_chunks_from_retrieval(self) -> None:
        store_document(
            self.root,
            "my-docs",
            "rates-a.md",
            self.encoded("UNIQUE_TOKEN_ALPHA daily rate for ages 0-4 is 111."),
        )
        searchable = verify_document_searchable(self.root, "my-docs", "rates-a.md")
        self.assertTrue(searchable["searchable"])
        self.assertGreaterEqual(searchable["chunk_count"], 1)
        chunks = load_chunks(self.root / "my-docs")
        ranked = retrieve("UNIQUE_TOKEN_ALPHA ages 0-4 daily rate", chunks, top_k=3)
        self.assertTrue(ranked)
        self.assertEqual(ranked[0][1].source, "rates-a.md")

        delete_document(self.root, "my-docs", "rates-a.md")
        removed = verify_document_removed(self.root, "my-docs", "rates-a.md")
        self.assertTrue(removed["removed_from_index"])
        self.assertNotIn("rates-a.md", removed["indexed_sources"])

        store_document(
            self.root,
            "my-docs",
            "rates-b.md",
            self.encoded("UNIQUE_TOKEN_BETA Surrey Council weekly fee ages 0-4 is 222."),
        )
        verify_document_searchable(self.root, "my-docs", "rates-b.md")
        chunks_after = load_chunks(self.root / "my-docs")
        sources = {chunk.source for chunk in chunks_after}
        self.assertEqual(sources, {"rates-b.md"})
        self.assertFalse(any("UNIQUE_TOKEN_ALPHA" in chunk.text for chunk in chunks_after))
        ranked_old = retrieve("UNIQUE_TOKEN_ALPHA", chunks_after, top_k=3)
        self.assertFalse(any("UNIQUE_TOKEN_ALPHA" in chunk.text for _, chunk in ranked_old))
        self.assertFalse(any(chunk.source == "rates-a.md" for _, chunk in ranked_old))
        ranked_new = retrieve("UNIQUE_TOKEN_BETA Surrey Council weekly fee", chunks_after, top_k=3)
        self.assertTrue(ranked_new)
        self.assertEqual(ranked_new[0][1].source, "rates-b.md")

    def test_overwrite_same_filename_replaces_searchable_content(self) -> None:
        store_document(self.root, "my-docs", "fees.md", self.encoded("OLD_ONLY_TOKEN fee 10"))
        store_document(
            self.root,
            "my-docs",
            "fees.md",
            self.encoded("NEW_ONLY_TOKEN fee 20"),
            overwrite=True,
        )
        verify_document_searchable(self.root, "my-docs", "fees.md")
        chunks = load_chunks(self.root / "my-docs")
        joined = "\n".join(chunk.text for chunk in chunks)
        self.assertIn("NEW_ONLY_TOKEN", joined)
        self.assertNotIn("OLD_ONLY_TOKEN", joined)
        ranked = retrieve("OLD_ONLY_TOKEN", chunks, top_k=3)
        self.assertFalse(any("OLD_ONLY_TOKEN" in chunk.text for _, chunk in ranked))

    def test_history_sanitizer_strips_deleted_document_answers(self) -> None:
        history = [
            {"role": "user", "content": "What is the fee?"},
            {
                "role": "assistant",
                "content": (
                    "The Banya fee is 99.498 from "
                    "Banya fee to carers – Carer Pay Rates – Effective from 1 April 2026.xlsx "
                    "[Source 1: file=Banya fee to carers – Carer Pay Rates – Effective from 1 April 2026.xlsx]"
                ),
            },
        ]
        cleaned = sanitize_history_for_collection(
            history,
            ["Placement Fees - Fee to LA (Local authority) -  Effective from 1 July 2026 -.xlsx"],
        )
        self.assertEqual(cleaned[0]["content"], "What is the fee?")
        self.assertIn("omitted because it cited document", cleaned[1]["content"].casefold())
        self.assertNotIn("99.498", cleaned[1]["content"])
        quoted = sanitize_history_for_collection(
            [{
                "role": "user",
                "content": (
                    "Use 99.498 from "
                    "Banya fee to carers – Carer Pay Rates – Effective from 1 April 2026.xlsx"
                ),
            }],
            ["Placement Fees - Fee to LA (Local authority) -  Effective from 1 July 2026 -.xlsx"],
        )
        self.assertIn("omitted because it cited document", quoted[0]["content"].casefold())
        self.assertNotIn("99.498", quoted[0]["content"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
