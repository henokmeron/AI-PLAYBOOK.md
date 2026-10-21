"""Retrieval acceptance probe. No model process is started."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops_centre.rag_probe import probe_acceptance, write_acceptance_corpus


class RagProbeTests(unittest.TestCase):
    def test_ingestion_retrieval_citation_abstention_and_injection_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "docs"
            write_acceptance_corpus(folder)
            report = probe_acceptance(folder)
            self.assertEqual(report["state"], "HEALTHY")
            self.assertTrue(report["grounded"])
            self.assertTrue(report["abstained"])
            self.assertFalse(report["model_called"])
            self.assertEqual(report["citation_file"], "warranty.txt")
            self.assertTrue(report["permission_blocked"])
            self.assertTrue(report["instruction_flagged"])
            self.assertTrue(report["instruction_treated_as_data"])
            self.assertNotIn("4412", str(report))


if __name__ == "__main__":
    unittest.main()
