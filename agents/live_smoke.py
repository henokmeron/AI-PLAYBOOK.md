"""Optional live smoke run of the agent loop against the platform gateway.

NOT TESTED against the live Pod. Run only on the Pod (gateway is loopback-only),
never print the key, and expect one or two short Qwen completions:

    python3 -m agents.live_smoke --gateway http://127.0.0.1:8010/v1 \
        --key-file /tmp/platform-gateway.key --model qwen3.5-27b

Exit code 0 means the model followed the JSON action protocol and the final
answer contains the calculator result.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .builtin import calculator_tool
from .model import OpenAICompatibleClient
from .runtime import AgentRunner
from .state import Budget
from .tools import ToolRegistry
from .trace import ExecutionTrace


def read_key(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > 4096:
        raise SystemExit("key file missing or too large")
    return path.read_text(encoding="utf-8").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="http://127.0.0.1:8010/v1")
    parser.add_argument("--key-file", type=Path, default=Path("/tmp/platform-gateway.key"))
    parser.add_argument("--model", default=None)
    args = parser.parse_args(argv)
    key = read_key(args.key_file)
    client = OpenAICompatibleClient(args.gateway, lambda: key, model=args.model)
    trace = ExecutionTrace(known_secrets=frozenset({key}))
    runner = AgentRunner(client, ToolRegistry([calculator_tool()]), trace=trace, max_reply_tokens=512)
    task = runner.new_task(
        "A placement costs 99.498 per day. Use the calculator to compute the cost for 7 days, "
        "then answer with the exact value.",
        budget=Budget(max_iterations=4, max_tool_calls=2, max_total_tokens=12_000, max_wall_seconds=240),
    )
    task = runner.run(task)
    summary = {
        "state": task.state.value, "answer": task.final_answer, "failure": task.failure_reason,
        "usage": task.usage.__dict__, "events": trace.kinds(),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0 if task.state.value == "final" and "696.486" in (task.final_answer or "") else 1


if __name__ == "__main__":
    sys.exit(main())
