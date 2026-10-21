"""Preflight fixtures. These tests do not start a service or print a secret."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ops.preflight import active_operator_count, probe_port, run_preflight


def _ready_env() -> dict[str, str]:
    return {
        "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010",
        "REPAIR_DEVICE_STATE": r"C:\state\device.json",
        "MICROSOFT_CLIENT_ID": "not-a-real-client",
        "PLATFORM_API_KEY": "super-secret-value",
    }


def _report(**overrides):
    env = _ready_env()
    ports = {8002: True, 8010: True, 8080: True}
    kwargs = {
        "disk_free_bytes": 2 << 30,
        "ports_open": ports,
        "yaml_ok": True,
        "operator_count": 1,
    }
    kwargs.update(overrides)
    if "env" in kwargs:
        env = kwargs.pop("env")
    return run_preflight(env, **kwargs)


class PreflightTests(unittest.TestCase):
    def test_complete_fixture_is_ready_and_hides_secrets(self) -> None:
        report = _report()
        self.assertTrue(report["ready"])
        blob = json.dumps(report)
        self.assertNotIn("not-a-real-client", blob)
        self.assertNotIn("super-secret-value", blob)
        self.assertIn("MICROSOFT_CLIENT_ID is present", blob)

    def test_missing_credentials_model_and_operators_fail_closed(self) -> None:
        report = _report(
            env={"PLATFORM_GATEWAY_URL": "http://example.com:8010", "REPAIR_DEVICE_STATE": "relative.json"},
            disk_free_bytes=100,
            ports_open={8002: False, 8010: False, 8080: False},
            yaml_ok=False,
            operator_count=None,
        )
        self.assertFalse(report["ready"])
        by_name = {item["name"]: item for item in report["checks"]}
        self.assertEqual(by_name["gateway_url"]["status"], "fail")
        self.assertEqual(by_name["repair_state"]["status"], "fail")
        self.assertEqual(by_name["disk"]["status"], "fail")
        self.assertEqual(by_name["pyyaml"]["status"], "fail")
        self.assertEqual(by_name["microsoft"]["status"], "not_configured")
        self.assertIn("unset", by_name["microsoft"]["detail"])
        self.assertEqual(by_name["model"]["status"], "not_configured")
        self.assertIn("NOT CONFIGURED", by_name["model"]["detail"])
        self.assertIn("was not started", by_name["model"]["detail"])
        self.assertEqual(by_name["gateway"]["status"], "not_configured")
        self.assertEqual(by_name["operators"]["status"], "fail")

    def test_zero_operators_and_closed_probe_do_not_listen(self) -> None:
        report = _report(operator_count=0, ports_open={8002: False, 8010: True, 8080: True})
        self.assertFalse(report["ready"])
        self.assertFalse(probe_port(1, timeout=0.1))
        text = Path(__file__).resolve().parent.joinpath("preflight.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", text)
        self.assertNotIn("START.sh", text)

    def test_operator_file_count_ignores_hashes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operators.json"
            path.write_text(json.dumps({
                "operators": [
                    {"operator_id": "a", "username": "ada", "password_hash": "hash-secret", "disabled": False},
                    {"operator_id": "b", "username": "bea", "password_hash": "other-secret", "disabled": True},
                ]
            }), encoding="utf-8")
            self.assertEqual(active_operator_count(path), 1)
            self.assertIsNone(active_operator_count(Path(tmp) / "missing.json"))
            path.write_text("{", encoding="utf-8")
            self.assertIsNone(active_operator_count(path))


if __name__ == "__main__":
    unittest.main()
