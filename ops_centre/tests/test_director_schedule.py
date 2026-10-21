"""Director schedule tests. No GPU, no network, no Pod."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops_centre.director_schedule import DirectorSchedule, DirectorScheduleError
from ops_centre.service import OpsCentre, OpsCentreConfig


class DirectorScheduleTests(unittest.TestCase):
    def test_due_run_records_audit_and_survives_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 1_000.0}
            path = Path(tmp) / "schedule.json"
            centre = OpsCentre(OpsCentreConfig(data_dir=Path(tmp) / "ops"))
            schedule = DirectorSchedule(
                path,
                clock=lambda: clock["now"],
                builder=lambda _centre: {"overall": "DEGRADED", "kind": "director_report"},
            )
            schedule.configure(enabled=True, interval_seconds=300)
            self.assertFalse(schedule.status()["due"])
            clock["now"] = 2_000.0
            report = schedule.run_due(centre)
            self.assertEqual(report["overall"], "DEGRADED")
            self.assertEqual(schedule.status()["last_outcome"], "degraded")
            self.assertEqual(schedule.status()["missed_runs"], 2)
            events = [row for row in centre.events.list(limit=20) if row.event_type == "director.schedule.run"]
            self.assertEqual(len(events), 1)
            reloaded = DirectorSchedule(path, clock=lambda: clock["now"])
            self.assertTrue(reloaded.enabled)
            self.assertEqual(reloaded.missed_runs, 2)
            self.assertFalse(reloaded.status()["due"])

    def test_failed_run_advances_and_is_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"now": 2_000.0}
            path = Path(tmp) / "schedule.json"
            centre = OpsCentre(OpsCentreConfig(data_dir=Path(tmp) / "ops"))

            def boom(_centre):
                raise RuntimeError("probe failed")

            schedule = DirectorSchedule(path, clock=lambda: clock["now"], builder=boom)
            schedule.configure(enabled=True, interval_seconds=300)
            clock["now"] = 2_400.0
            with self.assertRaises(RuntimeError):
                schedule.run_due(centre)
            self.assertEqual(schedule.status()["last_outcome"], "failed")
            self.assertEqual(schedule.status()["last_error"], "RuntimeError")
            self.assertGreaterEqual(schedule.status()["next_due_at"], 2_700.0)
            failed = [row for row in centre.events.list(limit=20) if row.event_type == "director.schedule.failed"]
            self.assertEqual(len(failed), 1)

    def test_interval_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            schedule = DirectorSchedule(Path(tmp) / "schedule.json")
            with self.assertRaises(DirectorScheduleError):
                schedule.configure(enabled=True, interval_seconds=60)


if __name__ == "__main__":
    unittest.main()
