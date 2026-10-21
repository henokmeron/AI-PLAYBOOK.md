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

if yaml is not None:
    from registry_loader import (  # noqa: E402
        get_model,
        load_registry,
        public_model_catalog,
        matching_upstream_model_id,
        resolve_requested_model,
        selection_decision,
        upstream_model_token,
    )


@unittest.skipUnless(yaml is not None, "PyYAML is required for registry loader tests")
class RegistryLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_registry(MODELS / "registry.yaml")

    def test_schema_and_production_default_is_qwen_first_release(self) -> None:
        self.assertEqual(self.registry.get("schema_version"), 2)
        self.assertEqual(self.registry.get("production"), "qwen3.5-27b")
        defaults = self.registry.get("defaults") or {}
        self.assertEqual(defaults.get("active_model_id"), "qwen3.5-27b")
        self.assertFalse(defaults.get("concurrent_gpu_models"))
        self.assertFalse(defaults.get("silent_model_fallback"))

    def test_qwen_is_first_release_primary_with_gemma_alternative(self) -> None:
        qwen = get_model(self.registry, "qwen3.5-27b")
        gemma = get_model(self.registry, "gemma-4-31b-it")
        self.assertEqual(qwen["license"], "Apache-2.0")
        self.assertEqual(qwen["status"], "first-release-primary")
        self.assertEqual(qwen["revision"], "fc05daec18b0a78c049392ed2e771dde82bdf654")
        self.assertIn("Qwen3.5-27B", qwen["runpod_path"])
        self.assertEqual(qwen["evaluation_status"], "first-release-primary-2026-10-13")
        serving = qwen["serving"]
        self.assertEqual(serving["listen_port"], 8002)
        self.assertNotEqual(serving["listen_port"], 8000)
        self.assertEqual(self.registry["production"], "qwen3.5-27b")
        self.assertTrue(gemma.get("selection_eligible", True))
        self.assertEqual(gemma["serving"]["listen_port"], 8000)

    def test_selection_decision_blocks_cross_runtime_without_silent_fallback(self) -> None:
        ok = selection_decision(self.registry, "qwen3.5-27b", upstream_port=8002)
        self.assertTrue(ok["allowed"])
        blocked = selection_decision(self.registry, "qwen3.5-27b", upstream_port=8000)
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["reason"], "runtime_mismatch")

    def test_public_catalog_omits_filesystem_paths(self) -> None:
        catalog = public_model_catalog(self.registry)
        blob = str(catalog)
        self.assertNotIn("/workspace", blob)
        self.assertNotIn("runpod_path", blob)
        ids = {item["id"] for item in catalog}
        self.assertIn("gemma-4-31b-it", ids)
        self.assertIn("qwen3.5-27b", ids)
        gemma = next(item for item in catalog if item["id"] == "gemma-4-31b-it")
        qwen = next(item for item in catalog if item["id"] == "qwen3.5-27b")
        self.assertFalse(gemma["is_production_default"])
        self.assertTrue(qwen["is_production_default"])

    def test_resolve_aliases_and_default(self) -> None:
        self.assertEqual(resolve_requested_model(self.registry, None), "qwen3.5-27b")
        self.assertEqual(
            resolve_requested_model(self.registry, "Qwen/Qwen3.5-27B"),
            "qwen3.5-27b",
        )
        self.assertEqual(
            upstream_model_token(self.registry, "qwen3.5-27b"),
            "/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654",
        )

    def test_unknown_model_is_rejected(self) -> None:
        decision = selection_decision(self.registry, "not-a-real-model", upstream_port=8002)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "unknown_model")
        self.assertIsNone(decision["resolved_id"])

    def test_omitted_model_is_qwen_only_when_that_checkpoint_is_served(self) -> None:
        decision = selection_decision(self.registry, None, upstream_port=8002)
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["resolved_id"], "qwen3.5-27b")
        self.assertEqual(decision["reason"], "default")
        qwen_path = upstream_model_token(self.registry, "qwen3.5-27b")
        self.assertEqual(
            matching_upstream_model_id(self.registry, "qwen3.5-27b", [qwen_path]),
            qwen_path,
        )
        self.assertIsNone(
            matching_upstream_model_id(
                self.registry,
                "qwen3.5-27b",
                ["/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it"],
            )
        )

    def test_invalid_registry_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_text("candidates: []\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_registry(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
