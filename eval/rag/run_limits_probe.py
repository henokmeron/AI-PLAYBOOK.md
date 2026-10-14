#!/usr/bin/env python3
"""Context-limit probes for Document Q&A against an isolated gateway (stdlib only).

Probes that stress the 8192-token Qwen context: maximum allowed history,
top_k=20 and a large table. A healthy gateway must answer (or abstain) with
HTTP 200, never a 5xx from context overflow. Optionally measures characters
per token on representative text through vLLM's read-only ``/tokenize``.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_e2e import DATASET, call  # noqa: E402

BIG_TABLE = "band,rate,placement,notes\n" + "\n".join(
    f"Band {i},{60 + i * 0.37:.3f},Type {i % 7},Reviewed quarterly by the regional panel; contract ref NB-{i:05d}"
    for i in range(2, 600)
)


def history(pairs: int, chars: int) -> list[dict[str, str]]:
    turns = []
    for i in range(pairs):
        turns.append({"role": "user", "content": (f"Earlier question {i} about placement fees. " * 40)[:chars]})
        turns.append({"role": "assistant", "content": (f"Earlier answer {i} citing rates. " * 40)[:chars]})
    return turns


def tokenize_ratio(vllm_url: str, model: str, samples: dict[str, str]) -> dict[str, float]:
    ratios = {}
    for name, text in samples.items():
        body = json.dumps({"model": model, "prompt": text}).encode()
        request = urllib.request.Request(vllm_url.rstrip("/") + "/tokenize", data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            count = json.loads(response.read())["count"]
        ratios[name] = round(len(text) / count, 3)
    return ratios


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8014")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--vllm-url", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if ":8010" in args.base_url or ":8080" in args.base_url:
        print("refusing to probe the live gateway/console ports", file=sys.stderr)
        return 2
    key = args.key_file.read_text(encoding="utf-8").strip()
    collection = f"limits-{args.label}"[:40]
    for path in sorted((DATASET / "docs").iterdir()):
        call(args.base_url, key, "POST", "/v1/rag/documents", {
            "collection": collection, "filename": path.name, "overwrite": True,
            "content_base64": base64.b64encode(path.read_bytes()).decode()}, 120)
    status, body = call(args.base_url, key, "POST", "/v1/rag/documents", {
        "collection": collection, "filename": "rate-register.csv", "overwrite": True,
        "content_base64": base64.b64encode(BIG_TABLE.encode()).decode()}, 120)
    probes = {
        "table_topk20_max_history": {"question": "Give the complete table of daily rates for Standard Placements for every age band.",
                                     "top_k": 20, "history": history(6, 990)},
        "csv_list_every_topk20": {"question": "List every vehicle based at the Leeds depot with its monthly lease cost.", "top_k": 20},
        "big_table_list_all_topk20_max_history": {"question": "List all bands with their rate and placement type from the rate register.",
                                                  "top_k": 20, "history": history(6, 990)},
        "big_table_list_all_topk20": {"question": "List all bands with their rate and placement type from the rate register.", "top_k": 20},
    }
    results = {"label": args.label, "big_table_upload_status": status, "probes": {}}
    for name, payload in probes.items():
        timing: dict[str, float] = {}
        status, body = call(args.base_url, key, "POST", "/v1/rag/ask", {**payload, "collection": collection}, 300, timing)
        retrieval = body.get("retrieval", {}) if isinstance(body, dict) else {}
        results["probes"][name] = {
            "http_status": status,
            "gateway_status": body.get("status"),
            "reason": body.get("reason"),
            "latency_ms": timing.get("ms"),
            "prompt_tokens": (body.get("usage") or {}).get("prompt_tokens"),
            "sources_returned": retrieval.get("sources_returned"),
            "sources_dropped_for_budget": retrieval.get("sources_dropped_for_budget"),
            "history_messages_dropped": retrieval.get("history_messages_dropped"),
            "truncated": retrieval.get("truncated"),
        }
    if args.vllm_url and args.model:
        workbook = next((DATASET / "docs").glob("*.xlsx"))
        sys.path.insert(0, str(HERE.parent.parent / "rag"))
        try:
            from document_loaders import read_document

            sheet_text = read_document(workbook)
        except Exception:  # parser deps missing
            sheet_text = ""
        samples = {
            "prose_policy": (DATASET / "docs" / "expenses-policy.txt").read_text(encoding="utf-8"),
            "csv_rows": BIG_TABLE[:6000],
        }
        if sheet_text:
            samples["xlsx_rows"] = sheet_text
        results["chars_per_token"] = tokenize_ratio(args.vllm_url, args.model, samples)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
