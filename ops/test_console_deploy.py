"""Console reload decisions. These tests do not open a socket or signal a process."""
from __future__ import annotations

import unittest

from ops.release.console_deploy import DeployRefusal, decide


class ConsoleDeployTests(unittest.TestCase):
    def test_healthy_stack_without_approval_is_a_dry_run(self) -> None:
        self.assertEqual(decide(
            approved=False, health_8002=200, health_8010=200,
            pid_8002="11", pid_8010="22", pid_8080="33",
        ), "dry-run")

    def test_down_qwen_is_refused_even_with_approval(self) -> None:
        with self.assertRaises(DeployRefusal) as caught:
            decide(approved=True, health_8002=0, health_8010=200, pid_8002="11", pid_8010="22", pid_8080="33")
        self.assertIn("will not start them", str(caught.exception))

    def test_approval_cannot_stop_qwen_or_the_gateway_pid(self) -> None:
        with self.assertRaises(DeployRefusal):
            decide(
                approved=True, health_8002=200, health_8010=200,
                pid_8002="11", pid_8010="22", pid_8080="11",
            )
        self.assertEqual(decide(
            approved=True, health_8002=200, health_8010=200,
            pid_8002="11", pid_8010="22", pid_8080="33",
        ), "restart-console")

    def test_missing_console_pid_does_not_become_a_restart(self) -> None:
        with self.assertRaises(DeployRefusal):
            decide(
                approved=True, health_8002=200, health_8010=200,
                pid_8002="11", pid_8010="22", pid_8080="",
            )


if __name__ == "__main__":
    unittest.main()
