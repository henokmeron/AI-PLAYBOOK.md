"""Recorded finish-order progress for the existing console status page.

Percentages count completed criteria. Editing a sentence does not change a
percentage. HTTP 200 is not a recovery, and a push is not a deployment.
"""
from __future__ import annotations

# Set from commands run in this session. A document edit must not flip these.
LOCAL_SUITE_PASSED = True
ISOLATED_RECOVER_PASSED = True

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


def _row(name: str, criteria: list[tuple[str, bool]], evidence: str, next_action: str, blocker: str) -> dict:
    done = [text for text, flag in criteria if flag]
    remaining = [text for text, flag in criteria if not flag]
    percent = (100 * len(done)) // len(criteria)
    return {
        "name": name,
        "percent": percent,
        "bar": _bar(percent),
        "completed": done,
        "remaining": remaining,
        "evidence": evidence,
        "next_action": next_action,
        "blocker": blocker,
    }


def workstreams() -> list[dict]:
    return [
        _row(
            "Source and tests",
            [
                ("Suite entry is python -m ops.run_tests", True),
                ("Release tests reject unsafe archives and a non-fast-forward", True),
                ("This session's full local suite exited 0", LOCAL_SUITE_PASSED),
                ("The H100 re-ran this suite", False),
            ],
            "Local suite only. The pod checkout was not used to run tests.",
            "Keep the suite green on the next code change.",
            "hardware",
        ),
        _row(
            "Recovery and release",
            [
                ("Checksum is stored in a sidecar file outside the archive", True),
                ("Isolated local extract into a temp directory", ISOLATED_RECOVER_PASSED),
                ("Fresh-machine or new-pod recovery", False),
                ("Volume copy of this tip", False),
            ],
            "An isolated extract is not a fresh machine. The volume was not written.",
            "Package the new tip locally, then wait for approval before any volume copy.",
            "user approval",
        ),
        _row(
            "RunPod deployment parity",
            [
                ("Read-only health on the running pod was recorded", True),
                ("update-source-only.sh is fast-forward only and does not signal services", True),
                ("Deployed commit equals the intended Git tip", False),
            ],
            "2026-10-22T01:18:42Z SSH: HEAD a0e9422145aae4e38025709d1ca88288e42f375b; :8002/health 200; :8010/health 200; :8080/api/status 200. HTTP 200 is not parity.",
            "After approval, fast-forward /tmp/AI-PLAYBOOK with update-source-only.sh. Do not run it until then.",
            "user approval",
        ),
        _row(
            "RAG",
            [
                ("RAG unit tests exist in this tree", True),
                ("Live Qwen RAG was re-run this session", False),
            ],
            "No live generation was sent. Older E2E notes were not repeated.",
            "Re-run RAG only against the deployed tip, with the gateway key left unread.",
            "user approval",
        ),
        _row(
            "Authentication and security",
            [
                ("Named operator login is implemented and covered by unit tests", True),
                ("The running console is this tip", False),
            ],
            "The pod console is still checkout a0e9422. Privileged repair was not run.",
            "Do not restart the console until a deploy is approved.",
            "user approval",
        ),
        _row(
            "Microsoft integration",
            [
                ("Saved Authentication blade has the loopback public-client redirect", True),
                ("Delegated Mail.Read and User.Read only; admin consent required No", True),
                ("A running console has loaded the application id", False),
                ("A mailbox read succeeded", False),
            ],
            "Authentication (Preview) shows Mobile and desktop applications and http://127.0.0.1:18080/api/microsoft/callback. Supported accounts: Single tenant only - Default Directory. Tenant d595636e-9ef4-4890-b8a7-bde8dd5cab03. Status label NOT CONFIGURED.",
            "One consent click after an approved console that loads the client id and MICROSOFT_TENANT set to that directory. common will not complete sign-in.",
            "user approval",
        ),
        _row(
            "Source backups",
            [
                ("GitHub origin is the expected repository", True),
                ("Local archive of d8c32ff was read back and matches its manifest", True),
                ("Local archive of the commit that contains this board was read back", False),
                ("This tip was copied to the Global Volume", False),
            ],
            "d8c32ff archive SHA-256 de30f6a2877fee34036731ab58073da8e0433cd6a10742e4ecfb4b6f3437f0c6, 685460 bytes, 377 members. Not on the volume.",
            "After this commit is pushed, package it and record that hash in a following commit.",
            "code",
        ),
        _row(
            "Model-weight and runtime backups",
            [
                ("Runtime archive checksum was verified on the volume on 2026-10-22", True),
                ("Weight shards were copied off the volume and verified", False),
                ("Shard hashes were recomputed this session", False),
            ],
            "Weights and the runtime archive remain only on Global Volume cmv2p5m0d000007jk9o3931ea. No independent weight backup exists.",
            "Do not copy the ~52GB shards unless the owner approves a separate backup.",
            "user approval",
        ),
        _row(
            "Documentation",
            [
                ("Playbook, handoff, recovery, status, matrix, and manual exist", True),
                ("Source update and volume transfer include preflight, rollback, and acceptance", True),
                ("Second-endpoint procedure has been executed", False),
                ("Blackwell procedure has been executed", False),
            ],
            "Second endpoint and Blackwell stay NOT TESTED. Hardware required: another Windows computer, and a CC 12.0 GPU with driver 575 or newer.",
            "Keep the procedures labelled NOT TESTED until that hardware is used.",
            "hardware",
        ),
        _row(
            "Live acceptance",
            [
                ("Pod health URLs returned HTTP 200", True),
                ("Deployed commit equals the intended Git tip", False),
                ("Mail end-to-end", False),
                ("Second endpoint", False),
                ("Blackwell live acceptance", False),
                ("Fresh-environment recovery", False),
            ],
            "HTTP 200 at 2026-10-22T01:18:42Z on the old checkout. That is not acceptance.",
            "Leave the decision NO-GO until the failing gates pass.",
            "user approval",
        ),
    ]


def board() -> dict:
    rows = workstreams()
    overall = sum(row["percent"] for row in rows) // len(rows)
    failing = [name for name, passed in ACCEPTANCE_GATES if not passed]
    return {
        "decision": "NO-GO" if failing else "GO",
        "failing_acceptance": failing,
        "overall_percent": overall,
        "overall_bar": _bar(overall),
        "microsoft_status": "NOT CONFIGURED",
        "microsoft_reason": (
            "The saved redirect and delegated Mail.Read are portal configuration. "
            "No running console has loaded the application id, and no mailbox was read."
        ),
        "note": (
            "Percentages count completed criteria. A document edit does not move them. "
            "HTTP 200 is not a recovery. A push is not a deployment."
        ),
        "workstreams": rows,
    }
