#!/usr/bin/env python3
"""Unit tests for the model registry loader; no GPU required."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELS = HERE.parent
ROOT = MODELS.parent
sys.path.insert(0, str(MODELS))

try:
    import yaml  # noqa: F401
except ImportError:
    yaml = None  # type: ignore

from registry_loader import (  # noqa: E402
    get_model,
    load_registry,
    public_model_catalog,
    resolve_requested_model,
    upstream_model_token,
)


@unittest.skipUnless(yaml is not None, "PyYAML is required for registry loader tests")
class RegistryLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_registry(MODELS / "registry.yaml")

    def test_schema_and_production_default_remain_gemma(self) -> None:
        self.assertEqual(self.registry.get("schema_version"), 2)
        self.assertEqual(self.registry.get("production"), "gemma-4-31b-it")
        defaults = self.registry.get("defaults") or {}
        self.assertEqual(defaults.get("active_model_id"), "gemma-4-31b-it")
        self.assertFalse(defaults.get("concurrent_gpu_models"))

    def test_qwen_candidate_is_registered_without_becoming_production(self) -> None:
        qwen = get_model(self.registry, "qwen3.5-27b")
        self.assertEqual(qwen["license"], "Apache-2.0")
        self.assertEqual(qwen["status"], "integration-candidate")
        self.assertEqual(qwen["revision"], "fc05daec18b0a78c049392ed2e771dde82bdf654")
        self.assertIn("Qwen3.5-27B", qwen["runpod_path"])
        serving = qwen["serving"]
        self.assertEqual(serving["listen_port"], 8002)
        self.assertNotEqual(serving["listen_port"], 8000)
        self.assertEqual(self.registry["production"], "gemma-4-31b-it")

    def test_public_catalog_omits_filesystem_paths(self) -> None:
        catalog = public_model_catalog(self.registry)
        blob = str(catalog)
        self.assertNotIn("/workspace", blob)
        self.assertNotIn("runpod_path", blob)
        ids = {item["id"] for item in catalog}
        self.assertIn("gemma-4-31b-it", ids)
        self.assertIn("qwen3.5-27b", ids)
        gemma = next(item for item in catalog if item["id"] == "gemma-4-31b-it")
        self.assertTrue(gemma["is_production_default"])

    def test_resolve_aliases_and_default(self) -> None:
        self.assertEqual(resolve_requested_model(self.registry, None), "gemma-4-31b-it")
        self.assertEqual(
            resolve_requested_model(self.registry, "Qwen/Qwen3.5-27B"),
            "qwen3.5-27b",
        )
        self.assertEqual(
            upstream_model_token(self.registry, "qwen3.5-27b"),
            "/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654",
        )

    def test_invalid_registry_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_text("candidates: []\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_registry(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
