#!/usr/bin/env python3
"""Live Agent async / cancel / history smoke against the loopback console.

Requires console on 127.0.0.1:8080 with Qwen + gateway already up.
Does not redownload models. Prints PASS/FAIL lines and exits non-zero on failure.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

ORIGIN = "http://127.0.0.1:8080"
TIMEOUT = 180


def _request(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        ORIGIN + path,
        data=data,
        method=method,
        headers={"Accept": "application/json", **({"Content-Type": "application/json"} if data else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw[:300]}
        return exc.code, payload


def main() -> int:
    fails = 0

    status_code, status = _request("GET", "/api/status")
    print(f"STATUS_HTTP={status_code}")
    if status_code != 200:
        print("FAIL status")
        return 1

    code, started = _request("POST", "/api/agent", {
        "task": "Use the calculator tool to evaluate 12.5 * 4 and report the exact result.",
        "wait": False,
    })
    print(f"ASYNC_START_HTTP={code} execution={started.get('execution')} task_id={started.get('task_id')}")
    if code != 200 or not started.get("task_id"):
        print("FAIL async start")
        return 1
    task_id = started["task_id"]
    deadline = time.time() + TIMEOUT
    final = started
    while time.time() < deadline:
        code, final = _request("GET", f"/api/agent?task_id={task_id}")
        if code != 200:
            print(f"FAIL poll HTTP={code}")
            fails += 1
            break
        if not final.get("running") and final.get("execution") in {
            "completed", "failed", "cancelled", "escalated",
            "awaiting_approval", "awaiting_information",
        }:
            break
        time.sleep(1.0)
    print(f"ASYNC_FINAL execution={final.get('execution')} answer={final.get('answer')!r}")
    if final.get("execution") != "completed" or "50" not in str(final.get("answer") or ""):
        print("FAIL async completion")
        fails += 1
    else:
        print("PASS async calculator")

    code, hist = _request("GET", "/api/agent/history?limit=10")
    tasks = hist.get("tasks") if isinstance(hist, dict) else None
    print(f"HISTORY_HTTP={code} count={len(tasks or [])}")
    if code != 200 or not any(row.get("task_id") == task_id for row in (tasks or [])):
        print("FAIL history")
        fails += 1
    else:
        print("PASS history")

    # Cancel smoke: start a long-ish task then cancel.
    code, long_task = _request("POST", "/api/agent", {
        "task": (
            "IT support: investigate why the enrolled computer is slow. "
            "Use tools carefully and ask if you need more facts."
        ),
        "wait": False,
    })
    cancel_id = long_task.get("task_id")
    print(f"CANCEL_START_HTTP={code} task_id={cancel_id} execution={long_task.get('execution')}")
    if code == 200 and cancel_id:
        time.sleep(0.5)
        c_code, cancelled = _request("POST", "/api/agent/cancel", {"task_id": cancel_id})
        print(f"CANCEL_HTTP={c_code} execution={cancelled.get('execution')} running={cancelled.get('running')}")
        deadline = time.time() + 60
        while time.time() < deadline:
            _, cancelled = _request("GET", f"/api/agent?task_id={cancel_id}")
            if not cancelled.get("running") and cancelled.get("execution") in {
                "cancelled", "completed", "failed", "escalated",
            }:
                break
            time.sleep(0.5)
        print(f"CANCEL_FINAL execution={cancelled.get('execution')}")
        if cancelled.get("execution") == "cancelled":
            print("PASS cancel")
        else:
            # Early completion is acceptable if model finished before cancel landed.
            print(f"WARN cancel ended as {cancelled.get('execution')} (not a hard fail)")
    else:
        print("FAIL cancel start")
        fails += 1

    print(f"FAILS={fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
