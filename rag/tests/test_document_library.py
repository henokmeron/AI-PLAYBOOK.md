#!/usr/bin/env python3
"""No-GPU unit tests for safe document collection storage operations."""
from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from document_library import (
    DocumentLibraryError,
    delete_document,
    list_documents,
    store_document,
    validate_collection_name,
    validate_filename,
)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
