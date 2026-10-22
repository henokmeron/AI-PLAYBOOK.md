"""Live acceptance score computed from recorded evidence.

Gate rules live here. Observations live in ``docs/results/acceptance-evidence.json``.
A live gate passes only when, for every result token it requires, there is a
record with ``evidence_kind`` ``live``, that exact ``result``, and a
``timestamp_utc`` inside the gate's freshness window. Deployment also needs
``deployed_sha`` equal to the intended source tip, so a push (``source_sha``
only) never passes. ``http_200`` satisfies the health gate and nothing else.

Offline implementation progress is computed separately from LOCAL/MOCK records
and never enters the live score or the production decision.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = REPO_ROOT / "docs" / "results" / "acceptance-evidence.json"
INTENDED_TIP_ENV = "AI_PLAYBOOK_INTENDED_TIP"
GIT_ENV = "AI_PLAYBOOK_GIT"
DOC_ONLY_PATHSPECS = ("docs/**", "*.md", "**/test_*.py", "**/tests/**")

EVIDENCE_KINDS = ("live", "local", "mock", "none")
OFFLINE_FRESHNESS_HOURS = 168
FUTURE_TOLERANCE = timedelta(minutes=5)
_SHA = re.compile(r"^[0-9a-f]{40}$")

LIVE_GATES = (
    {
        "id": "live_health",
        "description": "Qwen, gateway, and console health return HTTP 200 on the running pod",
        "mandatory": True,
        "required_results": ["http_200"],
        "freshness_hours": 24,
    },
    {
        "id": "deployment_parity",
        "description": "Deployed commit equals the intended Git tip",
        "mandatory": True,
        "required_results": ["deployed_sha_read"],
        "freshness_hours": 24,
        "requires_tip_parity": True,
    },
    {
        "id": "inference_completion",
        "description": "A live chat completion returned content",
        "mandatory": True,
        "required_results": ["completion_ok"],
        "freshness_hours": 24,
    },
    {
        "id": "rag_cited_and_abstain",
        "description": "Live RAG returned a cited answer and abstained on an unanswerable question",
        "mandatory": True,
        "required_results": ["rag_cited_answer_ok", "rag_abstention_ok"],
        "freshness_hours": 24,
    },
    {
        "id": "microsoft_mailbox_read",
        "description": "A live Microsoft mailbox search returned the expected harmless phrase",
        "mandatory": True,
        "required_results": ["mailbox_read_ok", "mailbox_content_match_ok"],
        "freshness_hours": 24,
    },
    {
        "id": "second_endpoint",
        "description": "A second Windows computer ran the endpoint worker",
        "mandatory": True,
        "required_results": ["second_endpoint_worker_ok"],
        "freshness_hours": 168,
    },
    {
        "id": "blackwell",
        "description": "Live install, serve, and infer on a CC 12.0 (Blackwell) GPU",
        "mandatory": True,
        "required_results": ["blackwell_inference_ok"],
        "freshness_hours": 168,
    },
    {
        "id": "fresh_recovery",
        "description": "Recovery on a fresh machine or a new pod (a temp extract does not count)",
        "mandatory": True,
        "required_results": ["fresh_recovery_ok"],
        "freshness_hours": 168,
    },
    {
        "id": "independent_weight_backup",
        "description": "Weight shards were copied off the Global Volume and verified",
        "mandatory": False,
        "required_results": ["weight_backup_verified"],
        "freshness_hours": 168,
    },
)

MICROSOFT_GATE = "microsoft_mailbox_read"


def _bar(percent: int) -> str:
    filled = max(0, min(20, (percent + 2) // 5))
    return "[" + ("#" * filled) + ("-" * (20 - filled)) + "]"


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_dir(root: Path) -> Path | None:
    marker = root / ".git"
    if marker.is_dir():
        return marker
    if marker.is_file():
        text = marker.read_text(encoding="utf-8", errors="replace").strip()
        if text.startswith("gitdir:"):
            return (root / text[len("gitdir:"):].strip()).resolve()
    return None


def read_git_head(root: Path) -> str | None:
    """Return the checked-out commit without running git. None when unreadable."""
    try:
        git = _git_dir(root)
        if git is None:
            return None
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head if _SHA.match(head) else None
        ref = head[len("ref:"):].strip()
        common = git
        if (git / "commondir").is_file():
            common = (git / (git / "commondir").read_text(encoding="utf-8").strip()).resolve()
        for base in (git, common):
            path = base / ref
            if path.is_file():
                value = path.read_text(encoding="utf-8").strip()
                return value if _SHA.match(value) else None
        packed = common / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split(" ")
                if len(parts) == 2 and parts[1] == ref and _SHA.match(parts[0]):
                    return parts[0]
    except OSError:
        return None
    return None


def _resolve_tip(intended_tip: str | None, repo_root: Path) -> tuple[str | None, str]:
    if intended_tip is not None:
        tip = intended_tip.strip().lower()
        return (tip, "argument") if _SHA.match(tip) else (None, "argument (not a full SHA)")
    env = os.environ.get(INTENDED_TIP_ENV, "").strip().lower()
    if env:
        return (env, INTENDED_TIP_ENV) if _SHA.match(env) else (None, f"{INTENDED_TIP_ENV} (not a full SHA)")
    head = read_git_head(repo_root)
    if head:
        runtime = read_runtime_tip(repo_root, head)
        if runtime:
            if runtime == head:
                return head, "git HEAD of this checkout"
            return runtime, f"latest commit outside {', '.join(DOC_ONLY_PATHSPECS)} (HEAD {_short(head)} adds docs only)"
        return head, "git HEAD of this checkout (git unavailable; docs-only commits not discounted)"
    return None, "unknown"


def read_runtime_tip(root: Path, head: str) -> str | None:
    """Latest commit at or before HEAD that changes anything outside docs and tests.

    Recording evidence is itself a commit, so the deployed code can never equal
    the HEAD that records it. Docs and test files are not served.
    None when git cannot be run; callers then keep the stricter HEAD.
    """
    git = os.environ.get(GIT_ENV, "").strip() or shutil.which("git")
    if not git:
        return None
    excludes = [f":(exclude,glob){spec}" for spec in DOC_ONLY_PATHSPECS]
    try:
        done = subprocess.run(
            [git, "-C", str(root), "log", "-1", "--format=%H", head, "--", ".", *excludes],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = done.stdout.strip().lower()
    return value if done.returncode == 0 and _SHA.match(value) else None


def _load(path: Path) -> tuple[dict, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"evidence file not found: {path.name}"
    except (OSError, ValueError) as exc:
        return {}, f"evidence file unreadable: {type(exc).__name__}"
    if not isinstance(data, dict):
        return {}, "evidence file is not a JSON object"
    return data, ""


def _records(value: object) -> list[dict]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _short(sha: object) -> str:
    return sha[:12] if isinstance(sha, str) and sha else "none"


def _assess(record: dict, now: datetime, freshness: timedelta) -> dict:
    """Common checks for one record. ``problems`` empty means it is live, timed, and fresh."""
    kind = record.get("evidence_kind")
    when = _parse_time(record.get("timestamp_utc"))
    problems: list[str] = []
    stale = False
    age_hours = None
    if kind not in EVIDENCE_KINDS:
        problems.append(f"evidence_kind {kind!r} is not one of {', '.join(EVIDENCE_KINDS)}")
    for key in ("source_sha", "deployed_sha"):
        value = record.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str) or not _SHA.match(value.strip().lower()):
            problems.append(f"{key} must be a full 40-character SHA")
    if when is None:
        problems.append("timestamp_utc is missing or not an ISO-8601 UTC time")
    elif when > now + FUTURE_TOLERANCE:
        problems.append("timestamp_utc is in the future")
    else:
        age = now - when
        age_hours = round(age.total_seconds() / 3600, 2)
        if age > freshness:
            stale = True
    return {
        "source_sha": record.get("source_sha"),
        "deployed_sha": record.get("deployed_sha"),
        "command": record.get("command") or "",
        "timestamp_utc": record.get("timestamp_utc"),
        "result": record.get("result"),
        "evidence_kind": kind if kind in EVIDENCE_KINDS else "none",
        "detail": record.get("detail") or "",
        "citation": record.get("citation") or "",
        "age_hours": age_hours,
        "stale": stale,
        "problems": problems,
    }


def _evaluate_gate(gate: dict, entry: dict, now: datetime, tip: str | None) -> dict:
    hours = entry.get("freshness_hours", gate["freshness_hours"])
    if not isinstance(hours, (int, float)) or isinstance(hours, bool) or hours <= 0:
        hours = gate["freshness_hours"]
    freshness = timedelta(hours=hours)
    evidence = [_assess(record, now, freshness) for record in _records(entry.get("evidence"))]
    required = list(gate["required_results"])
    reasons: list[str] = []
    satisfied: list[str] = []
    stale_only: list[str] = []

    for item in evidence:
        if item["result"] not in required:
            reasons.append(f"result {item['result']!r} does not satisfy {' + '.join(required)}")

    for token in required:
        matches = [item for item in evidence if item["result"] == token]
        if not matches:
            reasons.append(f"no {token} evidence")
            continue
        qualified = False
        blocked_by_staleness = False
        for item in matches:
            own: list[str] = list(item["problems"])
            if item["evidence_kind"] != "live":
                own.append(f"{token} evidence is {item['evidence_kind']}, not live")
            if gate.get("requires_tip_parity"):
                deployed = item["deployed_sha"]
                if not deployed:
                    own.append("push or source_sha only: no deployed_sha was read from the serving host")
                elif tip is None:
                    own.append("intended Git tip is unknown")
                elif str(deployed).lower() != tip:
                    own.append(f"deployed_sha {_short(deployed)} is not the intended tip {_short(tip)}")
            if not own and not item["stale"]:
                qualified = True
                break
            if not own and item["stale"]:
                blocked_by_staleness = True
            reasons.extend(own)
        if qualified:
            satisfied.append(token)
        elif blocked_by_staleness:
            stale_only.append(token)
            reasons.append(f"{token} evidence is older than {hours:g}h (STALE)")

    passed = len(satisfied) == len(required)
    stale = bool(stale_only) and not passed
    if passed:
        status = "PASS"
    elif stale and len(satisfied) + len(stale_only) == len(required):
        status = "STALE"
    elif gate["id"] == MICROSOFT_GATE:
        status = "NOT CONFIGURED"
    elif not evidence:
        status = "NO EVIDENCE"
    else:
        status = "FAIL"
    for item in evidence:
        item.pop("problems")
    return {
        "id": gate["id"],
        "description": gate["description"],
        "mandatory": gate["mandatory"],
        "required_results": required,
        "freshness_hours": hours,
        "passed": passed,
        "stale": stale,
        "status": status,
        "reasons": [] if passed else list(dict.fromkeys(reasons)),
        "evidence": evidence,
    }


def _offline(items: object, now: datetime) -> dict:
    freshness = timedelta(hours=OFFLINE_FRESHNESS_HOURS)
    criteria = []
    for raw in items if isinstance(items, list) else []:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        evidence = [_assess(record, now, freshness) for record in _records(raw.get("evidence"))]
        done = any(
            not item["problems"] and not item["stale"]
            and item["evidence_kind"] in {"local", "mock"} and item["result"] == "pass"
            for item in evidence
        )
        for item in evidence:
            item.pop("problems")
        criteria.append({
            "id": str(raw["id"]),
            "description": str(raw.get("description") or raw["id"]),
            "done": done,
            "stale": bool(evidence) and not done and any(item["stale"] for item in evidence),
            "evidence": evidence,
        })
    done_count = sum(1 for item in criteria if item["done"])
    percent = (100 * done_count) // len(criteria) if criteria else 0
    return {
        "label": "Offline implementation",
        "done": done_count,
        "total": len(criteria),
        "text": f"{done_count}/{len(criteria)}",
        "percent": percent,
        "bar": _bar(percent),
        "freshness_hours": OFFLINE_FRESHNESS_HOURS,
        "criteria": criteria,
    }


def board(
    *,
    evidence_path: Path | None = None,
    now: datetime | None = None,
    intended_tip: str | None = None,
    repo_root: Path | None = None,
) -> dict:
    path = Path(evidence_path) if evidence_path is not None else EVIDENCE_PATH
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    tip, tip_source = _resolve_tip(intended_tip, Path(repo_root) if repo_root else REPO_ROOT)
    data, error = _load(path)
    gate_data = data.get("gates") if isinstance(data.get("gates"), dict) else {}

    gates = []
    for gate in LIVE_GATES:
        entry = gate_data.get(gate["id"])
        gates.append(_evaluate_gate(gate, entry if isinstance(entry, dict) else {}, moment, tip))

    passed = sum(1 for g in gates if g["passed"])
    mandatory = [g for g in gates if g["mandatory"]]
    mandatory_passed = sum(1 for g in mandatory if g["passed"])
    failing = [g for g in mandatory if not g["passed"]]
    decision = "NO-GO" if failing or error else "GO"
    live_percent = (100 * passed) // len(gates) if gates else 0
    offline = _offline(data.get("offline"), moment)
    mail = next(g for g in gates if g["id"] == MICROSOFT_GATE)

    return {
        "decision": decision,
        "production_decision": decision,
        "evaluated_at_utc": _iso(moment),
        "evidence_file": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else path.name,
        "evidence_file_error": error,
        "intended_source_tip": tip,
        "intended_tip_source": tip_source,
        "live_label": "Live acceptance",
        "live_score": {
            "passed": passed,
            "total": len(gates),
            "text": f"{passed}/{len(gates)}",
            "mandatory_passed": mandatory_passed,
            "mandatory_total": len(mandatory),
            "mandatory_text": f"{mandatory_passed}/{len(mandatory)}",
        },
        "live_acceptance_percent": live_percent,
        "live_acceptance_bar": _bar(live_percent),
        "overall_percent": live_percent,
        "overall_bar": _bar(live_percent),
        "live_gates": gates,
        "failing_mandatory": [g["id"] for g in failing],
        "failing_acceptance": [g["description"] for g in failing],
        "stale_gates": [g["id"] for g in gates if g["stale"]],
        "offline": offline,
        "offline_label": offline["label"],
        "offline_percent": offline["percent"],
        "offline_bar": offline["bar"],
        "offline_is_not_production_go": True,
        "microsoft_status": "MAILBOX READ VERIFIED" if mail["passed"] else "NOT CONFIGURED",
        "microsoft_reason": (
            "A live mailbox search returned the expected harmless phrase inside the freshness window."
            if mail["passed"]
            else "No fresh live mailbox_content_match_ok record. HTTP 200, a message count, and a search that returns count 0 are not a content match."
        ),
        "note": (
            "Offline implementation percent is not a production GO and does not change the live score. "
            "Live gates count only fresh live evidence. "
            "A push is not a deployment. HTTP 200 is not inference. "
            "Stale evidence is shown as STALE and does not count."
        ),
    }
