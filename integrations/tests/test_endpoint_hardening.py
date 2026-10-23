"""Test redaction, secret storage, and hardening features."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from integrations.errors import InvalidRequest
from integrations.redaction import (
    is_sensitive_looking,
    redact_check_summary,
    redact_report_before_upload,
    redact_text,
)


class RedactionTests(unittest.TestCase):
    def test_redact_usernames_from_windows_paths(self) -> None:
        text = r"C:\Users\Alice\Documents\report.txt"
        redacted = redact_text(text)
        self.assertNotIn("Alice", redacted)
        self.assertIn("<USERNAME>", redacted)
        self.assertIn(r"C:\Users\<USERNAME>\Documents", redacted)

    def test_redact_usernames_from_linux_paths(self) -> None:
        text = "/home/bob/.config/app.conf"
        redacted = redact_text(text)
        self.assertNotIn("bob", redacted)
        self.assertIn("<USERNAME>", redacted)

    def test_redact_emails(self) -> None:
        text = "Contact alice@example.com for support"
        redacted = redact_text(text)
        self.assertNotIn("alice@example.com", redacted)
        self.assertIn("<EMAIL>", redacted)

    def test_redact_long_tokens(self) -> None:
        text = "Bearer abc123def456ghi789jkl012mno345pqr678stu901vwx234yz"
        redacted = redact_text(text)
        self.assertIn("<TOKEN>", redacted)
        self.assertNotIn("abc123def456", redacted)

    def test_redact_guids(self) -> None:
        text = "Device ID: 12345678-1234-1234-1234-123456789abc"
        redacted = redact_text(text)
        self.assertNotIn("12345678-1234-1234-1234-123456789abc", redacted)
        self.assertIn("<GUID>", redacted)

    def test_redact_sids(self) -> None:
        text = "User SID: S-1-5-21-123456789-123456789-123456789-1001"
        redacted = redact_text(text)
        self.assertNotIn("S-1-5-21-123456789-123456789-123456789-1001", redacted)
        self.assertIn("<SID>", redacted)

    def test_redact_home_directory(self) -> None:
        home = str(Path.home())
        if len(home) > 3:
            text = f"File at {home}/secrets.txt"
            redacted = redact_text(text)
            self.assertNotIn(home, redacted)
            self.assertIn("<HOME>", redacted)

    def test_redact_current_user_env_var(self) -> None:
        user = os.environ.get("USERNAME") or os.environ.get("USER")
        if user and len(user) > 0:
            text = f"Logged in as {user}"
            redacted = redact_text(text)
            self.assertNotIn(user, redacted)
            self.assertIn("<USERNAME>", redacted)

    def test_redact_ip_addresses_when_requested(self) -> None:
        text = "Server at 192.168.1.100 port 8080"
        redacted = redact_text(text, redact_ips=True)
        self.assertNotIn("192.168.1.100", redacted)
        self.assertIn("<IP>", redacted)

    def test_ip_addresses_kept_by_default(self) -> None:
        text = "Server at 192.168.1.100 port 8080"
        redacted = redact_text(text, redact_ips=False)
        self.assertIn("192.168.1.100", redacted)

    def test_redact_check_summary(self) -> None:
        check = {
            "procedure_id": "win.storage.space",
            "summary": r"C:\Users\Alice\disk=100GB",
            "detail": "alice@example.com owns this disk",
            "ok": True,
        }
        redacted = redact_check_summary(check)
        self.assertNotIn("Alice", redacted["summary"])
        self.assertNotIn("alice@example.com", redacted["detail"])
        self.assertIn("<USERNAME>", redacted["summary"])
        self.assertIn("<EMAIL>", redacted["detail"])
        self.assertEqual(redacted["ok"], True)

    def test_redact_report_before_upload(self) -> None:
        report = {
            "os_family": "windows",
            "os_version": r"10.0.19045 at C:\Users\Alice\build",
            "disk_free_bytes": 100,
            "disk_total_bytes": 200,
            "memory_total_bytes": 8192,
            "boot_time_unix": 1000,
            "collected_at_unix": 2000,
            "checks": [
                {
                    "procedure_id": "win.storage.space",
                    "summary": r"disks=1; path=C:\Users\Alice\disk",
                }
            ],
        }
        redacted = redact_report_before_upload(report)
        self.assertNotIn(r"C:\Users\Alice", redacted["os_version"])
        self.assertIn("<USERNAME>", redacted["os_version"])
        self.assertNotIn(r"C:\Users\Alice", redacted["checks"][0]["summary"])
        self.assertIn("<USERNAME>", redacted["checks"][0]["summary"])

    def test_is_sensitive_looking(self) -> None:
        self.assertTrue(is_sensitive_looking(r"C:\Users\Alice\file.txt"))
        self.assertTrue(is_sensitive_looking("alice@example.com"))
        self.assertTrue(is_sensitive_looking("S-1-5-21-123456789-123456789-123456789-1001"))
        self.assertFalse(is_sensitive_looking("normal text without sensitive data"))


class SecretStorageTests(unittest.TestCase):
    def test_write_and_read_secret_with_metadata(self) -> None:
        from integrations.secret_storage import read_secret, write_secret

        secret = "x" * 40
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device-secret"
            write_secret(path, secret, metadata={"device_id": "abc123"})
            read_back, metadata = read_secret(path)
            self.assertEqual(read_back, secret)
            self.assertIn("device_id", metadata)
            self.assertEqual(metadata["device_id"], "abc123")
            self.assertIn("storage_type", metadata)
            if os.name == "nt":
                self.assertEqual(metadata["storage_type"], "dpapi")
            else:
                self.assertEqual(metadata["storage_type"], "private_file")

    def test_secret_file_is_private(self) -> None:
        from integrations.secret_storage import write_secret
        from integrations.state_guard import assert_private

        secret = "y" * 40
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device-secret"
            write_secret(path, secret)
            assert_private(path)

    def test_migrate_to_dpapi_on_windows(self) -> None:
        from integrations.secret_storage import migrate_to_dpapi, read_secret, write_secret

        if os.name != "nt":
            self.skipTest("DPAPI is only available on Windows")

        secret = "z" * 40
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device-secret"
            
            write_secret(path, secret, metadata={"storage_type": "private_file"})
            
            migrated = migrate_to_dpapi(path)
            self.assertTrue(migrated, "Migration should have occurred")
            
            read_back, metadata = read_secret(path)
            self.assertEqual(read_back, secret)
            self.assertEqual(metadata["storage_type"], "dpapi")

            second_migrate = migrate_to_dpapi(path)
            self.assertFalse(second_migrate, "Should not migrate again")

    def test_reject_short_secret(self) -> None:
        from integrations.secret_storage import write_secret

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device-secret"
            with self.assertRaises(InvalidRequest):
                write_secret(path, "short")

    def test_read_legacy_plaintext_secret(self) -> None:
        from integrations.secret_storage import read_secret

        secret = "legacy-plaintext-secret-value-here"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device-secret"
            
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            descriptor = os.open(path, flags, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(secret)
            
            from integrations.state_guard import restrict_private
            try:
                restrict_private(path)
            except Exception:
                pass
            
            read_back, metadata = read_secret(path)
            self.assertEqual(read_back, secret)
            self.assertEqual(metadata.get("storage_type"), "legacy_plaintext")
            self.assertEqual(metadata.get("schema_version"), 0)

    def test_remove_secret(self) -> None:
        from integrations.secret_storage import remove_secret, write_secret

        secret = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device-secret"
            write_secret(path, secret)
            self.assertTrue(path.is_file())
            remove_secret(path)
            self.assertFalse(path.is_file())


class SchemaVersionTests(unittest.TestCase):
    def test_report_with_schema_version_and_agent_version(self) -> None:
        from integrations.endpoint import normalise_report

        payload = {
            "device_id": "a" * 32,
            "display_name": "Office PC",
            "os_family": "windows",
            "os_version": "10.0.19045",
            "disk_free_bytes": 100,
            "disk_total_bytes": 200,
            "memory_total_bytes": 8192,
            "boot_time_unix": 1000,
            "collected_at_unix": 2000,
            "schema_version": 1,
            "agent_version": "0.2.0",
        }
        cleaned = normalise_report(payload)
        self.assertEqual(cleaned["schema_version"], 1)
        self.assertEqual(cleaned["agent_version"], "0.2.0")

    def test_report_without_optional_fields_still_valid(self) -> None:
        from integrations.endpoint import normalise_report

        payload = {
            "device_id": "b" * 32,
            "display_name": "Office PC",
            "os_family": "windows",
            "os_version": "10.0.19045",
            "disk_free_bytes": 100,
            "disk_total_bytes": 200,
            "memory_total_bytes": 8192,
            "boot_time_unix": 1000,
            "collected_at_unix": 2000,
        }
        cleaned = normalise_report(payload)
        self.assertNotIn("schema_version", cleaned)
        self.assertNotIn("agent_version", cleaned)

    def test_unknown_fields_still_rejected(self) -> None:
        from integrations.endpoint import normalise_report

        payload = {
            "device_id": "c" * 32,
            "display_name": "Office PC",
            "os_family": "windows",
            "os_version": "10.0.19045",
            "disk_free_bytes": 100,
            "disk_total_bytes": 200,
            "memory_total_bytes": 8192,
            "boot_time_unix": 1000,
            "collected_at_unix": 2000,
            "unknown_field": "rejected",
        }
        with self.assertRaises(InvalidRequest):
            normalise_report(payload)


if __name__ == "__main__":
    unittest.main()
