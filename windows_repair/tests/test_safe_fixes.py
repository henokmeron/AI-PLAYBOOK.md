"""Approval-gated safe fixes. Executors are fakes. No service or file is touched."""
from __future__ import annotations

import unittest
from pathlib import Path

from windows_repair.approval import (
    CLEAR_PRINTER_QUEUE,
    FORBIDDEN_ACTION_IDS,
    RESTART_FAILED_SERVICE,
    Approval,
    evaluate_approval,
    is_forbidden_action,
    issue_approval,
)
from windows_repair.safe_fixes import (
    LIVE_REPAIR_ENABLED,
    clear_stuck_printer_queue,
    restart_failed_automatic_service,
    run_safe_fix,
)

_NOW = 1_000.0
_LATER = 2_000.0
_DEVICE = "device-1"
_SERVICE = "wuauserv"
_QUEUE = "HP Laser"
_SPL = r"C:\Windows\System32\spool\PRINTERS\00002.SPL"
_SHD = r"C:\Windows\System32\spool\PRINTERS\00002.SHD"


class FakeExecutors:
    def __init__(self) -> None:
        self.restarts: list[str] = []
        self.deletes: list[tuple[str, tuple[str, ...]]] = []

    def restart(self, service_name: str) -> dict[str, bool]:
        self.restarts.append(service_name)
        return {"ok": True}

    def delete(self, queue_name: str, paths: tuple[str, ...]) -> dict[str, bool]:
        self.deletes.append((queue_name, paths))
        return {"ok": True}


def _approval(action_id: str, target: str, *, device_id: str = _DEVICE, expires_at: float = _LATER) -> Approval:
    return issue_approval(device_id=device_id, action_id=action_id, target=target, expires_at=expires_at)


def _failed_automatic(name: str = _SERVICE, **overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "name": name,
        "status": "Stopped",
        "start_type": "Automatic",
        "failed": True,
    }
    state.update(overrides)
    return state


def _stuck_queue(name: str = _QUEUE, **overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "queue": name,
        "stuck": True,
        "spool_files": (
            {"path": _SPL, "queue": name},
            {"path": _SHD, "queue": name},
        ),
    }
    state.update(overrides)
    return state


class ApprovalGateTests(unittest.TestCase):
    def test_missing_approval_is_refused(self) -> None:
        decision = evaluate_approval(
            None,
            device_id=_DEVICE,
            action_id=RESTART_FAILED_SERVICE,
            target=_SERVICE,
            now=_NOW,
        )
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["status"], "refused")
        self.assertEqual(decision["reason"], "approval_missing")

    def test_diagnostic_result_is_not_an_approval(self) -> None:
        diagnostic = {
            "device_id": _DEVICE,
            "action_id": RESTART_FAILED_SERVICE,
            "target": _SERVICE,
            "expires_at": _LATER,
            "status": "failed",
            "proposed_procedure": RESTART_FAILED_SERVICE,
            "ok": False,
        }
        decision = evaluate_approval(
            diagnostic,
            device_id=_DEVICE,
            action_id=RESTART_FAILED_SERVICE,
            target=_SERVICE,
            now=_NOW,
        )
        self.assertEqual(decision["reason"], "not_an_approval")
        self.assertFalse(decision["allowed"])

    def test_expired_approval_is_refused(self) -> None:
        approval = _approval(RESTART_FAILED_SERVICE, _SERVICE, expires_at=_NOW)
        decision = evaluate_approval(
            approval,
            device_id=_DEVICE,
            action_id=RESTART_FAILED_SERVICE,
            target=_SERVICE,
            now=_NOW,
        )
        self.assertEqual(decision["reason"], "approval_expired")

    def test_different_device_action_and_target_are_refused(self) -> None:
        approval = _approval(RESTART_FAILED_SERVICE, _SERVICE)
        other_device = evaluate_approval(
            approval,
            device_id="device-2",
            action_id=RESTART_FAILED_SERVICE,
            target=_SERVICE,
            now=_NOW,
        )
        other_action = evaluate_approval(
            approval,
            device_id=_DEVICE,
            action_id=CLEAR_PRINTER_QUEUE,
            target=_SERVICE,
            now=_NOW,
        )
        other_target = evaluate_approval(
            approval,
            device_id=_DEVICE,
            action_id=RESTART_FAILED_SERVICE,
            target="Spooler",
            now=_NOW,
        )
        self.assertEqual(other_device["reason"], "approval_device_mismatch")
        self.assertEqual(other_action["reason"], "approval_action_mismatch")
        self.assertEqual(other_target["reason"], "approval_target_mismatch")

    def test_blanket_names_are_refused(self) -> None:
        for device_id, action_id, target in (
            ("*", RESTART_FAILED_SERVICE, _SERVICE),
            (_DEVICE, "*", _SERVICE),
            (_DEVICE, RESTART_FAILED_SERVICE, "*"),
            ("all", RESTART_FAILED_SERVICE, "all services"),
            (_DEVICE, RESTART_FAILED_SERVICE, "wuauserv, Spooler"),
        ):
            approval = Approval(device_id, action_id, target, _LATER)
            with self.subTest(target=target, action_id=action_id, device_id=device_id):
                decision = evaluate_approval(
                    approval,
                    device_id=device_id,
                    action_id=action_id,
                    target=target,
                    now=_NOW,
                )
                self.assertEqual(decision["reason"], "blanket_approval")

    def test_forbidden_actions_stay_refused_with_matching_approval(self) -> None:
        self.assertFalse(LIVE_REPAIR_ENABLED)
        for action_id in FORBIDDEN_ACTION_IDS:
            approval = Approval(_DEVICE, action_id, _SERVICE, _LATER)
            with self.subTest(action_id=action_id):
                self.assertTrue(is_forbidden_action(action_id))
                decision = evaluate_approval(
                    approval,
                    device_id=_DEVICE,
                    action_id=action_id,
                    target=_SERVICE,
                    now=_NOW,
                )
                self.assertEqual(decision["status"], "refused")
                self.assertEqual(decision["reason"], "action_forbidden")

    def test_matching_approval_is_specific(self) -> None:
        approval = _approval(CLEAR_PRINTER_QUEUE, _QUEUE)
        decision = evaluate_approval(
            approval,
            device_id=_DEVICE,
            action_id=CLEAR_PRINTER_QUEUE,
            target=_QUEUE,
            now=_NOW,
        )
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["device_id"], _DEVICE)
        self.assertEqual(decision["action_id"], CLEAR_PRINTER_QUEUE)
        self.assertEqual(decision["target"], _QUEUE)


class RestartServiceTests(unittest.TestCase):
    def test_restart_refused_without_matching_approval(self) -> None:
        fakes = FakeExecutors()
        cases = (
            None,
            _approval(RESTART_FAILED_SERVICE, _SERVICE, expires_at=_NOW),
            _approval(RESTART_FAILED_SERVICE, _SERVICE, device_id="device-2"),
            _approval(CLEAR_PRINTER_QUEUE, _SERVICE),
            _approval(RESTART_FAILED_SERVICE, "Spooler"),
            {
                "device_id": _DEVICE,
                "action_id": RESTART_FAILED_SERVICE,
                "target": _SERVICE,
                "service": _SERVICE,
                "status": "Stopped",
            },
        )
        for approval in cases:
            with self.subTest(approval=approval):
                result = restart_failed_automatic_service(
                    device_id=_DEVICE,
                    service_name=_SERVICE,
                    approval=approval,
                    now=_NOW,
                    service_state=_failed_automatic(),
                    restarter=fakes.restart,
                )
                self.assertEqual(result["status"], "refused")
                self.assertFalse(result["executed"])
                self.assertFalse(result["changed_device"])
                self.assertEqual(result["services_touched"], [])
        self.assertEqual(fakes.restarts, [])

    def test_restart_fake_success_with_matching_approval(self) -> None:
        fakes = FakeExecutors()
        result = restart_failed_automatic_service(
            device_id=_DEVICE,
            service_name=_SERVICE,
            approval=_approval(RESTART_FAILED_SERVICE, _SERVICE),
            now=_NOW,
            service_state=_failed_automatic(),
            restarter=fakes.restart,
        )
        self.assertEqual(result["status"], "restarted")
        self.assertTrue(result["executed"])
        self.assertTrue(result["fake"])
        self.assertFalse(result["live"])
        self.assertFalse(result["changed_device"])
        self.assertFalse(result["problem_resolved"])
        self.assertFalse(result["rebooted"])
        self.assertEqual(result["services_touched"], [_SERVICE])
        self.assertEqual(fakes.restarts, [_SERVICE])

    def test_delayed_automatic_failure_uses_the_same_single_target(self) -> None:
        fakes = FakeExecutors()
        state = _failed_automatic(start_type="Automatic (Delayed Start)")
        result = restart_failed_automatic_service(
            device_id=_DEVICE,
            service_name=_SERVICE,
            approval=_approval(RESTART_FAILED_SERVICE, _SERVICE),
            now=_NOW,
            service_state=state,
            restarter=fakes.restart,
        )
        self.assertEqual(result["status"], "restarted")
        self.assertEqual(fakes.restarts, [_SERVICE])

    def test_running_service_is_not_stopped(self) -> None:
        fakes = FakeExecutors()
        result = restart_failed_automatic_service(
            device_id=_DEVICE,
            service_name=_SERVICE,
            approval=_approval(RESTART_FAILED_SERVICE, _SERVICE),
            now=_NOW,
            service_state=_failed_automatic(status="Running"),
            restarter=fakes.restart,
        )
        self.assertEqual(result["reason"], "service_running")
        self.assertEqual(fakes.restarts, [])

    def test_manual_and_healthy_services_are_not_restarted(self) -> None:
        fakes = FakeExecutors()
        manual = restart_failed_automatic_service(
            device_id=_DEVICE,
            service_name=_SERVICE,
            approval=_approval(RESTART_FAILED_SERVICE, _SERVICE),
            now=_NOW,
            service_state=_failed_automatic(start_type="Manual"),
            restarter=fakes.restart,
        )
        healthy = restart_failed_automatic_service(
            device_id=_DEVICE,
            service_name=_SERVICE,
            approval=_approval(RESTART_FAILED_SERVICE, _SERVICE),
            now=_NOW,
            service_state=_failed_automatic(failed=False),
            restarter=fakes.restart,
        )
        self.assertEqual(manual["reason"], "not_automatic")
        self.assertEqual(healthy["reason"], "not_failed")
        self.assertEqual(fakes.restarts, [])

    def test_a_list_of_services_is_not_restarted(self) -> None:
        fakes = FakeExecutors()
        result = restart_failed_automatic_service(
            device_id=_DEVICE,
            service_name=_SERVICE,
            approval=_approval(RESTART_FAILED_SERVICE, _SERVICE),
            now=_NOW,
            service_state={"services": [_failed_automatic(), _failed_automatic("Spooler")]},
            restarter=fakes.restart,
        )
        self.assertEqual(result["reason"], "multiple_services")
        self.assertEqual(fakes.restarts, [])

    def test_reboot_flag_does_not_restart_the_service_or_the_computer(self) -> None:
        fakes = FakeExecutors()
        result = restart_failed_automatic_service(
            device_id=_DEVICE,
            service_name=_SERVICE,
            approval=_approval(RESTART_FAILED_SERVICE, _SERVICE),
            now=_NOW,
            service_state=_failed_automatic(reboot=True),
            restarter=fakes.restart,
        )
        self.assertEqual(result["reason"], "reboot_refused")
        self.assertFalse(result["rebooted"])
        self.assertEqual(result["services_touched"], [])
        self.assertEqual(fakes.restarts, [])

    def test_matching_approval_without_a_fake_does_not_run_live(self) -> None:
        result = restart_failed_automatic_service(
            device_id=_DEVICE,
            service_name=_SERVICE,
            approval=_approval(RESTART_FAILED_SERVICE, _SERVICE),
            now=_NOW,
            service_state=_failed_automatic(),
        )
        self.assertEqual(result["reason"], "live_execution_disabled")
        self.assertFalse(result["executed"])
        self.assertFalse(result["rebooted"])


class ClearQueueTests(unittest.TestCase):
    def test_clear_queue_refused_without_matching_approval(self) -> None:
        fakes = FakeExecutors()
        cases = (
            None,
            _approval(CLEAR_PRINTER_QUEUE, _QUEUE, expires_at=999.0),
            _approval(CLEAR_PRINTER_QUEUE, _QUEUE, device_id="other-device"),
            _approval(RESTART_FAILED_SERVICE, _QUEUE),
            _approval(CLEAR_PRINTER_QUEUE, "Front Desk"),
        )
        for approval in cases:
            with self.subTest(approval=approval):
                result = clear_stuck_printer_queue(
                    device_id=_DEVICE,
                    queue_name=_QUEUE,
                    approval=approval,
                    now=_NOW,
                    queue_state=_stuck_queue(),
                    deleter=fakes.delete,
                )
                self.assertEqual(result["status"], "refused")
                self.assertEqual(result["files_touched"], [])
        self.assertEqual(fakes.deletes, [])

    def test_clear_queue_fake_success_with_matching_approval(self) -> None:
        fakes = FakeExecutors()
        result = clear_stuck_printer_queue(
            device_id=_DEVICE,
            queue_name=_QUEUE,
            approval=_approval(CLEAR_PRINTER_QUEUE, _QUEUE),
            now=_NOW,
            queue_state=_stuck_queue(),
            deleter=fakes.delete,
        )
        self.assertEqual(result["status"], "cleared")
        self.assertTrue(result["executed"])
        self.assertTrue(result["fake"])
        self.assertFalse(result["changed_device"])
        self.assertFalse(result["problem_resolved"])
        self.assertEqual(result["files_touched"], [_SPL, _SHD])
        self.assertEqual(fakes.deletes, [(_QUEUE, (_SPL, _SHD))])
        self.assertEqual(fakes.restarts, [])

    def test_other_queues_user_documents_and_spool_directory_are_kept(self) -> None:
        fakes = FakeExecutors()
        other_queue = _stuck_queue(spool_files=(
            {"path": _SPL, "queue": _QUEUE},
            {"path": r"C:\Windows\System32\spool\PRINTERS\00009.SPL", "queue": "Front Desk"},
        ))
        documents = _stuck_queue(spool_files=(
            {"path": r"C:\Users\Alex\Documents\report.docx", "queue": _QUEUE},
        ))
        spool_dir = _stuck_queue(spool_files=(
            {"path": r"C:\Windows\System32\spool\PRINTERS", "queue": _QUEUE},
            {"path": r"C:\Windows\System32\spool", "queue": _QUEUE},
        ))
        outside = _stuck_queue(spool_files=(
            {"path": r"C:\Windows\Temp\00002.SPL", "queue": _QUEUE},
        ))
        expectations = (
            (other_queue, "other_queue"),
            (documents, "file_outside_queue"),
            (spool_dir, "file_outside_queue"),
            (outside, "file_outside_queue"),
        )
        for state, reason in expectations:
            with self.subTest(reason=reason):
                result = clear_stuck_printer_queue(
                    device_id=_DEVICE,
                    queue_name=_QUEUE,
                    approval=_approval(CLEAR_PRINTER_QUEUE, _QUEUE),
                    now=_NOW,
                    queue_state=state,
                    deleter=fakes.delete,
                )
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["files_touched"], [])
        self.assertEqual(fakes.deletes, [])

    def test_idle_queue_is_not_cleared(self) -> None:
        fakes = FakeExecutors()
        result = clear_stuck_printer_queue(
            device_id=_DEVICE,
            queue_name=_QUEUE,
            approval=_approval(CLEAR_PRINTER_QUEUE, _QUEUE),
            now=_NOW,
            queue_state=_stuck_queue(stuck=False),
            deleter=fakes.delete,
        )
        self.assertEqual(result["reason"], "queue_not_stuck")
        self.assertEqual(fakes.deletes, [])

    def test_matching_approval_without_a_fake_deletes_nothing(self) -> None:
        result = clear_stuck_printer_queue(
            device_id=_DEVICE,
            queue_name=_QUEUE,
            approval=_approval(CLEAR_PRINTER_QUEUE, _QUEUE),
            now=_NOW,
            queue_state=_stuck_queue(),
        )
        self.assertEqual(result["reason"], "live_execution_disabled")
        self.assertEqual(result["files_touched"], [])


class ForbiddenDispatchTests(unittest.TestCase):
    def test_out_of_scope_actions_do_not_call_fakes(self) -> None:
        fakes = FakeExecutors()
        action_ids = (
            "reboot",
            "format",
            "registry.wipe",
            "firewall.change",
            "net.firewall.disable",
            "uninstall",
            "driver.download",
            "hw.driver.install",
            "file.delete",
            "microsoft365",
            "signin",
            "microsoft.signin",
            "mail",
            "mail.send",
            "tokens",
        )
        for action_id in action_ids:
            with self.subTest(action_id=action_id):
                result = run_safe_fix(
                    action_id,
                    device_id=_DEVICE,
                    target=_SERVICE,
                    approval=Approval(_DEVICE, action_id, _SERVICE, _LATER),
                    now=_NOW,
                    service_state=_failed_automatic(),
                    queue_state=_stuck_queue(),
                    restarter=fakes.restart,
                    deleter=fakes.delete,
                )
                self.assertEqual(result["status"], "refused")
                self.assertEqual(result["reason"], "action_forbidden")
                self.assertFalse(result["executed"])
        self.assertEqual(fakes.restarts, [])
        self.assertEqual(fakes.deletes, [])

    def test_modules_do_not_import_repair_runners_or_live_commands(self) -> None:
        root = Path(__file__).resolve().parents[1]
        combined = "\n".join(
            (root / name).read_text(encoding="utf-8")
            for name in ("approval.py", "safe_fixes.py")
        )
        lowered = combined.casefold()
        for banned in (
            "subprocess",
            "os.remove",
            "shutil",
            "restart-service",
            "remove-item",
            "ctypes",
            "win32",
            "paramiko",
            "ssh",
        ):
            self.assertNotIn(banned, lowered)
        for owned_elsewhere in (
            "hardware_inventory",
            "health_checks",
            "driver_health",
            "endpoint_worker",
            "acceptance_board",
        ):
            self.assertNotIn(owned_elsewhere, lowered)


if __name__ == "__main__":
    unittest.main()
