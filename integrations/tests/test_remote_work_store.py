"""Tests for durable WorkStore with SQLite persistence."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from integrations.remote_work import (
    APPROVAL_TTL_SECONDS,
    WorkRefused,
    WorkStore,
    approve_work_order,
    claim_job,
    complete_job,
    create_work_order,
    post_heartbeat,
    register_enrolled_device,
)

DEVICE = "a" * 32
OTHER = "b" * 32
OPERATOR = "it.operator"
APPROVER = "approver"
PIN = "0123456789abcdef" * 4
STAGING = r"C:\ProgramData\RemoteIT\staging"
DEST = r"C:\ProgramData\RemoteIT\staging\package.cab"
UTC = "2026-10-23T23:00:00Z"


class TestDurableStore(unittest.TestCase):
    """Test SQLite persistence and restart semantics."""

    def test_survive_restart_round_trip(self) -> None:
        """Create, approve, reopen: state and audit intact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "work.db")
            
            store1 = WorkStore(path=db_path)
            register_enrolled_device(store1, DEVICE)
            
            order = create_work_order(
                store1,
                device_id=DEVICE,
                action="repair.service.restart",
                target="Spooler",
                operator_id=OPERATOR,
                params={"start_type": "automatic", "status": "stopped"},
            )
            order_id = order["id"]
            
            approve_work_order(store1, order_id, APPROVER)
            
            audit_count_before_reopen = len(store1.audit)
            self.assertTrue(DEVICE in store1.enrolled)
            
            store2 = WorkStore(path=db_path)
            
            self.assertTrue(DEVICE in store2.enrolled)
            self.assertEqual(len(store2.orders), 1)
            self.assertEqual(len(store2.audit), audit_count_before_reopen)
            
            reopened = store2.orders[order_id]
            self.assertEqual(reopened["id"], order_id)
            self.assertEqual(reopened["device_id"], DEVICE)
            self.assertEqual(reopened["action"], "repair.service.restart")
            self.assertEqual(reopened["target"], "Spooler")
            self.assertEqual(reopened["state"], "approved")
            self.assertIsNotNone(reopened["approval"])
            self.assertEqual(reopened["approval"]["operator_id"], APPROVER)
            self.assertFalse(reopened["approval"]["used"])

    def test_expired_approval_after_reopen(self) -> None:
        """Expired approval stays unusable after reopen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "work.db")
            
            clock_value = [1000.0]
            
            def fake_clock() -> float:
                return clock_value[0]
            
            store1 = WorkStore(path=db_path, clock=fake_clock)
            register_enrolled_device(store1, DEVICE)
            
            order = create_work_order(
                store1,
                device_id=DEVICE,
                action="repair.service.restart",
                target="Spooler",
                operator_id=OPERATOR,
                params={"start_type": "automatic", "status": "stopped"},
            )
            order_id = order["id"]
            
            approve_work_order(store1, order_id, APPROVER)
            
            clock_value[0] = 1000.0 + APPROVAL_TTL_SECONDS + 1
            
            store2 = WorkStore(path=db_path, clock=fake_clock)
            
            with self.assertRaisesRegex(WorkRefused, "approval expired"):
                claim_job(store2, DEVICE, order_id)

    def test_claimed_order_becomes_interrupted_after_reopen(self) -> None:
        """Claimed order becomes failed after reopen and is not re-offered by poll."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "work.db")
            
            store1 = WorkStore(path=db_path)
            register_enrolled_device(store1, DEVICE)
            
            order = create_work_order(
                store1,
                device_id=DEVICE,
                action="repair.service.restart",
                target="Spooler",
                operator_id=OPERATOR,
                params={"start_type": "automatic", "status": "stopped"},
            )
            order_id = order["id"]
            
            approve_work_order(store1, order_id, APPROVER)
            claim_job(store1, DEVICE, order_id)
            
            self.assertEqual(store1.orders[order_id]["state"], "claimed")
            
            store2 = WorkStore(path=db_path)
            
            reopened = store2.orders[order_id]
            self.assertEqual(reopened["state"], "failed")
            self.assertEqual(reopened["error"], "order was interrupted by restart")
            
            found_audit = [
                entry for entry in store2.audit
                if entry["state"] == "failed" and "interrupted" in (entry.get("error") or "")
            ]
            self.assertEqual(len(found_audit), 1)
            
            available = [job for job in store2.orders.values() if job["state"] == "approved"]
            self.assertEqual(len(available), 0)

    def test_self_approval_refused_after_reopen(self) -> None:
        """Self-approval still refused after reopen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "work.db")
            
            store1 = WorkStore(path=db_path)
            register_enrolled_device(store1, DEVICE)
            
            order = create_work_order(
                store1,
                device_id=DEVICE,
                action="repair.service.restart",
                target="Spooler",
                operator_id=OPERATOR,
                params={"start_type": "automatic", "status": "stopped"},
            )
            order_id = order["id"]
            
            self.assertEqual(store1.orders[order_id]["state"], "pending_approval")
            
            store2 = WorkStore(path=db_path)
            
            self.assertEqual(store2.orders[order_id]["state"], "pending_approval")
            
            with self.assertRaisesRegex(WorkRefused, "cannot approve"):
                approve_work_order(store2, order_id, OPERATOR)

    def test_secret_never_on_disk(self) -> None:
        """Secret never written to sqlite file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "work.db")
            
            store = WorkStore(path=db_path)
            register_enrolled_device(store, DEVICE)
            
            secret_password = "SecretPass123!"
            
            order = create_work_order(
                store,
                device_id=DEVICE,
                action="setup.onboard.local_user",
                target="testuser",
                operator_id=OPERATOR,
                params={"password": secret_password},
            )
            
            self.assertEqual(order["state"], "refused")
            self.assertIn("secret", order["error"])
            
            with open(db_path, "rb") as f:
                db_bytes = f.read()
            
            self.assertNotIn(secret_password.encode("utf-8"), db_bytes)

    def test_concurrent_writers(self) -> None:
        """Concurrent writers from threads don't corrupt the store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "work.db")
            
            store = WorkStore(path=db_path)
            register_enrolled_device(store, DEVICE)
            
            errors = []
            order_ids = []
            lock = threading.Lock()
            
            def create_orders(device_id: str, thread_id: int, count: int) -> None:
                try:
                    for i in range(count):
                        order = create_work_order(
                            store,
                            device_id=device_id,
                            action="repair.service.restart",
                            target=f"Service{thread_id}_{i}",
                            operator_id=f"operator{thread_id}_{i}",
                            params={"start_type": "automatic", "status": "stopped"},
                        )
                        with lock:
                            order_ids.append(order["id"])
                except Exception as e:
                    with lock:
                        errors.append(str(e))
            
            threads = [
                threading.Thread(target=create_orders, args=(DEVICE, idx, 10))
                for idx in range(5)
            ]
            
            for t in threads:
                t.start()
            
            for t in threads:
                t.join()
            
            if errors:
                self.fail(f"Concurrent writes failed with errors: {errors}")
            
            store2 = WorkStore(path=db_path)
            
            self.assertEqual(len(store2.orders), 50)
            self.assertTrue(all(order["state"] in {"pending_approval", "refused"} for order in store2.orders.values()))

    def test_heartbeat_cap_per_device(self) -> None:
        """Heartbeats capped at 1000 per device."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "work.db")
            
            store = WorkStore(path=db_path)
            register_enrolled_device(store, DEVICE)
            register_enrolled_device(store, OTHER)
            
            for i in range(1100):
                post_heartbeat(
                    store,
                    {
                        "device_id": DEVICE,
                        "utc": f"2026-10-23T{i % 24:02d}:00:00Z",
                        "worker_version": "1.0.0",
                    },
                )
            
            for i in range(500):
                post_heartbeat(
                    store,
                    {
                        "device_id": OTHER,
                        "utc": f"2026-10-23T{i % 24:02d}:00:00Z",
                        "worker_version": "1.0.0",
                    },
                )
            
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM heartbeats WHERE device_id = ?", (DEVICE,))
            device_count = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM heartbeats WHERE device_id = ?", (OTHER,))
            other_count = cursor.fetchone()[0]
            conn.close()
            
            self.assertEqual(device_count, 1000)
            self.assertEqual(other_count, 500)

    def test_in_memory_default_unchanged(self) -> None:
        """In-memory default unchanged (no path argument)."""
        store = WorkStore()
        
        self.assertIsNone(store._path)
        
        register_enrolled_device(store, DEVICE)
        
        order = create_work_order(
            store,
            device_id=DEVICE,
            action="repair.service.restart",
            target="Spooler",
            operator_id=OPERATOR,
            params={"start_type": "automatic", "status": "stopped"},
        )
        
        self.assertIsNotNone(order)
        self.assertEqual(order["device_id"], DEVICE)
        self.assertTrue(DEVICE in store.enrolled)

    def test_file_permissions_0600(self) -> None:
        """Database file created with 0600 permissions where supported."""
        if not hasattr(os, "chmod"):
            self.skipTest("chmod not available on this platform")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "work.db")
            
            store = WorkStore(path=db_path)
            register_enrolled_device(store, DEVICE)
            
            file_stat = os.stat(db_path)
            mode = file_stat.st_mode & 0o777
            
            self.assertEqual(mode, 0o600)

    def test_audit_append_only_after_reopen(self) -> None:
        """Audit stays append-only after reopen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "work.db")
            
            store1 = WorkStore(path=db_path)
            register_enrolled_device(store1, DEVICE)
            
            order = create_work_order(
                store1,
                device_id=DEVICE,
                action="repair.service.restart",
                target="Spooler",
                operator_id=OPERATOR,
                params={"start_type": "automatic", "status": "stopped"},
            )
            order_id = order["id"]
            
            approve_work_order(store1, order_id, APPROVER)
            
            audit_entries_before = store1.audit.copy()
            initial_count = len(audit_entries_before)
            
            store2 = WorkStore(path=db_path)
            
            self.assertEqual(len(store2.audit), initial_count)
            for i, entry in enumerate(audit_entries_before):
                self.assertEqual(store2.audit[i], entry)
            
            claim_job(store2, DEVICE, order_id)
            
            self.assertEqual(len(store2.audit), initial_count + 1)
            for i, entry in enumerate(audit_entries_before):
                self.assertEqual(store2.audit[i], entry)


if __name__ == "__main__":
    unittest.main()
