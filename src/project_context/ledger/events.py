"""Append-only ledger events. Every change to ledger state is one event;
history is never rewritten. Events carry their own `recorded_at`
timestamps so projection never reads a clock."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

LEDGER_EVENT_SCHEMA = "project_context.ledger_event.v1"


class LedgerError(Exception):
    """Typed runtime validation failure with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class EventType(str, Enum):
    ITEM_CREATED = "item_created"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    SATISFIED = "satisfied"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    RELATIONSHIP_ADDED = "relationship_added"


STATUS_EVENTS = frozenset(
    {
        EventType.BLOCKED,
        EventType.UNBLOCKED,
        EventType.SATISFIED,
        EventType.FAILED,
        EventType.SUPERSEDED,
        EventType.CANCELLED,
        EventType.EXPIRED,
        EventType.CONTRADICTED,
    }
)


@dataclass(frozen=True)
class Evidence:
    """Already-supplied verification evidence. Stage 6A records it; it
    performs no verification of its own."""

    kind: str
    ref: str
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "ref": self.ref, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Evidence":
        if not isinstance(data, dict):
            raise ValueError(f"invalid ledger evidence: {data!r}")
        unknown = set(data) - {"kind", "ref", "detail"}
        if unknown:
            raise ValueError(f"unknown ledger evidence keys: {sorted(unknown)}")
        return cls(kind=data["kind"], ref=data["ref"], detail=data.get("detail"))


@dataclass(frozen=True)
class LedgerEvent:
    """One append-only change. Optional fields are event-specific:

    - item_created: `item` (LedgerItem dict).
    - verified: `outcome` ("passed" | "failed"), `evidence` (Evidence dict).
    - contradicted: `contradicted_by` (item id), `evidence` (optional).
    - superseded: `superseded_by` (item id).
    - blocked: `reason`; optional `blocked_by` (item ids, informational).
    - relationship_added: `relationship` ({type, source_id, target_id}).
    - all: optional `actor`, `reason`.
    """

    event_id: str
    event: EventType
    item_id: str
    recorded_at: str
    item: dict[str, Any] | None = None
    outcome: str | None = None
    evidence: dict[str, Any] | None = None
    contradicted_by: str | None = None
    superseded_by: str | None = None
    blocked_by: tuple[str, ...] = ()
    relationship: dict[str, Any] | None = None
    actor: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "schema_version": LEDGER_EVENT_SCHEMA,
            "event_id": self.event_id,
            "event": self.event.value,
            "item_id": self.item_id,
            "recorded_at": self.recorded_at,
        }
        if self.item is not None:
            doc["item"] = self.item
        if self.outcome is not None:
            doc["outcome"] = self.outcome
        if self.evidence is not None:
            doc["evidence"] = self.evidence
        if self.contradicted_by is not None:
            doc["contradicted_by"] = self.contradicted_by
        if self.superseded_by is not None:
            doc["superseded_by"] = self.superseded_by
        if self.blocked_by:
            doc["blocked_by"] = list(self.blocked_by)
        if self.relationship is not None:
            doc["relationship"] = self.relationship
        if self.actor is not None:
            doc["actor"] = self.actor
        if self.reason is not None:
            doc["reason"] = self.reason
        return doc

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LedgerEvent":
        version = data.get("schema_version", LEDGER_EVENT_SCHEMA)
        if version != LEDGER_EVENT_SCHEMA:
            raise LedgerError("unsupported_schema", f"unsupported LedgerEvent schema: {version!r}")
        unknown = set(data) - {
            "schema_version",
            "event_id",
            "event",
            "item_id",
            "recorded_at",
            "item",
            "outcome",
            "evidence",
            "contradicted_by",
            "superseded_by",
            "blocked_by",
            "relationship",
            "actor",
            "reason",
        }
        if unknown:
            raise LedgerError("unsupported_schema", f"unknown LedgerEvent keys: {sorted(unknown)}")
        try:
            event = EventType(data["event"])
        except ValueError:
            raise LedgerError("unsupported_schema", f"unknown event type: {data.get('event')!r}")
        event_id = data.get("event_id")
        item_id = data.get("item_id")
        recorded_at = data.get("recorded_at")
        for field, value in (
            ("event_id", event_id),
            ("item_id", item_id),
            ("recorded_at", recorded_at),
        ):
            if not isinstance(value, str) or not value.strip():
                raise LedgerError("unsupported_schema", f"invalid {field}: {value!r}")
        outcome = data.get("outcome")
        if outcome is not None and outcome not in ("passed", "failed"):
            raise LedgerError("unsupported_schema", f"invalid outcome: {outcome!r}")
        if event is EventType.VERIFIED and outcome is None:
            raise LedgerError("unsupported_schema", "verified event requires an outcome")
        if event is EventType.ITEM_CREATED and not isinstance(data.get("item"), dict):
            raise LedgerError("unsupported_schema", "item_created event requires an item")
        if event is EventType.SUPERSEDED and not data.get("superseded_by"):
            raise LedgerError("unsupported_schema", "superseded event requires superseded_by")
        if event is EventType.CONTRADICTED and not data.get("contradicted_by"):
            raise LedgerError("unsupported_schema", "contradicted event requires contradicted_by")
        if event is EventType.RELATIONSHIP_ADDED and not isinstance(data.get("relationship"), dict):
            raise LedgerError("unsupported_schema", "relationship_added requires a relationship")
        return cls(
            event_id=event_id,
            event=event,
            item_id=item_id,
            recorded_at=recorded_at,
            item=data.get("item"),
            outcome=outcome,
            evidence=data.get("evidence"),
            contradicted_by=data.get("contradicted_by"),
            superseded_by=data.get("superseded_by"),
            blocked_by=tuple(data.get("blocked_by", [])),
            relationship=data.get("relationship"),
            actor=data.get("actor"),
            reason=data.get("reason"),
        )
