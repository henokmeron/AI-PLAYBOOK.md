"""Acceptance board scoring from recorded evidence. These tests do not contact the Pod."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops.acceptance_board import EVIDENCE_PATH, GIT_ENV, LIVE_GATES, board, read_runtime_tip

TIP = "1" * 40
OLD = "be9cbd2baf08ee1d9f1bbd192982c94575f57aeb"
NOW = datetime(2026, 10, 22, 19, 15, tzinfo=timezone.utc)

REQUIRED = {
    "live_health": ["http_200"],
    "deployment_parity": ["deployed_sha_read"],
    "inference_completion": ["completion_ok"],
    "rag_cited_and_abstain": ["rag_cited_answer_ok", "rag_abstention_ok"],
    "microsoft_mailbox_read": ["mailbox_read_ok"],
    "second_endpoint": ["second_endpoint_worker_ok"],
    "blackwell": ["blackwell_inference_ok"],
    "fresh_recovery": ["fresh_recovery_ok"],
    "independent_weight_backup": ["weight_backup_verified"],
}


def record(result: str, *, hours_ago: float = 1.0, kind: str = "live",
           deployed: str | None = TIP, source: str | None = TIP) -> dict:
    when = NOW - timedelta(hours=hours_ago)
    return {
        "source_sha": source,
        "deployed_sha": deployed,
        "command": "test fixture",
        "timestamp_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "result": result,
        "evidence_kind": kind,
    }


def all_passing() -> dict:
    return {gate: [record(result) for result in results] for gate, results in REQUIRED.items()}


class AcceptanceBoardTests(unittest.TestCase):
    def run_board(self, gates: dict, offline: list | None = None) -> dict:
        data = {"schema_version": 1, "gates": {k: {"evidence": v} for k, v in gates.items()}}
        if offline is not None:
            data["offline"] = offline
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "acceptance-evidence.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return board(evidence_path=path, now=NOW, intended_tip=TIP)

    @staticmethod
    def gate(payload: dict, gate_id: str) -> dict:
        return next(g for g in payload["live_gates"] if g["id"] == gate_id)

    def test_gate_ids_cover_every_live_gate(self) -> None:
        self.assertEqual({g["id"] for g in LIVE_GATES}, set(REQUIRED))
        payload = self.run_board(all_passing())
        for gate in payload["live_gates"]:
            self.assertEqual(gate["required_results"], REQUIRED[gate["id"]])
            self.assertIsInstance(gate["mandatory"], bool)
            self.assertTrue(gate["description"])

    def test_all_live_evidence_fresh_is_go(self) -> None:
        payload = self.run_board(all_passing())
        self.assertEqual(payload["live_score"]["passed"], len(REQUIRED))
        self.assertEqual(payload["live_score"]["total"], len(REQUIRED))
        self.assertEqual(payload["live_score"]["text"], f"{len(REQUIRED)}/{len(REQUIRED)}")
        self.assertEqual(payload["decision"], "GO")
        self.assertEqual(payload["microsoft_status"], "MAILBOX READ VERIFIED")

    def test_push_is_not_deploy(self) -> None:
        gates = all_passing()
        gates["deployment_parity"] = [
            {**record("pushed", deployed=None), "deployed_sha": None},
            record("deployed_sha_read", deployed=None),
        ]
        payload = self.run_board(gates)
        deployment = self.gate(payload, "deployment_parity")
        self.assertFalse(deployment["passed"])
        self.assertEqual(payload["decision"], "NO-GO")
        self.assertIn("Deployed commit equals the intended Git tip", payload["failing_acceptance"])
        self.assertTrue(any("push" in reason for reason in deployment["reasons"]))

    def test_deployed_sha_must_equal_intended_tip(self) -> None:
        gates = all_passing()
        gates["deployment_parity"] = [record("deployed_sha_read", deployed=OLD, source=OLD)]
        deployment = self.gate(self.run_board(gates), "deployment_parity")
        self.assertFalse(deployment["passed"])
        self.assertTrue(any(OLD[:12] in reason for reason in deployment["reasons"]))

    def test_http_200_is_not_inference_or_integration(self) -> None:
        gates = all_passing()
        for gate_id in ("inference_completion", "rag_cited_and_abstain", "microsoft_mailbox_read",
                        "second_endpoint", "blackwell"):
            gates[gate_id] = [record("http_200")]
        payload = self.run_board(gates)
        for gate_id in ("inference_completion", "rag_cited_and_abstain", "microsoft_mailbox_read",
                        "second_endpoint", "blackwell"):
            self.assertFalse(self.gate(payload, gate_id)["passed"], gate_id)
        self.assertTrue(self.gate(payload, "live_health")["passed"])
        self.assertEqual(payload["decision"], "NO-GO")

    def test_rag_needs_cited_answer_and_abstention(self) -> None:
        gates = all_passing()
        gates["rag_cited_and_abstain"] = [record("rag_cited_answer_ok")]
        rag = self.gate(self.run_board(gates), "rag_cited_and_abstain")
        self.assertFalse(rag["passed"])
        self.assertTrue(any("rag_abstention_ok" in reason for reason in rag["reasons"]))

    def test_stale_evidence_is_shown_stale_and_not_counted(self) -> None:
        gates = all_passing()
        gates["inference_completion"] = [record("completion_ok", hours_ago=25)]
        payload = self.run_board(gates)
        inference = self.gate(payload, "inference_completion")
        self.assertFalse(inference["passed"])
        self.assertTrue(inference["stale"])
        self.assertEqual(inference["status"], "STALE")
        self.assertTrue(inference["evidence"][0]["stale"])
        self.assertEqual(payload["live_score"]["passed"], len(REQUIRED) - 1)
        self.assertEqual(payload["decision"], "NO-GO")

    def test_future_timestamp_does_not_count(self) -> None:
        gates = all_passing()
        gates["live_health"] = [record("http_200", hours_ago=-2)]
        self.assertFalse(self.gate(self.run_board(gates), "live_health")["passed"])

    def test_local_and_mock_evidence_never_pass_a_live_gate(self) -> None:
        for kind in ("local", "mock", "none"):
            gates = all_passing()
            gates["inference_completion"] = [record("completion_ok", kind=kind)]
            inference = self.gate(self.run_board(gates), "inference_completion")
            self.assertFalse(inference["passed"], kind)

    def test_microsoft_without_mailbox_read_is_not_configured(self) -> None:
        for evidence in (
            [],
            [record("http_200")],
            [record("consent_ok")],
            [record("mailbox_read_ok", kind="mock")],
        ):
            gates = all_passing()
            gates["microsoft_mailbox_read"] = evidence
            payload = self.run_board(gates)
            mail = self.gate(payload, "microsoft_mailbox_read")
            self.assertFalse(mail["passed"])
            self.assertEqual(mail["status"], "NOT CONFIGURED")
            self.assertEqual(payload["microsoft_status"], "NOT CONFIGURED")
            self.assertEqual(payload["decision"], "NO-GO")
        gates = all_passing()
        gates["microsoft_mailbox_read"] = [record("mailbox_read_ok", hours_ago=30)]
        payload = self.run_board(gates)
        self.assertEqual(payload["microsoft_status"], "NOT CONFIGURED")
        self.assertEqual(self.gate(payload, "microsoft_mailbox_read")["status"], "STALE")

    def test_hardware_gates_need_their_own_evidence_kind(self) -> None:
        gates = all_passing()
        for gate_id in ("second_endpoint", "blackwell", "fresh_recovery", "independent_weight_backup"):
            gates[gate_id] = [record("completion_ok"), record("http_200"), record("deployed_sha_read")]
        payload = self.run_board(gates)
        for gate_id in ("second_endpoint", "blackwell", "fresh_recovery", "independent_weight_backup"):
            self.assertFalse(self.gate(payload, gate_id)["passed"], gate_id)

    def test_production_no_go_while_any_mandatory_gate_fails(self) -> None:
        mandatory = [g["id"] for g in LIVE_GATES if g["mandatory"]]
        self.assertIn("deployment_parity", mandatory)
        self.assertIn("microsoft_mailbox_read", mandatory)
        for gate_id in mandatory:
            gates = all_passing()
            gates[gate_id] = []
            payload = self.run_board(gates)
            self.assertEqual(payload["decision"], "NO-GO", gate_id)
            self.assertEqual(payload["production_decision"], "NO-GO", gate_id)
            self.assertIn(gate_id, payload["failing_mandatory"])
        optional = [g["id"] for g in LIVE_GATES if not g["mandatory"]]
        for gate_id in optional:
            gates = all_passing()
            gates[gate_id] = []
            payload = self.run_board(gates)
            self.assertEqual(payload["decision"], "GO", gate_id)
            self.assertLess(payload["live_score"]["passed"], payload["live_score"]["total"])

    def test_offline_progress_cannot_affect_live_score(self) -> None:
        offline = [{
            "id": "suite",
            "description": "Local suite",
            "evidence": record("pass", kind="local"),
        }]
        payload = self.run_board({}, offline=offline)
        self.assertEqual(payload["offline"]["percent"], 100)
        self.assertEqual(payload["live_score"]["passed"], 0)
        self.assertEqual(payload["live_acceptance_percent"], 0)
        self.assertEqual(payload["overall_percent"], 0)
        self.assertEqual(payload["decision"], "NO-GO")
        self.assertTrue(payload["offline_is_not_production_go"])

    def test_missing_or_malformed_evidence_file_is_no_go(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = board(evidence_path=Path(tmp) / "absent.json", now=NOW, intended_tip=TIP)
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            broken = board(evidence_path=bad, now=NOW, intended_tip=TIP)
        for payload in (missing, broken):
            self.assertEqual(payload["decision"], "NO-GO")
            self.assertEqual(payload["live_score"]["passed"], 0)
            self.assertTrue(payload["evidence_file_error"])

    def test_short_sha_cannot_pass_a_gate(self) -> None:
        gates = all_passing()
        gates["inference_completion"] = [record("completion_ok", deployed="be9cbd2")]
        payload = self.run_board(gates)
        gate = self.gate(payload, "inference_completion")
        self.assertFalse(gate["passed"])
        self.assertIn("40-character SHA", " ".join(gate["reasons"]))
        self.assertEqual(payload["decision"], "NO-GO")

    def test_unknown_intended_tip_fails_deployment(self) -> None:
        gates = all_passing()
        data = {"schema_version": 1, "gates": {k: {"evidence": v} for k, v in gates.items()}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            payload = board(evidence_path=path, now=NOW, intended_tip="", repo_root=Path(tmp))
        self.assertFalse(self.gate(payload, "deployment_parity")["passed"])
        self.assertEqual(payload["decision"], "NO-GO")

    def test_recorded_repo_evidence(self) -> None:
        self.assertTrue(EVIDENCE_PATH.is_file())
        data = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        recorded = {
            gate_id: {item.get("result") for item in entry.get("evidence", [])}
            for gate_id, entry in data.get("gates", {}).items()
        }
        payload = board(now=NOW, intended_tip=TIP)
        self.assertFalse(self.gate(payload, "deployment_parity")["passed"])
        self.assertEqual(payload["decision"], "NO-GO")
        for gate in payload["live_gates"]:
            if not set(REQUIRED[gate["id"]]) <= recorded.get(gate["id"], set()):
                self.assertFalse(gate["passed"], gate["id"])
            for item in gate["evidence"]:
                self.assertEqual(item["evidence_kind"], "live")
                for key in ("source_sha", "deployed_sha"):
                    if item.get(key) is not None:
                        self.assertRegex(item[key], r"^[0-9a-f]{40}$")
                stamp = datetime.strptime(item["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ")
                self.assertLessEqual(stamp.replace(tzinfo=timezone.utc), datetime.now(timezone.utc) + timedelta(minutes=5))
        if "mailbox_read_ok" not in recorded.get("microsoft_mailbox_read", set()):
            self.assertEqual(payload["microsoft_status"], "NOT CONFIGURED")
        later = board(now=datetime.now(timezone.utc) + timedelta(days=30), intended_tip=TIP)
        self.assertEqual(later["live_score"]["passed"], 0)
        self.assertEqual(later["decision"], "NO-GO")
        self.assertEqual(self.gate(later, "live_health")["status"], "STALE")
        text = EVIDENCE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", text)


class RuntimeTipTests(unittest.TestCase):
    """Docs-only commits after a deploy do not move the deployment target."""

    def setUp(self) -> None:
        self.git = os.environ.get(GIT_ENV, "").strip() or shutil.which("git")
        if not self.git:
            self.skipTest("git is not available")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        try:
            self.run_git("init", "-q")
        except (OSError, subprocess.CalledProcessError):
            self.tmp.cleanup()
            self.skipTest("git cannot be run here")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_git(self, *args: str) -> str:
        done = subprocess.run(
            [self.git, "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
             "-c", "commit.gpgsign=false", *args],
            capture_output=True, text=True, check=True,
        )
        return done.stdout.strip()

    def commit(self, relative: str, text: str) -> str:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.run_git("add", "-A")
        self.run_git("commit", "-q", "-m", relative)
        return self.run_git("rev-parse", "HEAD")

    def test_docs_only_commits_keep_the_code_tip(self) -> None:
        code = self.commit("app.py", "print(1)\n")
        self.commit("docs/results/evidence.json", "{}\n")
        self.commit("README.md", "notes\n")
        self.commit("ops/test_board.py", "assert True\n")
        head = self.commit("rag/tests/test_pipeline.py", "assert True\n")
        self.assertEqual(read_runtime_tip(self.root, head), code)
        newer = self.commit("app.py", "print(2)\n")
        self.assertEqual(read_runtime_tip(self.root, newer), newer)
        nested = self.commit("rag/fixtures/policy.md", "rail travel\n")
        self.assertEqual(read_runtime_tip(self.root, nested), nested)


if __name__ == "__main__":
    unittest.main()
