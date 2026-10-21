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
        self.assertIn("sessions.json", report["not_backed_up"])
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


if __name__ == "__main__":
    unittest.main()
