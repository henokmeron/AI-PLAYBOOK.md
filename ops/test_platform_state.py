"""Operator backup and restore. These tests do not print passwords or hashes."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops.platform_state import PlatformStateError, assess, layout_report, main
from web.auth.service import AuthService

PASSWORD = "test-operator-password"


def _provision(directory: Path) -> None:
    AuthService(directory).create_operator(
        "ada",
        PASSWORD,
        "admin",
        allow_first_admin=True,
    )


class PlatformStateTests(unittest.TestCase):
    def test_layout_separates_secrets_from_weights(self) -> None:
        report = layout_report(volume_mounted=True)
        self.assertFalse(report["operator_live_durable"])
        self.assertFalse(report["runtime_env_durable"])
        self.assertIn("operators.json", report["operator_backup_contains"])
        self.assertIn("endpoint-devices.json", report["endpoint_backup_contains"])
        self.assertFalse(report["endpoint_live_durable"])
        self.assertEqual(report["endpoint_live_file"], "/tmp/endpoint-devices.json")
        self.assertIn("sessions.json", report["not_backed_up"])
        self.assertIn("/tmp/platform-gateway.key", report["not_backed_up"])
        self.assertIn("/tmp/microsoft-365-token.json", report["not_backed_up"])
        self.assertNotIn("password", json.dumps(report).casefold())

    def test_backup_restores_hashes_without_sessions_or_the_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live"
            backup = root / "backups"
            _provision(live)
            (live / "sessions.json").write_text('{"sessions":[{"csrf_token":"session-secret-token"}]}', encoding="utf-8")
            status = assess(live_dir=live, backup_dir=backup, apply=True)
            self.assertTrue(status["ready"])
            self.assertEqual(status["action"], "backed_up")
            self.assertFalse(status["sessions_restored"])
            blob = next(backup.rglob("operators.json")).read_text(encoding="utf-8")
            self.assertNotIn(PASSWORD, blob)
            self.assertNotIn("session-secret-token", blob)
            os.remove(live / "operators.json")
            os.remove(live / "sessions.json")
            restored = assess(live_dir=live, backup_dir=backup, apply=True)
            self.assertEqual(restored["action"], "restored")
            self.assertGreaterEqual(restored["admins"], 1)
            self.assertFalse(restored["sessions_restored"])
            self.assertFalse((live / "sessions.json").exists())
            loaded = json.loads((live / "operators.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded["operators"][0]["username"], "ada")
            self.assertNotIn(PASSWORD, json.dumps(loaded))

    def test_check_does_not_write_a_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live"
            backup = root / "backups"
            _provision(live)
            status = assess(live_dir=live, backup_dir=backup, apply=False)
            self.assertEqual(status["action"], "live")
            self.assertEqual(status["backup"], "would_backup")
            self.assertFalse(backup.exists())

    def test_plaintext_password_is_refused_and_not_echoed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live"
            live.mkdir()
            secret = "plain-operator-secret"
            (live / "operators.json").write_text(json.dumps({"operators": [{
                "operator_id": "abc",
                "username": "ada",
                "password": secret,
                "role": "admin",
                "disabled": False,
            }]}), encoding="utf-8")
            from integrations.state_guard import restrict_private

            restrict_private(live)
            restrict_private(live / "operators.json")
            with self.assertRaises(PlatformStateError) as caught:
                assess(live_dir=live, backup_dir=None, apply=True)
            self.assertNotIn(secret, str(caught.exception))

    def test_symlink_operator_file_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live"
            _provision(live)
            with patch.object(Path, "is_symlink", lambda self: self.name == "operators.json"):
                with self.assertRaises(PlatformStateError) as caught:
                    assess(live_dir=live, backup_dir=None, apply=False)
            self.assertNotIn(PASSWORD, str(caught.exception))
            self.assertIn("symbolic link", str(caught.exception))

    def test_bad_checksum_is_not_restored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live"
            backup = root / "backups"
            _provision(live)
            assess(live_dir=live, backup_dir=backup, apply=True)
            blob = next(backup.rglob("operators.json"))
            blob.write_bytes(blob.read_bytes() + b" ")
            os.remove(live / "operators.json")
            with self.assertRaises(PlatformStateError):
                assess(live_dir=live, backup_dir=backup, apply=True)
            self.assertFalse((live / "operators.json").exists())

    def test_cli_check_exits_when_no_administrator_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["--check", "--live-dir", tmp])
            self.assertEqual(code, 2)

    def test_endpoint_backup_restores_hashes_without_the_secret(self) -> None:
        from ops.platform_state import assess_endpoint

        secret = "d" * 32
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live_dir = root / "state"
            live_dir.mkdir()
            live = live_dir / "endpoint-devices.json"
            backup = root / "endpoint-backups"
            from integrations.endpoint import DeviceRegistry

            registry = DeviceRegistry(live)
            created = registry.create_enrolment("local-console")
            code = created["enrolment_code"]
            registry.enrol(code, "Office PC", secret)
            status = assess_endpoint(live_file=live, backup_dir=backup, apply=True)
            self.assertEqual(status["action"], "backed_up")
            self.assertFalse(status["secrets_copied"])
            self.assertGreaterEqual(status["devices"], 1)
            blob = next(backup.rglob("endpoint-devices.json")).read_text(encoding="utf-8")
            self.assertNotIn(secret, blob)
            self.assertNotIn(code, blob)
            self.assertNotIn("device_secret", blob)
            os.remove(live)
            restored = assess_endpoint(live_file=live, backup_dir=backup, apply=True)
            self.assertEqual(restored["action"], "restored")
            self.assertGreaterEqual(restored["devices"], 1)
            reloaded = DeviceRegistry(live)
            self.assertEqual(reloaded.enrolled_count("local-console"), 1)
            again = json.loads(live.read_text(encoding="utf-8"))
            self.assertNotIn(secret, json.dumps(again))
            self.assertNotIn(code, json.dumps(again))

    def test_endpoint_save_mirrors_when_the_volume_dir_is_configured(self) -> None:
        secret = "e" * 32
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "endpoint-devices.json"
            backup = root / "endpoint-backups"
            from integrations.endpoint import DeviceRegistry

            with patch.dict(os.environ, {"ENDPOINT_BACKUP_DIR": str(backup)}):
                registry = DeviceRegistry(live)
                created = registry.create_enrolment("local-console")
                registry.enrol(created["enrolment_code"], "Office PC", secret)
            blobs = list(backup.rglob("endpoint-devices.json"))
            self.assertTrue(blobs)
            stored = "\n".join(path.read_text(encoding="utf-8") for path in blobs)
            self.assertNotIn(secret, stored)
            self.assertNotIn(created["enrolment_code"], stored)

    def test_operator_save_mirrors_hashes_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live"
            backup = root / "operator-backups"
            with patch.dict(os.environ, {"OPERATOR_BACKUP_DIR": str(backup)}):
                _provision(live)
            blob = next(backup.rglob("operators.json")).read_text(encoding="utf-8")
            self.assertNotIn(PASSWORD, blob)
            self.assertNotIn("sessions", blob)

    def test_plaintext_device_secret_is_not_copied(self) -> None:
        from ops.platform_state import PlatformStateError, assess_endpoint

        secret = "raw-device-secret-value-not-a-hash"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "endpoint-devices.json"
            backup = root / "endpoint-backups"
            live.write_text(json.dumps({
                "version": 1,
                "codes": [],
                "devices": [{
                    "tenant_id": "local-console",
                    "device_id": "ab" * 16,
                    "display_name": "Office PC",
                    "device_secret": secret,
                    "secret_hash": "cd" * 32,
                    "status": "enrolled",
                }],
            }), encoding="utf-8")
            from integrations.state_guard import restrict_private

            restrict_private(live)
            with self.assertRaises(PlatformStateError) as caught:
                assess_endpoint(live_file=live, backup_dir=backup, apply=True)
            self.assertNotIn(secret, str(caught.exception))
            self.assertFalse(backup.exists())

    def test_bad_endpoint_checksum_is_not_restored(self) -> None:
        from ops.platform_state import assess_endpoint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "endpoint-devices.json"
            backup = root / "endpoint-backups"
            from integrations.endpoint import DeviceRegistry

            registry = DeviceRegistry(live)
            created = registry.create_enrolment("local-console")
            registry.enrol(created["enrolment_code"], "Office PC", "f" * 32)
            assess_endpoint(live_file=live, backup_dir=backup, apply=True)
            blob = next(backup.rglob("endpoint-devices.json"))
            blob.write_bytes(blob.read_bytes() + b" ")
            os.remove(live)
            restored = assess_endpoint(live_file=live, backup_dir=backup, apply=True)
            self.assertEqual(restored["action"], "none")
            self.assertFalse(live.exists())
            self.assertNotIn(created["enrolment_code"], json.dumps(restored))

    def test_existing_endpoint_file_is_not_replaced(self) -> None:
        from ops.platform_state import PlatformStateError, restore_endpoint_backup

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "endpoint-devices.json"
            backup = root / "endpoint-backups"
            from integrations.endpoint import DeviceRegistry

            registry = DeviceRegistry(live)
            created = registry.create_enrolment("local-console")
            registry.enrol(created["enrolment_code"], "Office PC", "a" * 32)
            assess_from = __import__("ops.platform_state", fromlist=["assess_endpoint"]).assess_endpoint
            assess_from(live_file=live, backup_dir=backup, apply=True)
            before = live.read_bytes()
            with self.assertRaises(PlatformStateError):
                restore_endpoint_backup(backup, live)
            self.assertEqual(live.read_bytes(), before)

    def test_shared_tmp_is_not_a_dedicated_directory(self) -> None:
        from ops.platform_state import _dedicated_directory

        self.assertFalse(_dedicated_directory(Path("/tmp")))
        self.assertFalse(_dedicated_directory(Path("/workspace")))

    def test_missing_endpoint_file_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["--check", "--endpoint-live", str(Path(tmp) / "missing.json")])
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
