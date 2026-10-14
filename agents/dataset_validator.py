"""Validate a chat-format JSONL dataset for future LoRA/QLoRA fine-tuning.

No training happens here. This only checks structure, provenance fields,
split hygiene and obvious secret leakage so a dataset can be reviewed before
anyone spends GPU time on it. See docs/fine-tuning.md.

Usage::

    python -m agents.dataset_validator path/to/dataset.jsonl [--max-tokens 8192]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .redaction import SECRET_PATTERNS

DATASET_SCHEMA_VERSION = 1
SPLITS = {"train", "validation", "test"}
ROLES = {"system", "user", "assistant"}
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
MAX_LINE_BYTES = 256 * 1024
MAX_RECORDS = 200_000
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
UK_NI_RE = re.compile(r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.IGNORECASE)
REQUIRED_FIELDS = {"id", "split", "messages", "source", "license", "contains_personal_data"}
OPTIONAL_FIELDS = {"schema_version", "tags", "consent_basis", "notes", "created"}


@dataclass
class Report:
    records: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    splits: Counter = field(default_factory=Counter)
    licenses: Counter = field(default_factory=Counter)
    max_estimated_tokens: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "records": self.records, "splits": dict(self.splits),
            "licenses": dict(self.licenses), "max_estimated_tokens": self.max_estimated_tokens,
            "errors": self.errors[:200], "warnings": self.warnings[:200],
            "error_count": len(self.errors), "warning_count": len(self.warnings),
        }


def _conversation_key(messages: list[dict[str, Any]]) -> str:
    prompt = "\n".join(m["content"].strip().casefold() for m in messages if m.get("role") == "user")
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def validate_record(record: Any, line_no: int, report: Report, max_tokens: int) -> dict[str, Any] | None:
    where = f"line {line_no}"
    if not isinstance(record, dict):
        report.errors.append(f"{where}: record must be a JSON object")
        return None
    missing = REQUIRED_FIELDS - set(record)
    unknown = set(record) - REQUIRED_FIELDS - OPTIONAL_FIELDS
    if missing:
        report.errors.append(f"{where}: missing fields {sorted(missing)}")
        return None
    if unknown:
        report.errors.append(f"{where}: unknown fields {sorted(unknown)}")
    if record.get("schema_version", DATASET_SCHEMA_VERSION) != DATASET_SCHEMA_VERSION:
        report.errors.append(f"{where}: unsupported schema_version")
    if not isinstance(record["id"], str) or not ID_RE.fullmatch(record["id"]):
        report.errors.append(f"{where}: id must be 1-128 safe characters")
    if record["split"] not in SPLITS:
        report.errors.append(f"{where}: split must be one of {sorted(SPLITS)}")
    for name in ("source", "license"):
        if not isinstance(record[name], str) or not record[name].strip():
            report.errors.append(f"{where}: {name} must be a non-empty string (data rights must be recorded)")
    if not isinstance(record["contains_personal_data"], bool):
        report.errors.append(f"{where}: contains_personal_data must be true or false")
    elif record["contains_personal_data"] and not str(record.get("consent_basis", "")).strip():
        report.errors.append(f"{where}: personal data requires a consent_basis")

    messages = record["messages"]
    if not isinstance(messages, list) or len(messages) < 2:
        report.errors.append(f"{where}: messages must be a list with at least a user and assistant turn")
        return None
    expected = "user"
    total_chars = 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or set(message) - {"role", "content"} or "role" not in message:
            report.errors.append(f"{where}: message {index} must have only role and content")
            return None
        role, content = message.get("role"), message.get("content")
        if role not in ROLES or not isinstance(content, str) or not content.strip():
            report.errors.append(f"{where}: message {index} has an invalid role or empty content")
            return None
        if role == "system":
            if index != 0:
                report.errors.append(f"{where}: system message only allowed first")
            continue
        if role != expected:
            report.errors.append(f"{where}: roles must alternate user/assistant (message {index})")
            return None
        expected = "assistant" if role == "user" else "user"
        total_chars += len(content)
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                report.errors.append(f"{where}: message {index} appears to contain a credential")
                break
        if not record["contains_personal_data"] and (EMAIL_RE.search(content) or UK_NI_RE.search(content)):
            report.warnings.append(f"{where}: possible personal data but contains_personal_data is false")
    if messages[-1]["role"] != "assistant":
        report.errors.append(f"{where}: final message must be an assistant turn")
    estimated = total_chars // 4 + 8 * len(messages)
    report.max_estimated_tokens = max(report.max_estimated_tokens, estimated)
    if estimated > max_tokens:
        report.errors.append(f"{where}: ~{estimated} tokens exceeds the {max_tokens}-token training context")
    return record


def validate_file(path: Path, max_tokens: int = 8192) -> Report:
    report = Report()
    seen_ids: set[str] = set()
    split_by_prompt: dict[str, str] = {}
    with Path(path).open("rb") as stream:
        for line_no, raw in enumerate(stream, start=1):
            if len(raw) > MAX_LINE_BYTES:
                report.errors.append(f"line {line_no}: line exceeds {MAX_LINE_BYTES} bytes")
                continue
            if not raw.strip():
                continue
            if report.records >= MAX_RECORDS:
                report.errors.append(f"dataset exceeds {MAX_RECORDS} records")
                break
            report.records += 1
            try:
                record = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                report.errors.append(f"line {line_no}: not valid UTF-8 JSON")
                continue
            checked = validate_record(record, line_no, report, max_tokens)
            if checked is None:
                continue
            record_id = checked.get("id")
            if record_id in seen_ids:
                report.errors.append(f"line {line_no}: duplicate id {record_id!r}")
            seen_ids.add(record_id)
            split = checked.get("split")
            report.splits[split] += 1
            report.licenses[str(checked.get("license"))] += 1
            key = _conversation_key(checked["messages"])
            previous = split_by_prompt.get(key)
            if previous is not None and previous != split:
                report.errors.append(
                    f"line {line_no}: identical prompt appears in both {previous} and {split} (split leakage)"
                )
            split_by_prompt.setdefault(key, split)
    if report.records and not report.splits.get("test"):
        report.warnings.append("no test split: before/after benchmarks need a held-out test set")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-tokens", type=int, default=8192)
    args = parser.parse_args(argv)
    report = validate_file(args.path, args.max_tokens)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
