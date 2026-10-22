"""Recorded offline implementation and live acceptance for System Status.

Offline percent counts offline criteria only. Live acceptance percent counts
live criteria only. ``overall_percent`` is the live figure so an offline 100
cannot be read as production GO. Decision stays NO-GO while any live gate fails.
A temp extract is not a fresh machine. A push is not a deployment.
"""
from __future__ import annotations

# Local/mock checks run on this Windows PC. They do not start the pod.
LOCAL_SUITE_PASSED = True
ISOLATED_RECOVER_PASSED = True
# True only after the archive bytes were read back. This recording commit is not inside that archive.
CODE_TIP_ARCHIVE_READ_BACK = True

ACCEPTANCE_GATES = (
    ("deployed commit equals intended Git tip", False),
    ("mail end-to-end", False),
    ("second endpoint", False),
    ("Blackwell live acceptance", False),
    ("fresh-environment recovery", False),
)


def _bar(percent: int) -> str:
    filled = max(0, min(20, (percent + 2) // 5))
    return "[" + ("#" * filled) + ("-" * (20 - filled)) + "]"


def _row(
    name: str,
    lane: str,
    criteria: list[tuple[str, bool]],
    evidence: str,
    next_action: str,
    blocker: str,
) -> dict:
    done = [text for text, flag in criteria if flag]
    remaining = [text for text, flag in criteria if not flag]
    percent = (100 * len(done)) // len(criteria) if criteria else 0
    return {
        "name": name,
        "lane": lane,
        "percent": percent,
        "bar": _bar(percent),
        "completed": done,
        "remaining": remaining,
        "evidence": evidence,
        "next_action": next_action,
        "blocker": blocker,
    }


def _average(rows: list[dict]) -> int:
    if not rows:
        return 0
    return sum(row["percent"] for row in rows) // len(rows)


def workstreams() -> list[dict]:
    offline = [
        _row(
            "Source and local tests",
            "offline",
            [
                ("Suite entry is python -m ops.run_tests", True),
                ("This session's local suite exited 0", LOCAL_SUITE_PASSED),
                ("Auth unit tests passed in that suite", LOCAL_SUITE_PASSED),
                ("Host and origin regressions passed in that suite", LOCAL_SUITE_PASSED),
            ],
            "LOCAL/MOCK on Python 3.11. python -m ops.run_tests was 41 modules, 0 failed, exit 0, about 132 seconds. integrations.tests.test_endpoint skipped 1. api.test_gateway_reliability was 27 tests, logged a Windows socket abort, and still passed. windows_repair.tests.test_live_diagnostics passed on its automatic retry. The pod was not used.",
            "Keep the local suite green on the next code change. That does not deploy it.",
            "code",
        ),
        _row(
            "RAG offline cases",
            "offline",
            [
                ("Empty collection abstains", True),
                ("Malformed file is skipped and does not fail the collection", True),
                ("Duplicate evidence collapses to one group", True),
                ("Unavailable embedding does not replace BM25", True),
            ],
            "rag.tests.test_retrieval_pipeline.OfflineEdgeTests. Retrieval stays lexical BM25. No embedding service is called for ranking. Live Qwen generation was not run.",
            "Re-run live RAG only after the pod is Running on the deployed tip.",
            "code",
        ),
        _row(
            "Release packaging and temp extract",
            "offline",
            [
                ("Checksum sidecar is stored outside the archive", True),
                ("Isolated temp extract of 6f07b58", ISOLATED_RECOVER_PASSED),
                ("The extract is labelled a temp extract and not a fresh machine", ISOLATED_RECOVER_PASSED),
            ],
            "python -m ops.release.recover extracted commit 6f07b581f4dd4a7ee2811a99e9ac62edbee3eac8 into %TEMP%\\ai-playbook-recover-6f07b58-temp-extract. Sidecar SHA-256 3cf154feb99536781232408ea06cc93373e14fe69e1d866daffa64ecdb015de7 matched. ops/release/START.sh was present. This is a temp extract, not a fresh machine, not a second computer, and not a deployment.",
            "Package the new tip locally after it is pushed. Do not copy it to the volume.",
            "code",
        ),
        _row(
            "Git parity",
            "offline",
            [
                ("Checker refuses a different origin", True),
                ("Checker refuses a force push", True),
                ("This checkout origin was read without pushing", True),
            ],
            "python -m ops.git_parity --ls-remote after the push showed d6d3ac2f9cb7fb3632b042c3fe58eefe0e180eb4 on HEAD, main, feature/qwen-a100-start-hardening, and feature/qwen3.5-27b-integration. That push was a fast-forward from b0ead09a8df7c5cd6abace971331ef46de6646a7. A matching SHA is not a deployment.",
            "After each push, run python -m ops.git_parity --ls-remote and require one SHA on those three refs.",
            "code",
        ),
        _row(
            "Documentation",
            "offline",
            [
                ("Playbook, handoff, status, matrix, manual, and recovery describe the offline and live split", True),
                ("Second endpoint and Blackwell stay labelled NOT TESTED", True),
                ("Those procedures were not marked executed", True),
            ],
            "Docs name running A100 mlar88u3ku8utm and stopped H100 xx9cjogra5vcwl. They do not say mail is end-to-end verified. Production stays NO-GO.",
            "Update the same docs when the next verified fact changes.",
            "code",
        ),
        _row(
            "Source archive of this tip",
            "offline",
            [
                ("GitHub origin is the expected repository", True),
                ("Local archive of the latest packaged code tip was read back", CODE_TIP_ARCHIVE_READ_BACK),
                ("No new archive was copied to the Global Volume", True),
            ],
            "Python read the archive of d6d3ac2f9cb7fb3632b042c3fe58eefe0e180eb4 back from %LOCALAPPDATA%\\AI-PLAYBOOK\\releases\\d6d3ac2f9cb7fb3632b042c3fe58eefe0e180eb4\\AI-PLAYBOOK-d6d3ac2f9cb7fb3632b042c3fe58eefe0e180eb4.tar.gz. 715415 bytes, 383 members, SHA-256 50df5371070cc5004cad45ec645e9da938460f077b373f08240fda1e24ac98ee. The sidecar matched. It contains reported_model_count. This recording commit is not inside that archive. It was not copied to the Global Volume. The older temp extract of 5cb961b is not a fresh machine.",
            "Package again after the next code change. Do not copy the archive to the volume unless the owner approves.",
            "code",
        ),
    ]
    live = [
        _row(
            "RunPod deployment parity",
            "live",
            [
                ("Deployed commit equals the intended Git tip", False),
                ("Current pod health was read while the pod was Running this session", False),
            ],
            "The running pod is A100 mlar88u3ku8utm (screeching_crimson_vole) at $1.80/hr with Global Volume cmv2p5m0d000007jk9o3931ea mounted at /workspace. START.sh --preflight passed. Ports :8002, :8010, and :8080 refused connections. Qwen is not loaded. The pod checkout is not this tip. H100 xx9cjogra5vcwl stayed Stopped at $0.00/hr and was not started. A refused connection is not live acceptance.",
            "Do not start the H100. The next approved command on the running A100 is bash /workspace/ai-platform-release/START.sh. That was not run.",
            "user approval",
        ),
        _row(
            "Microsoft mail",
            "live",
            [
                ("A running console has loaded the application id", False),
                ("A mailbox read succeeded", False),
            ],
            "NOT CONFIGURED. The saved redirect is http://127.0.0.1:18080/api/microsoft/callback with delegated User.Read and Mail.Read only. This session did not open Azure, did not create a secret, and did not read a mailbox. The A100 is Running and the console process is not listening, so the consent screen was not started.",
            "One consent click only after an approved console deploy with MICROSOFT_TENANT set to d595636e-9ef4-4890-b8a7-bde8dd5cab03. common will not complete sign-in.",
            "user approval",
        ),
        _row(
            "Second endpoint",
            "live",
            [
                ("A second Windows computer ran the endpoint worker", False),
            ],
            "This development PC is not a second endpoint. Its collectors are not that result.",
            "Use another Windows computer. Do not count this PC.",
            "hardware",
        ),
        _row(
            "Blackwell",
            "live",
            [
                ("Live install, serve, and infer on a CC 12.0 GPU", False),
            ],
            "NOT TESTED. The running A100 is not a CC 12.0 GPU. The stopped H100 is not a Blackwell result. No Blackwell pod was started.",
            "Use a CC 12.0 GPU and driver 575 or newer. Do not claim the A100 or the H100 as that result.",
            "hardware",
        ),
        _row(
            "Fresh environment",
            "live",
            [
                ("Recovery on a fresh machine or a new pod", False),
            ],
            "The temp extract of 6f07b58 is not a fresh machine and not a new pod.",
            "Run recovery on a machine that does not already have this checkout, or on a new pod with this volume, after approval.",
            "hardware",
        ),
        _row(
            "Volume and weights",
            "live",
            [
                ("This tip was copied to the Global Volume", False),
                ("Weight shards were copied off the volume and verified", False),
            ],
            "Global Volume cmv2p5m0d000007jk9o3931ea was not written. No S3 key was created. Shard bytes were not recomputed. The S3 API does not apply to this Global Volume.",
            "Do not copy the volume or the ~52 GB shards unless the owner approves that backup.",
            "user approval",
        ),
    ]
    return offline + live


def board() -> dict:
    rows = workstreams()
    offline_rows = [row for row in rows if row["lane"] == "offline"]
    live_rows = [row for row in rows if row["lane"] == "live"]
    offline_percent = _average(offline_rows)
    live_percent = _average(live_rows)
    failing = [name for name, passed in ACCEPTANCE_GATES if not passed]
    decision = "GO" if not failing and live_percent == 100 else "NO-GO"
    return {
        "decision": decision,
        "production_decision": decision,
        "offline_percent": offline_percent,
        "offline_bar": _bar(offline_percent),
        "offline_label": "Offline implementation",
        "live_acceptance_percent": live_percent,
        "live_acceptance_bar": _bar(live_percent),
        "live_label": "Live acceptance",
        "overall_percent": live_percent,
        "overall_bar": _bar(live_percent),
        "offline_is_not_production_go": True,
        "failing_acceptance": failing,
        "microsoft_status": "NOT CONFIGURED",
        "microsoft_reason": (
            "Portal configuration is not a mailbox read. "
            "No running console has loaded the application id."
        ),
        "note": (
            "Offline implementation percent is not a production GO. "
            "Live acceptance is separate. "
            "A temp extract is not a fresh machine. "
            "A push is not a deployment. "
            "HTTP health on a stopped pod is not acceptance. "
            "A refused connection on the running A100 is not acceptance."
        ),
        "workstreams": rows,
        "offline_workstreams": offline_rows,
        "live_workstreams": live_rows,
    }
