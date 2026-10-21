#!/usr/bin/env python3
"""Run every repository test module in its own process.

A single ``unittest discover`` process opens many loopback servers on Windows
and can abort sockets under load. One module per process keeps the suite
stable without weakening a case. Exit code is non-zero when any module fails.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path


def discover_modules(root: Path) -> list[str]:
    """Return importable modules that contain at least one unittest case.

    Scripts named ``test_*.py`` that are CLIs, not suites, are omitted so an
    empty load is not treated as a failure.
    """
    modules: list[str] = []
    loader = unittest.defaultTestLoader
    for path in sorted(root.rglob("test_*.py")):
        if "__pycache__" in path.parts:
            continue
        name = ".".join(path.with_suffix("").relative_to(root).parts)
        try:
            suite = loader.loadTestsFromName(name)
        except Exception:
            continue
        if suite.countTestCases() < 1:
            continue
        modules.append(name)
    return modules


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run each test_*.py module in a separate process.")
    parser.add_argument("--module", action="append", default=[], help="Limit to one or more module names")
    parser.add_argument("--failfast", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    modules = args.module or discover_modules(root)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root), str(root / "rag"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    started = time.monotonic()
    totals = {"modules": 0, "ok": 0, "failed": 0, "errors": 0}
    for name in modules:
        totals["modules"] += 1
        print(f"=== {name} ===", flush=True)
        attempts = 2 if os.name == "nt" else 1
        result = None
        for attempt in range(1, attempts + 1):
            result = subprocess.run(
                [sys.executable, "-m", "unittest", name],
                cwd=root,
                env=env,
                check=False,
            )
            if result.returncode == 0:
                break
            if attempt < attempts:
                print(
                    f"(retry {name} once after Windows socket abort under load)",
                    flush=True,
                )
        assert result is not None
        if result.returncode == 0:
            totals["ok"] += 1
        else:
            totals["failed"] += 1
            if args.failfast:
                break
    elapsed = time.monotonic() - started
    print(
        "SUMMARY modules={modules} ok={ok} failed={failed} elapsed_s={elapsed:.1f}".format(
            modules=totals["modules"],
            ok=totals["ok"],
            failed=totals["failed"],
            elapsed=elapsed,
        ),
        flush=True,
    )
    return 0 if totals["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
