"""Console reload decisions. These tests do not open a socket or signal a process."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ops.release.console_deploy import DeployRefusal, assess_replacement, decide, main, operators_provisioned

_RELEASE = Path(__file__).resolve().parent / "release"


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

    def test_release_scripts_default_to_main(self) -> None:
        for name in ("START.sh", "deploy-console-only.sh", "snapshot-published-tip.sh"):
            text = (_RELEASE / name).read_text(encoding="utf-8")
            self.assertIn('BRANCH="${PLATFORM_BRANCH:-main}"', text, name)
            self.assertNotIn("feature/qwen3.5-27b-integration", text, name)

    def test_unconfigured_operators_do_not_replace_a_healthy_console(self) -> None:
        with self.assertRaises(DeployRefusal) as caught:
            decide(
                approved=True, health_8002=200, health_8010=200,
                pid_8002="11", pid_8010="22", pid_8080="33",
                operators_ready=False,
            )
        self.assertIn("was not replaced", str(caught.exception))
        self.assertEqual(decide(
            approved=False, health_8002=200, health_8010=200,
            pid_8002="11", pid_8010="22", pid_8080="33",
            operators_ready=False,
        ), "dry-run")

    def test_replacement_health_uses_fixtures_only(self) -> None:
        self.assertEqual(assess_replacement(qwen_health=200, gateway_health=200, console_health=200), "keep")
        self.assertEqual(assess_replacement(qwen_health=200, gateway_health=200, console_health=503), "rollback")
        self.assertEqual(assess_replacement(qwen_health=0, gateway_health=200, console_health=200), "rollback")
        self.assertEqual(assess_replacement(qwen_health=200, gateway_health=0, console_health=200), "rollback")

    def test_shell_checks_operators_before_it_stops_the_console(self) -> None:
        text = (_RELEASE / "deploy-console-only.sh").read_text(encoding="utf-8")
        operators = text.index("--operators-file")
        kill = text.index('kill "$P8080"')
        assess = text.index("--assess")
        self.assertLess(operators, kill)
        self.assertLess(kill, assess)
        self.assertNotIn('if [[ -f "$OPERATOR_AUTH_DIR/operators.json" ]]', text)

    def test_empty_or_disabled_operator_file_is_not_provisioned(self) -> None:
        secret = "hash-must-not-print"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operators.json"
            self.assertFalse(operators_provisioned(path))
            path.write_text("{", encoding="utf-8")
            self.assertFalse(operators_provisioned(path))
            path.write_text(json.dumps({"operators": []}), encoding="utf-8")
            self.assertFalse(operators_provisioned(path))
            path.write_text(json.dumps({"operators": [{
                "operator_id": "a", "username": "ada", "password_hash": secret, "disabled": True,
            }]}), encoding="utf-8")
            self.assertFalse(operators_provisioned(path))
            path.write_text(json.dumps({"operators": [{
                "operator_id": "a", "username": "ada", "password_hash": secret, "disabled": False,
            }]}), encoding="utf-8")
            self.assertTrue(operators_provisioned(path))
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--operators-file", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue().strip(), "yes")
            self.assertNotIn(secret, output.getvalue())

    def test_missing_console_pid_does_not_become_a_restart(self) -> None:
        with self.assertRaises(DeployRefusal):
            decide(
                approved=True, health_8002=200, health_8010=200,
                pid_8002="11", pid_8010="22", pid_8080="",
            )


if __name__ == "__main__":
    unittest.main()
