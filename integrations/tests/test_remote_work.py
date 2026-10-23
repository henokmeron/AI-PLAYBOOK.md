"""State machine, handler refusals, and the offline worker for remote IT work."""
from __future__ import annotations

import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from integrations import remote_work, remote_worker
from integrations.remote_work import (
    APPROVAL_TTL_SECONDS,
    CONSOLE_FUNCTIONS,
    WorkRefused,
    WorkStore,
    approve_work_order,
    claim_job,
    complete_job,
    create_work_order,
    default_runner_invocations,
    execute_work_order,
    poll_jobs,
    post_heartbeat,
    register_enrolled_device,
    service_facts_from_text,
    snapshot,
)
from integrations.remote_worker import WORKER_VERSION, main, poll_once

DEVICE = "a" * 32
OTHER = "b" * 32
OPERATOR = "it.operator"
PIN = "0123456789abcdef" * 4
SENTINEL = "SENTINEL-PASSWORD-do-not-log-9f3a"
STAGING = r"C:\ProgramData\RemoteIT\staging"
DEST = r"C:\ProgramData\RemoteIT\staging\package.cab"
DELETE_OK = r"C:\Users\alice\AppData\Local\Temp\old.tmp"
UTC = "2026-10-23T23:00:00Z"


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, request: dict) -> dict:
        self.calls.append(request)
        return {"ok": True}


class Clock:
    def __init__(self) -> None:
        self.moment = 1_700_000_000.0

    def __call__(self) -> float:
        return self.moment


class RemoteWorkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.store = WorkStore(clock=self.clock)
        register_enrolled_device(self.store, DEVICE)
        register_enrolled_device(self.store, OTHER)

    def _service(self, device_id: str = DEVICE, target: str = "Spooler", params: dict | None = None) -> dict:
        body = {"start_type": "automatic", "status": "stopped"} if params is None else params
        return create_work_order(
            self.store, device_id=device_id, action="repair.service.restart",
            target=target, operator_id=OPERATOR, params=body,
        )

    def _approve(self, order: dict) -> dict:
        return approve_work_order(self.store, order["id"], "approver")

    def _printer(self, target: str = "HP-Lab", path: str | None = None) -> dict:
        params: dict = {} if path is None else {"path": path}
        return create_work_order(
            self.store, device_id=DEVICE, action="repair.printer.clear_queue",
            target=target, operator_id=OPERATOR, params=params,
        )

    def _offboard(self, target: str = "alice", params: dict | None = None) -> dict:
        body = {"mode": "disable", "admin_count": 2} if params is None else params
        return create_work_order(
            self.store, device_id=DEVICE, action="setup.offboard.local_user",
            target=target, operator_id=OPERATOR, params=body,
        )

    def _download(
        self,
        url: str = "https://updates.example.com/a.cab",
        pin: str = PIN,
        destination: str = DEST,
    ) -> dict:
        return create_work_order(
            self.store, device_id=DEVICE, action="change.download",
            target=url, operator_id=OPERATOR,
            params={
                "allowlist": ["updates.example.com"],
                "staging_directory": STAGING,
                "destination": destination,
                "sha256": pin,
            },
        )

    def _install(self, source: str = "pnputil", destination_as_target: str | None = None) -> dict:
        return create_work_order(
            self.store, device_id=DEVICE, action="change.install",
            target=DEST if destination_as_target is None else destination_as_target,
            operator_id=OPERATOR,
            params={"source": source, "sha256": PIN, "staging_directory": STAGING},
        )

    def test_console_functions_are_the_unwired_http_contract(self) -> None:
        for name in CONSOLE_FUNCTIONS:
            self.assertTrue(callable(getattr(remote_work, name)))
        server = Path(remote_work.__file__).resolve().parents[1] / "web" / "server.py"
        text = server.read_text(encoding="utf-8")
        self.assertNotIn("remote_work", text)
        self.assertNotIn("/api/remote-work", text)
        self.assertEqual(APPROVAL_TTL_SECONDS, 15 * 60)

    def test_creating_an_order_does_not_approve_it(self) -> None:
        order = self._service()
        self.assertEqual(order["state"], "pending_approval")
        self.assertIsNone(order["approval"])
        self.assertEqual(poll_jobs(self.store, DEVICE), [])
        states = [entry["state"] for entry in self.store.audit]
        self.assertEqual(states, ["draft", "pending_approval"])
        self.assertNotIn("approved", states)

    def test_enrolment_alone_does_not_approve_work(self) -> None:
        fresh = WorkStore(clock=self.clock)
        register_enrolled_device(fresh, DEVICE)
        self.assertEqual(fresh.orders, {})
        self.assertEqual(fresh.audit, [])

    def test_a_diagnostic_result_does_not_approve(self) -> None:
        order = self._service()
        with self.assertRaises(WorkRefused) as caught:
            complete_job(
                self.store, DEVICE, order["id"],
                outcome="succeeded",
                result={"diagnostic": True, "ok": True},
            )
        self.assertEqual(caught.exception.message, "job is not claimed")
        stored = self.store.orders[order["id"]]
        self.assertEqual(stored["state"], "pending_approval")
        self.assertIsNone(stored["approval"])

    def test_approval_is_single_use_and_expires(self) -> None:
        order = self._approve(self._service())
        self.clock.moment += APPROVAL_TTL_SECONDS - 1
        claimed = claim_job(self.store, DEVICE, order["id"])
        self.assertEqual(claimed["state"], "claimed")
        self.assertTrue(claimed["approval"]["used"])
        with self.assertRaises(WorkRefused) as caught:
            claim_job(self.store, DEVICE, order["id"])
        self.assertEqual(caught.exception.message, "approval is already used")
        with self.assertRaises(WorkRefused) as again:
            approve_work_order(self.store, order["id"], OPERATOR)
        self.assertEqual(again.exception.message, "only a pending order can be approved")

    def test_approval_expires_at_fifteen_minutes(self) -> None:
        order = self._approve(self._service())
        self.clock.moment += APPROVAL_TTL_SECONDS
        with self.assertRaises(WorkRefused) as caught:
            claim_job(self.store, DEVICE, order["id"])
        self.assertEqual(caught.exception.message, "approval expired")
        self.assertEqual(self.store.orders[order["id"]]["state"], "refused")
        self.assertEqual(poll_jobs(self.store, DEVICE), [])

    def test_approval_is_bound_to_device_action_and_target(self) -> None:
        order = self._approve(self._service())
        self.store.orders[order["id"]]["approval"]["device_id"] = OTHER
        with self.assertRaises(WorkRefused) as device:
            claim_job(self.store, DEVICE, order["id"])
        self.assertEqual(device.exception.message, "approval is bound to a different device")
        self.store.orders[order["id"]]["approval"]["device_id"] = DEVICE
        self.store.orders[order["id"]]["action"] = "change.delete"
        with self.assertRaises(WorkRefused) as action:
            claim_job(self.store, DEVICE, order["id"])
        self.assertEqual(action.exception.message, "approval is bound to a different action")
        self.store.orders[order["id"]]["action"] = "repair.service.restart"
        self.store.orders[order["id"]]["target"] = "wuauserv"
        with self.assertRaises(WorkRefused) as target:
            claim_job(self.store, DEVICE, order["id"])
        self.assertEqual(target.exception.message, "approval is bound to a different target")
        self.store.orders[order["id"]]["target"] = "Spooler"
        self.store.orders[order["id"]]["params"]["status"] = "running"
        with self.assertRaises(WorkRefused) as params:
            claim_job(self.store, DEVICE, order["id"])
        self.assertEqual(params.exception.message, "approval is bound to different parameters")

    def test_poll_returns_only_the_callers_approved_jobs(self) -> None:
        own = self._approve(self._service())
        self._approve(self._service(device_id=OTHER, target="wuauserv"))
        pending = self._service(target="BITS")
        found = poll_jobs(self.store, DEVICE)
        self.assertEqual([item["id"] for item in found], [own["id"]])
        self.assertNotIn(pending["id"], [item["id"] for item in found])
        claim_job(self.store, DEVICE, own["id"])
        self.assertEqual(poll_jobs(self.store, DEVICE), [])

    def test_a_second_complete_call_is_refused(self) -> None:
        order = self._approve(self._service())
        claim_job(self.store, DEVICE, order["id"])
        done = complete_job(self.store, DEVICE, order["id"], outcome="succeeded")
        self.assertEqual(done["state"], "succeeded")
        with self.assertRaises(WorkRefused) as caught:
            complete_job(self.store, DEVICE, order["id"], outcome="failed", error="again")
        self.assertEqual(caught.exception.message, "a second result is refused")
        self.assertEqual(self.store.orders[order["id"]]["state"], "succeeded")
        with self.assertRaises(WorkRefused) as other:
            complete_job(self.store, OTHER, order["id"], outcome="failed")
        self.assertEqual(other.exception.message, "job belongs to another device")

    def test_refused_is_terminal(self) -> None:
        order = self._service(target="reboot")
        self.assertEqual(order["state"], "refused")
        with self.assertRaises(WorkRefused) as caught:
            approve_work_order(self.store, order["id"], OPERATOR)
        self.assertEqual(caught.exception.message, "a refused order is terminal")
        with self.assertRaises(WorkRefused):
            claim_job(self.store, DEVICE, order["id"])
        with self.assertRaises(WorkRefused):
            complete_job(self.store, DEVICE, order["id"], outcome="succeeded")

    def test_unenrolled_device_is_refused(self) -> None:
        stranger = "c" * 32
        with self.assertRaises(WorkRefused) as caught:
            create_work_order(
                self.store, device_id=stranger, action="repair.service.restart",
                target="Spooler", operator_id=OPERATOR,
                params={"start_type": "automatic", "status": "stopped"},
            )
        self.assertEqual(caught.exception.message, "device is not enrolled")
        with self.assertRaises(WorkRefused):
            poll_jobs(self.store, stranger)
        with self.assertRaises(WorkRefused):
            post_heartbeat(self.store, {
                "device_id": stranger, "utc": UTC, "worker_version": WORKER_VERSION,
            })

    def test_heartbeat_needs_no_second_approval_and_rejects_surveillance(self) -> None:
        pending = self._service()
        record = post_heartbeat(self.store, {
            "device_id": DEVICE, "utc": UTC, "worker_version": WORKER_VERSION,
        })
        self.assertEqual(set(record), {"device_id", "utc", "worker_version"})
        self.assertEqual(self.store.orders[pending["id"]]["state"], "pending_approval")
        self.assertEqual(len(self.store.heartbeats), 1)
        for extra in ("screenshot", "keystrokes", "processes", "serial"):
            with self.assertRaises(WorkRefused):
                post_heartbeat(self.store, {
                    "device_id": DEVICE, "utc": UTC, "worker_version": WORKER_VERSION, extra: "no",
                })
        self.assertEqual(len(self.store.heartbeats), 1)

    def test_unknown_and_forbidden_actions_are_refused(self) -> None:
        for action in (
            "remote.desktop", "input.keylog", "persist.startup", "firewall.disable",
            "security.tamper", "credential.dump", "change.spread", "repair.reboot",
        ):
            order = create_work_order(
                self.store, device_id=DEVICE, action=action, target="Spooler",
                operator_id=OPERATOR, params={},
            )
            self.assertEqual(order["state"], "refused", action)
            self.assertEqual(order["error"], "action is not allowlisted")
            self.assertIsNone(order["approval"])

    def test_service_restart_refusals(self) -> None:
        self.assertEqual(self._service(target="reboot")["error"], "reboot and restart-all are refused")
        self.assertEqual(self._service(target="*")["error"], "reboot and restart-all are refused")
        self.assertEqual(self._service(target="restart-all")["error"], "reboot and restart-all are refused")
        self.assertEqual(
            self._service(params={"start_type": "automatic", "status": "stopped", "restart_all": True})["error"],
            "reboot and restart-all are refused",
        )
        self.assertEqual(
            self._service(params={"start_type": "manual", "status": "stopped"})["error"],
            "service must be automatic",
        )
        self.assertEqual(
            self._service(params={"start_type": "automatic", "status": "running"})["error"],
            "service must not be running",
        )
        self.assertEqual(self._service(target="")["error"], "service name is not acceptable")

    def test_service_plan_does_not_run_until_approved_and_live(self) -> None:
        order = self._service()
        runner = RecordingRunner()
        planned = execute_work_order(self.store, order["id"], live=True, runner=runner)
        self.assertFalse(planned["executed"])
        self.assertEqual(planned["argv"], ["sc.exe", "start", "Spooler"])
        self.assertEqual(runner.calls, [])
        self._approve(order)
        held = execute_work_order(self.store, order["id"], live=False, runner=runner)
        self.assertFalse(held["executed"])
        self.assertEqual(runner.calls, [])
        with self.assertRaises(WorkRefused) as caught:
            execute_work_order(self.store, order["id"], live=True, runner=None)
        self.assertEqual(caught.exception.message, "live execution is disabled")
        self.assertEqual(default_runner_invocations(), 0)
        claim_job(self.store, DEVICE, order["id"])
        ran = execute_work_order(self.store, order["id"], live=True, runner=runner)
        self.assertTrue(ran["executed"])
        self.assertEqual(runner.calls[0]["argv"], ["sc.exe", "start", "Spooler"])
        self.assertNotIn("password", runner.calls[0])

    def test_printer_queue_refuses_paths_outside_its_spool(self) -> None:
        outside = (
            r"C:\Windows\System32\config\SAM",
            r"C:\Users\alice\job.spl",
            r"C:\Windows\System32\spool\PRINTERS\Other\job.spl",
            r"C:\Windows\System32\spool\PRINTERS\HP-Lab\notes.txt",
        )
        for path in outside:
            order = self._printer(path=path)
            self.assertEqual(order["state"], "refused", path)
            self.assertEqual(order["error"], "queue path is outside that queue spool")
        self.assertEqual(self._printer(target="all")["error"], "queue name is not acceptable")
        self.assertEqual(self._printer(target="*")["error"], "queue name is not acceptable")
        good = self._printer(path=r"C:\Windows\System32\spool\PRINTERS\HP-Lab\job.spl")
        self.assertEqual(good["state"], "pending_approval")
        named = self._approve(self._printer())
        runner = RecordingRunner()
        plan = execute_work_order(self.store, named["id"], live=False, runner=runner)
        self.assertFalse(plan["executed"])
        self.assertEqual(runner.calls, [])
        claim_job(self.store, DEVICE, named["id"])
        ran = execute_work_order(self.store, named["id"], live=True, runner=runner)
        self.assertTrue(ran["executed"])
        self.assertEqual(runner.calls[0]["queue"], "HP-Lab")
        self.assertNotIn(r"C:\Windows\System32\config", json.dumps(runner.calls))

    def test_onboard_password_never_enters_the_audit_or_the_order(self) -> None:
        refused = create_work_order(
            self.store, device_id=DEVICE, action="setup.onboard.local_user",
            target="alice", operator_id=OPERATOR, params={"password": SENTINEL},
        )
        self.assertEqual(refused["state"], "refused")
        self.assertEqual(refused["error"], "a secret was refused and was not stored")
        self.assertNotIn(SENTINEL, json.dumps(snapshot(self.store)))
        order = self._approve(create_work_order(
            self.store, device_id=DEVICE, action="setup.onboard.local_user",
            target="alice", operator_id=OPERATOR,
        ))
        runner = RecordingRunner()
        claim_job(self.store, DEVICE, order["id"])
        plan = execute_work_order(
            self.store, order["id"], live=True, runner=runner,
            handler_input={"password": SENTINEL},
        )
        self.assertEqual(runner.calls[0]["password"], SENTINEL)
        self.assertNotIn(SENTINEL, json.dumps(plan))
        self.assertEqual(plan["argv"], ["net", "user", "alice", "/add"])
        complete_job(
            self.store, DEVICE, order["id"], outcome="succeeded",
            result={"note": SENTINEL, "password": SENTINEL}, redact=(SENTINEL,),
        )
        dumped = json.dumps(snapshot(self.store))
        self.assertNotIn(SENTINEL, dumped)
        self.assertNotIn("password", dumped)

    def test_offboard_refusals(self) -> None:
        for target in ("", " ", ".."):
            order = self._offboard(target=target)
            self.assertEqual(order["state"], "refused", repr(target))
            self.assertEqual(order["error"], "local user name is blank or not acceptable")
        for count in (0, 1, True, None):
            params = {"mode": "remove"}
            if count is not None:
                params["admin_count"] = count
            order = self._offboard(params=params)
            self.assertEqual(order["error"], "refusing to change the only remaining admin", count)
        kept = self._approve(self._offboard(params={"mode": "disable", "admin_count": 2}))
        runner = RecordingRunner()
        plan = execute_work_order(self.store, kept["id"], live=False, runner=runner)
        self.assertEqual(plan["argv"], ["net", "user", "alice", "/active:no"])
        self.assertEqual(runner.calls, [])
        removed = self._offboard(params={"mode": "remove", "admin_count": 3})
        self.assertEqual(removed["state"], "pending_approval")

    def test_download_refuses_arbitrary_urls_and_does_not_use_the_network(self) -> None:
        self.assertEqual(self._download(url="http://updates.example.com/a.cab")["error"], "download URL must be https")
        self.assertEqual(self._download(url="https://evil.example/a.cab")["error"], "download host is not on the allowlist")
        self.assertEqual(
            self._download(url="https://updates.example.com.evil.com/a.cab")["error"],
            "download host is not on the allowlist",
        )
        self.assertEqual(
            self._download(url="https://user:{}@updates.example.com/a.cab".format(SENTINEL))["error"],
            "a secret was refused and was not stored",
        )
        self.assertNotIn(SENTINEL, json.dumps(snapshot(self.store)))
        missing = self._download(pin="not-a-pin")
        self.assertEqual(missing["error"], "download requires a sha256 pin")
        outside = self._download(destination=r"C:\Windows\System32\package.cab")
        self.assertEqual(outside["error"], "download destination is outside the staging directory")
        escaped = self._download(destination=STAGING + r"\..\Windows\System32\cmd.exe")
        self.assertEqual(escaped["error"], "download destination is outside the staging directory")
        order = self._approve(self._download())
        runner = RecordingRunner()
        with mock.patch("socket.getaddrinfo", side_effect=AssertionError("dns")), \
                mock.patch("socket.socket", side_effect=AssertionError("network")):
            plan = execute_work_order(self.store, order["id"], live=True, runner=runner)
        self.assertFalse(plan["executed"])
        self.assertFalse(plan["network"])
        self.assertEqual(plan["sha256"], PIN)
        self.assertEqual(runner.calls, [])
        source = Path(remote_work.__file__).read_text(encoding="utf-8")
        worker = Path(remote_worker.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urlopen", source + worker)
        self.assertNotIn("getaddrinfo", source + worker)

    def test_install_is_plan_only_and_refuses_other_sources(self) -> None:
        bad = self._install(source="cmd")
        self.assertEqual(bad["error"], "install source is not allowlisted")
        mismatch_order = self._approve(self._install())
        runner = RecordingRunner()
        with self.assertRaises(WorkRefused) as caught:
            execute_work_order(
                self.store, mismatch_order["id"], live=True, runner=runner,
                handler_input={"sha256": "f" * 64},
            )
        self.assertEqual(caught.exception.message, "staged file sha256 does not match the approved pin")
        self.assertEqual(runner.calls, [])
        for source in ("windows-update", "pnputil", "staged-file"):
            order = self._approve(self._install(source=source))
            plan = execute_work_order(
                self.store, order["id"], live=True, runner=runner,
                handler_input={"sha256": PIN},
            )
            self.assertFalse(plan["executed"])
            self.assertFalse(plan["invoke"])
            self.assertEqual(plan["source"], source)
        self.assertEqual(runner.calls, [])
        staged = self._install(destination_as_target=r"C:\Windows\System32\driver.inf")
        self.assertEqual(staged["error"], "staged file is outside the staging directory")

    def test_delete_refusals_and_exact_target(self) -> None:
        cases = {
            "C:\\": "path is a drive root",
            "D:\\": "path is a drive root",
            r"C:\Windows\System32\cmd.exe": "path is under a protected directory",
            r"c:\windows\system32\cmd.exe": "path is under a protected directory",
            r"C:/Windows/System32/cmd.exe": "path is under a protected directory",
            r"C:\Windows\SysWOW64\cmd.exe": "path is under a protected directory",
            r"C:\Program Files\Vendor\app.exe": "path is under a protected directory",
            r"C:\Program Files (x86)\Vendor\app.exe": "path is under a protected directory",
            r"C:\Users\alice": "path is a user profile directory",
            "C:\\Users\\alice\\": "path is a user profile directory",
            r"C:\Users\alice\*.tmp": "path contains a glob",
            r"C:\Users\alice\file?.tmp": "path contains a glob",
            r"\\server\share\a.txt": "path does not match the approved target",
        }
        for path, error in cases.items():
            order = create_work_order(
                self.store, device_id=DEVICE, action="change.delete",
                target=path, operator_id=OPERATOR,
            )
            self.assertEqual(order["state"], "refused", path)
            self.assertEqual(order["error"], error, path)
        order = self._approve(create_work_order(
            self.store, device_id=DEVICE, action="change.delete",
            target=DELETE_OK, operator_id=OPERATOR,
        ))
        self.store.orders[order["id"]]["target"] = r"C:\Users\alice\AppData\Local\Temp\other.tmp"
        runner = RecordingRunner()
        with self.assertRaises(WorkRefused) as caught:
            execute_work_order(self.store, order["id"], live=True, runner=runner)
        self.assertEqual(caught.exception.message, "path does not match the approved target")
        self.assertEqual(runner.calls, [])

    def test_delete_plan_does_not_touch_a_real_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keep.txt"
            path.write_text("keep", encoding="utf-8")
            order = self._approve(create_work_order(
                self.store, device_id=DEVICE, action="change.delete",
                target=str(path), operator_id=OPERATOR,
            ))
            runner = RecordingRunner()
            plan = execute_work_order(self.store, order["id"], live=False, runner=runner)
            self.assertFalse(plan["executed"])
            self.assertEqual(plan["argv"][0], "delete-file")
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_text(encoding="utf-8"), "keep")
            self.assertEqual(runner.calls, [])
            self.assertEqual(default_runner_invocations(), 0)

    def test_audit_shape_and_worker_round_trip_hide_the_password(self) -> None:
        order = self._approve(create_work_order(
            self.store, device_id=DEVICE, action="setup.onboard.local_user",
            target="alice", operator_id=OPERATOR,
        ))
        first = dict(self.store.audit[0])
        self.assertEqual(
            set(first),
            {"time", "device_id", "action", "target", "state", "operator_id", "error"},
        )
        runner = RecordingRunner()
        payload = {
            "device_id": DEVICE,
            "jobs": [{**order, "handler_input": {"password": SENTINEL}}, {"device_id": DEVICE, "state": "approved", "action": "repair.service.restart", "target": "BITS"}],
        }
        result = poll_once(payload, runner=runner, live=True, now=self.clock.moment)
        self.assertEqual(result["target"], "alice")
        self.assertEqual(runner.calls[0]["password"], SENTINEL)
        rendered = json.dumps(result)
        self.assertNotIn(SENTINEL, rendered)
        self.assertNotIn("BITS", rendered)
        self.assertGreater(len(self.store.audit), 1)
        self.assertEqual(self.store.audit[0], first)

    def test_worker_runs_one_job_for_its_own_device(self) -> None:
        own = self._approve(self._service())
        other = self._approve(self._service(device_id=OTHER, target="wuauserv"))
        runner = RecordingRunner()
        result = poll_once(
            {"device_id": DEVICE, "jobs": [other, own, own]},
            runner=runner, live=True, now=self.clock.moment,
        )
        self.assertEqual(result["order_id"], own["id"])
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(runner.calls[0]["target"], "Spooler")
        idle = poll_once({"device_id": DEVICE, "jobs": [other]}, now=self.clock.moment)
        self.assertEqual(idle["state"], "idle")
        beat = poll_once({
            "device_id": DEVICE, "heartbeat": True, "utc": UTC, "worker_version": WORKER_VERSION,
            "jobs": [],
        })
        self.assertEqual(set(beat["result"]), {"device_id", "utc", "worker_version"})
        with self.assertRaises(WorkRefused):
            poll_once({
                "device_id": DEVICE, "heartbeat": True, "utc": UTC,
                "worker_version": WORKER_VERSION, "screenshot": "x",
            })

    def test_worker_cli_reads_stdin_or_a_file_and_stays_offline(self) -> None:
        self.clock.moment = time.time()
        order = self._approve(self._service())
        payload = json.dumps({"device_id": DEVICE, "jobs": [order]})
        stdout = io.StringIO()
        code = main(["poll-once"], stdin=io.StringIO(payload), stdout=stdout)
        self.assertEqual(code, 0)
        body = json.loads(stdout.getvalue())
        self.assertEqual(body["state"], "planned")
        self.assertFalse(body["result"]["executed"])
        self.assertEqual(body["result"]["argv"], ["sc.exe", "start", "Spooler"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.json"
            path.write_text(payload, encoding="utf-8")
            again = io.StringIO()
            code = main(["poll-once", "--jobs", str(path)], stdout=again)
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(again.getvalue())["result"]["executed"])
        self.assertEqual(default_runner_invocations(), 0)
        self.assertNotIn("192.168.", Path(remote_worker.__file__).read_text(encoding="utf-8"))

    def test_service_fact_parser_reads_sc_text(self) -> None:
        facts = service_facts_from_text(
            "STATE              : 1  STOPPED",
            "START_TYPE         : 2   AUTO_START",
        )
        self.assertEqual(facts, {"start_type": "automatic", "status": "stopped"})
        running = service_facts_from_text(
            "STATE              : 4  RUNNING",
            "START_TYPE         : 3   DEMAND_START",
        )
        self.assertEqual(running, {"start_type": "manual", "status": "running"})


def tearDownModule() -> None:
    if default_runner_invocations() != 0:
        raise AssertionError("the default live runner was invoked")


if __name__ == "__main__":
    unittest.main()
