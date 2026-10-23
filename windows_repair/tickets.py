"""Helpdesk tickets linked to an enrolled device record.

A ticket stores an id, title, severity, status, device link, evidence
reference, and activity. An AI recommendation and a verified diagnosis are
separate fields. The severity floor is fixed in this module. A model request
cannot store a lower severity. Repair does not run until a person approves.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

FIXTURE_LABEL = "not-the-second-endpoint"
_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_CRITICAL = ("ransomware", "data loss", "cannot boot", "disk full")
_HIGH = ("outage", "service down", "cannot log in", "cannot print")
_MEDIUM = ("slow", "intermittent")
_ACTOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}\Z")
_DEVICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_EVIDENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z")


class TicketError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def severity_floor(text: str) -> str:
    """Fixed floor from the words in the ticket. The model does not choose this."""
    lowered = " ".join(str(text).casefold().split())
    if any(token in lowered for token in _CRITICAL):
        return "critical"
    if any(token in lowered for token in _HIGH):
        return "high"
    if any(token in lowered for token in _MEDIUM):
        return "medium"
    return "low"


def apply_severity(requested: Any, floor: str) -> tuple[str, str | None, bool]:
    """Return stored severity, the model request, and whether a downgrade was blocked."""
    if requested is None or requested == "":
        return floor, None, False
    if not isinstance(requested, str) or requested not in _SEVERITY_RANK:
        raise TicketError("severity must be low, medium, high, or critical")
    if _SEVERITY_RANK[requested] < _SEVERITY_RANK[floor]:
        return floor, requested, True
    return requested, requested, False


def _actor(value: Any) -> str:
    if not isinstance(value, str) or not _ACTOR.fullmatch(value):
        raise TicketError("actor is required")
    return value


def _text(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise TicketError(f"{label} is required")
    text = " ".join(value.split())
    if not text or len(text) > limit:
        raise TicketError(f"{label} is required")
    return text


def _evidence(value: Any) -> str:
    if not isinstance(value, str):
        raise TicketError("evidence reference is required")
    text = " ".join(value.split())
    if "://" in text or "\\" in text or text.startswith("/"):
        raise TicketError("evidence must be a reference, not a public URL or path")
    if not _EVIDENCE.fullmatch(text):
        raise TicketError("evidence reference is required")
    return text


def link_device(device: dict[str, Any]) -> dict[str, Any]:
    """Copy a device link. A fixture is never the second endpoint."""
    if not isinstance(device, dict):
        raise TicketError("device record is required")
    if device.get("counts_as_second_endpoint") is True:
        raise TicketError("this record cannot be treated as the second endpoint")
    device_id = device.get("device_id")
    if not isinstance(device_id, str) or not _DEVICE.fullmatch(device_id):
        raise TicketError("device id is required")
    label = device.get("fixture_label") or ""
    if label and label != FIXTURE_LABEL:
        raise TicketError("the only local fixture label is not-the-second-endpoint")
    return {
        "device_id": device_id,
        "counts_as_second_endpoint": False,
        "fixture_label": label,
    }


class TicketStore:
    def __init__(self, root: Path | str, *, clock: Callable[[], float] = time.time) -> None:
        self.root = Path(root)
        self._clock = clock
        self._lock = threading.Lock()
        self._tickets: dict[str, dict[str, Any]] = {}
        self._load()

    def create(
        self,
        *,
        title: Any,
        detail: Any,
        actor: Any,
        device: dict[str, Any],
        evidence_ref: Any,
        requested_severity: Any = None,
    ) -> dict[str, Any]:
        who = _actor(actor)
        heading = _text(title, "title", 120)
        body = _text(detail, "detail", 2000)
        linked = link_device(device)
        evidence = _evidence(evidence_ref)
        floor = severity_floor(f"{heading} {body}")
        stored, requested, blocked = apply_severity(requested_severity, floor)
        ticket = {
            "id": uuid.uuid4().hex,
            "title": heading,
            "detail": body,
            "severity": stored,
            "severity_floor": floor,
            "model_requested_severity": requested,
            "severity_downgrade_blocked": blocked,
            "status": "open",
            "device": linked,
            "evidence_ref": evidence,
            "ai_recommendation": None,
            "verified_diagnosis": None,
            "approval": None,
            "activity": [],
        }
        self._activity(ticket, who, "created", f"Opened at severity {stored}.")
        if blocked:
            self._activity(ticket, who, "severity_floor", f"A request for {requested} was raised to {stored}.")
        with self._lock:
            self._tickets[ticket["id"]] = ticket
            self._save_locked()
        return self.public(ticket)

    def list_tickets(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._tickets.values())
        rows.sort(key=lambda item: item["activity"][0]["at"] if item["activity"] else 0)
        return [self.public(item) for item in rows]

    def get(self, ticket_id: str) -> dict[str, Any]:
        with self._lock:
            ticket = self._tickets.get(ticket_id)
        if ticket is None:
            raise TicketError("ticket not found")
        return self.public(ticket)

    def recommend(self, ticket_id: str, actor: Any, text: Any, requested_severity: Any = None) -> dict[str, Any]:
        """Record an AI recommendation. This does not verify the diagnosis or lower severity."""
        who = _actor(actor)
        recommendation = _text(text, "recommendation", 2000)
        with self._lock:
            ticket = self._require(ticket_id)
            if requested_severity is not None:
                stored, requested, blocked = apply_severity(requested_severity, ticket["severity_floor"])
                ticket["model_requested_severity"] = requested
                if _SEVERITY_RANK[stored] < _SEVERITY_RANK[ticket["severity"]]:
                    blocked = True
                else:
                    ticket["severity"] = stored
                ticket["severity_downgrade_blocked"] = bool(ticket["severity_downgrade_blocked"] or blocked)
                if blocked:
                    self._activity(
                        ticket, who, "severity_floor",
                        f"A request for {requested} was kept at {ticket['severity']}.",
                    )
            ticket["ai_recommendation"] = recommendation
            self._activity(ticket, who, "ai_recommendation", "Recorded an AI recommendation. It is not a verified diagnosis.")
            self._save_locked()
            return self.public(ticket)

    def verify_diagnosis(self, ticket_id: str, actor: Any, text: Any) -> dict[str, Any]:
        who = _actor(actor)
        diagnosis = _text(text, "diagnosis", 2000)
        with self._lock:
            ticket = self._require(ticket_id)
            ticket["verified_diagnosis"] = diagnosis
            self._activity(ticket, who, "verified_diagnosis", "A person recorded a verified diagnosis.")
            self._save_locked()
            return self.public(ticket)

    def request_repair(self, ticket_id: str, actor: Any) -> dict[str, Any]:
        who = _actor(actor)
        with self._lock:
            ticket = self._require(ticket_id)
            if ticket["status"] == "completed":
                raise TicketError("ticket is already completed")
            ticket["status"] = "awaiting_approval"
            self._activity(ticket, who, "repair_proposed", "Repair is proposed and will not run until a person approves it.")
            self._save_locked()
            return self.public(ticket)

    def approve(self, ticket_id: str, approver: Any) -> dict[str, Any]:
        who = _actor(approver)
        with self._lock:
            ticket = self._require(ticket_id)
            if ticket["status"] not in {"awaiting_approval", "approved"}:
                raise TicketError("repair has not been proposed")
            ticket["status"] = "approved"
            ticket["approval"] = {"approver": who, "at": self._clock()}
            self._activity(ticket, who, "approved", "A person approved the repair. It has not run yet.")
            self._save_locked()
            return self.public(ticket)

    def execute_repair(
        self,
        ticket_id: str,
        actor: Any,
        executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        who = _actor(actor)
        with self._lock:
            ticket = self._require(ticket_id)
            if ticket["status"] != "approved" or not ticket.get("approval"):
                self._activity(ticket, who, "repair_refused", "Approval is required before a repair can run.")
                self._save_locked()
                view = self.public(ticket)
                view["executed"] = False
                view["changed_device"] = False
                view["repair_status"] = "approval_required"
                return view
            if executor is None:
                outcome = {
                    "executed": False,
                    "changed_device": False,
                    "repair_status": "approved_not_run",
                }
            else:
                outcome = executor(self.public(ticket))
                if not isinstance(outcome, dict):
                    outcome = {"executed": False, "changed_device": False, "repair_status": "approved_not_run"}
            executed = bool(outcome.get("executed"))
            changed = bool(outcome.get("changed_device"))
            if executed:
                ticket["status"] = "completed"
            self._activity(
                ticket,
                who,
                "repair_finished" if executed else "repair_held",
                "Repair finished." if executed else "Approval is recorded. No repair ran.",
            )
            self._save_locked()
            view = self.public(ticket)
            view["executed"] = executed
            view["changed_device"] = changed
            view["repair_status"] = "completed" if executed else str(outcome.get("repair_status") or "approved_not_run")
            return view

    def public(self, ticket: dict[str, Any]) -> dict[str, Any]:
        device = dict(ticket["device"])
        device["counts_as_second_endpoint"] = False
        return {
            "id": ticket["id"],
            "title": ticket["title"],
            "detail": ticket["detail"],
            "severity": ticket["severity"],
            "severity_floor": ticket["severity_floor"],
            "model_requested_severity": ticket["model_requested_severity"],
            "severity_downgrade_blocked": ticket["severity_downgrade_blocked"],
            "status": ticket["status"],
            "device": device,
            "evidence_ref": ticket["evidence_ref"],
            "ai_recommendation": ticket["ai_recommendation"],
            "verified_diagnosis": ticket["verified_diagnosis"],
            "approval": dict(ticket["approval"]) if ticket.get("approval") else None,
            "activity": [dict(item) for item in ticket["activity"]],
        }

    def _require(self, ticket_id: str) -> dict[str, Any]:
        if not isinstance(ticket_id, str) or ticket_id not in self._tickets:
            raise TicketError("ticket not found")
        return self._tickets[ticket_id]

    def _activity(self, ticket: dict[str, Any], actor: str, action: str, detail: str) -> None:
        ticket["activity"].append({
            "at": self._clock(),
            "actor": actor,
            "action": action,
            "detail": detail,
        })

    def _load(self) -> None:
        path = self.root / "tickets.json"
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    self._tickets[item["id"]] = item

    def _save_locked(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "tickets.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(list(self._tickets.values()), sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
