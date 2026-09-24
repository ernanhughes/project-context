"""Deterministic projection: an ordered event stream folds into ledger state.

Pure function of its input. No network, no model, no clock, no
randomness, no filesystem access. Timestamps are copied from recorded
events, never read from the wall clock. The same ordered event sequence
always yields the same state; `LedgerState.digest()` makes that
checkable.

Dependency rule (the only derived behaviour in Stage 6A): a `depends_on`
edge whose target is unmet blocks the dependent while it is active, and
a blocked dependent whose every dependency becomes met returns to
active. A dependency is met when its target is satisfied or verified.
Nothing is ever executed; only the representable state changes, and
every derived change is recorded in the item history with its cause.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from project_context.ledger.events import EventType, LedgerError, LedgerEvent
from project_context.ledger.lifecycle import is_legal
from project_context.ledger.records import (
    TERMINAL_STATUSES,
    LedgerItem,
    LifecycleStatus,
    VerificationState,
)
from project_context.ledger.relationships import Relationship


@dataclass(frozen=True)
class HistoryStep:
    event_id: str
    from_status: str | None
    to_status: str
    recorded_at: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "recorded_at": self.recorded_at,
            "note": self.note,
        }


@dataclass(frozen=True)
class ProjectedItem:
    item: LedgerItem
    status: LifecycleStatus
    verification: VerificationState
    created_at: str
    updated_at: str
    statement_digest: str
    superseded_by: str | None = None
    contradicted_by: str | None = None
    evidence: tuple[dict[str, Any], ...] = ()
    depends_on: tuple[str, ...] = ()
    history: tuple[HistoryStep, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.item.to_dict(),
            "status": self.status.value,
            "verification": self.verification.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "statement_digest": self.statement_digest,
            "superseded_by": self.superseded_by,
            "contradicted_by": self.contradicted_by,
            "evidence": list(self.evidence),
            "depends_on": list(self.depends_on),
            "history": [step.to_dict() for step in self.history],
        }


@dataclass(frozen=True)
class LedgerState:
    items: tuple[ProjectedItem, ...]
    relationships: tuple[Relationship, ...]
    event_ids: tuple[str, ...]

    def get(self, item_id: str) -> ProjectedItem:
        for item in self.items:
            if item.item.item_id == item_id:
                return item
        raise KeyError(item_id)

    def explain(self, item_id: str) -> tuple[str, ...]:
        """Deterministic, structure-derived account of an item's state.
        No model involved: every line names the event that caused it."""
        return tuple(explain(self.get(item_id)))

    def digest(self) -> str:
        canonical = {
            "items": [item.to_dict() for item in self.items],
            "relationships": [rel.to_dict() for rel in self.relationships],
            "event_ids": list(self.event_ids),
        }
        return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "relationships": [rel.to_dict() for rel in self.relationships],
            "event_ids": list(self.event_ids),
            "digest": self.digest(),
        }


def explain(item: ProjectedItem) -> list[str]:
    lines = [
        f"created by {item.history[0].event_id} at {item.created_at} "
        f"[kind={item.item.kind.value} authority={item.item.authority.value}]"
    ]
    for step in item.history[1:]:
        lines.append(
            f"{step.event_id} at {step.recorded_at}: "
            f"{step.from_status} -> {step.to_status} ({step.note})"
        )
    lines.append(f"status={item.status.value} verification={item.verification.value}")
    if item.superseded_by is not None:
        lines.append(f"superseded_by={item.superseded_by}")
    if item.contradicted_by is not None:
        lines.append(f"contradicted_by={item.contradicted_by}")
    if item.depends_on:
        lines.append(f"depends_on={','.join(item.depends_on)}")
    for evidence in item.evidence:
        lines.append(f"evidence={evidence.get('kind')}:{evidence.get('ref')}")
    return lines


@dataclass
class _MutableItem:
    record: LedgerItem
    status: LifecycleStatus
    verification: VerificationState
    created_at: str
    updated_at: str
    statement_digest: str
    superseded_by: str | None = None
    contradicted_by: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    history: list[HistoryStep] = field(default_factory=list)


def _digest_statement(statement: str) -> str:
    return hashlib.sha256(statement.encode("utf-8")).hexdigest()


def _dependency_met(state: dict[str, _MutableItem], target_id: str) -> bool:
    target = state[target_id]
    return (
        target.status is LifecycleStatus.SATISFIED
        or target.verification is VerificationState.VERIFIED
    )


def _set_status(
    mutable: _MutableItem,
    event: LedgerEvent,
    to_status: LifecycleStatus,
    note: str,
) -> None:
    if not is_legal(mutable.status, to_status):
        raise LedgerError(
            "invalid_transition",
            f"{mutable.record.item_id}: {mutable.status.value} -> {to_status.value} "
            f"is not a legal transition (event {event.event_id})",
        )
    mutable.history.append(
        HistoryStep(
            event_id=event.event_id,
            from_status=mutable.status.value,
            to_status=to_status.value,
            recorded_at=event.recorded_at,
            note=note,
        )
    )
    mutable.status = to_status
    mutable.updated_at = event.recorded_at


def _reevaluate_dependents(
    state: dict[str, _MutableItem], event: LedgerEvent, changed_id: str
) -> None:
    for candidate in state.values():
        if changed_id not in candidate.depends_on:
            continue
        if candidate.status is not LifecycleStatus.BLOCKED:
            continue
        if all(_dependency_met(state, dep) for dep in candidate.depends_on):
            candidate.history.append(
                HistoryStep(
                    event_id=event.event_id,
                    from_status=candidate.status.value,
                    to_status=LifecycleStatus.ACTIVE.value,
                    recorded_at=event.recorded_at,
                    note=f"dependencies_met after {changed_id}",
                )
            )
            candidate.status = LifecycleStatus.ACTIVE
            candidate.updated_at = event.recorded_at


def project(events: list[LedgerEvent]) -> LedgerState:
    """Fold an ordered event list into current ledger state."""
    state: dict[str, _MutableItem] = {}
    relationships: list[Relationship] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for event in events:
        if event.event is EventType.ITEM_CREATED:
            if event.item_id in state:
                raise LedgerError(
                    "projection_conflict",
                    f"item {event.item_id!r} created twice (event {event.event_id})",
                )
            try:
                record = LedgerItem.from_dict(event.item or {})
            except ValueError as exc:
                raise LedgerError("unsupported_schema", str(exc))
            mutable = _MutableItem(
                record=record,
                status=LifecycleStatus.ACTIVE,
                verification=VerificationState.UNVERIFIED,
                created_at=event.recorded_at,
                updated_at=event.recorded_at,
                statement_digest=_digest_statement(record.statement),
            )
            mutable.history.append(
                HistoryStep(
                    event_id=event.event_id,
                    from_status=None,
                    to_status=LifecycleStatus.ACTIVE.value,
                    recorded_at=event.recorded_at,
                    note="created",
                )
            )
            state[event.item_id] = mutable
            continue

        mutable = state.get(event.item_id)
        if mutable is None:
            raise LedgerError(
                "unknown_item",
                f"event {event.event_id} references unknown item {event.item_id!r}",
            )

        if event.event is EventType.BLOCKED:
            _set_status(mutable, event, LifecycleStatus.BLOCKED, event.reason or "blocked")
        elif event.event is EventType.UNBLOCKED:
            unmet = [dep for dep in mutable.depends_on if not _dependency_met(state, dep)]
            if unmet:
                raise LedgerError(
                    "dependency_unmet",
                    f"{event.item_id}: cannot unblock while {','.join(unmet)} unmet "
                    f"(event {event.event_id})",
                )
            _set_status(mutable, event, LifecycleStatus.ACTIVE, event.reason or "unblocked")
        elif event.event in (
            EventType.SATISFIED,
            EventType.FAILED,
            EventType.CANCELLED,
            EventType.EXPIRED,
        ):
            target = {
                EventType.SATISFIED: LifecycleStatus.SATISFIED,
                EventType.FAILED: LifecycleStatus.FAILED,
                EventType.CANCELLED: LifecycleStatus.CANCELLED,
                EventType.EXPIRED: LifecycleStatus.EXPIRED,
            }[event.event]
            _set_status(mutable, event, target, event.reason or event.event.value)
            if event.event is EventType.SATISFIED:
                _reevaluate_dependents(state, event, event.item_id)
        elif event.event is EventType.VERIFIED:
            if mutable.verification is VerificationState.CONTRADICTED:
                raise LedgerError(
                    "verification_conflict",
                    f"{event.item_id}: contradicted state cannot become verified "
                    f"(event {event.event_id})",
                )
            if mutable.status in TERMINAL_STATUSES and mutable.status is not (
                LifecycleStatus.SATISFIED
            ):
                raise LedgerError(
                    "invalid_transition",
                    f"{event.item_id}: terminal state {mutable.status.value} cannot be "
                    f"verified (event {event.event_id})",
                )
            if event.evidence is None:
                raise LedgerError(
                    "unsupported_schema",
                    f"verified event {event.event_id} requires evidence",
                )
            record_evidence = dict(event.evidence)
            record_evidence["event_id"] = event.event_id
            record_evidence["outcome"] = event.outcome
            if event.outcome == "failed":
                mutable.evidence.append(record_evidence)
                mutable.contradicted_by = record_evidence.get("ref")
                _set_status(
                    mutable,
                    event,
                    LifecycleStatus.CONTRADICTED,
                    f"verification_failed: {record_evidence.get('kind')}:"
                    f"{record_evidence.get('ref')}",
                )
                mutable.verification = VerificationState.CONTRADICTED
            else:
                mutable.evidence.append(record_evidence)
                mutable.verification = VerificationState.VERIFIED
                mutable.history.append(
                    HistoryStep(
                        event_id=event.event_id,
                        from_status=mutable.status.value,
                        to_status=mutable.status.value,
                        recorded_at=event.recorded_at,
                        note=f"verified: {record_evidence.get('kind')}:"
                        f"{record_evidence.get('ref')}",
                    )
                )
                mutable.updated_at = event.recorded_at
                _reevaluate_dependents(state, event, event.item_id)
        elif event.event is EventType.CONTRADICTED:
            if event.contradicted_by not in state:
                raise LedgerError(
                    "broken_reference",
                    f"event {event.event_id} names unknown item {event.contradicted_by!r}",
                )
            if event.evidence is not None:
                record_evidence = dict(event.evidence)
                record_evidence["event_id"] = event.event_id
                mutable.evidence.append(record_evidence)
            mutable.contradicted_by = event.contradicted_by
            _set_status(
                mutable, event, LifecycleStatus.CONTRADICTED, event.reason or "contradicted"
            )
            mutable.verification = VerificationState.CONTRADICTED
        elif event.event is EventType.SUPERSEDED:
            if event.superseded_by not in state:
                raise LedgerError(
                    "broken_reference",
                    f"event {event.event_id} names unknown item {event.superseded_by!r}",
                )
            mutable.superseded_by = event.superseded_by
            _set_status(mutable, event, LifecycleStatus.SUPERSEDED, event.reason or "superseded")
        elif event.event is EventType.RELATIONSHIP_ADDED:
            relationship = Relationship.from_dict(event.relationship or {})
            if relationship.source_id not in state or relationship.target_id not in state:
                raise LedgerError(
                    "broken_reference",
                    f"event {event.event_id} references unknown item in "
                    f"{relationship.source_id!r} -> {relationship.target_id!r}",
                )
            if event.item_id != relationship.source_id:
                raise LedgerError(
                    "projection_conflict",
                    f"event {event.event_id} subject {event.item_id!r} is not the "
                    f"relationship source {relationship.source_id!r}",
                )
            edge = (
                relationship.type.value,
                relationship.source_id,
                relationship.target_id,
            )
            if edge in seen_edges:
                raise LedgerError(
                    "projection_conflict",
                    f"duplicate relationship {edge} (event {event.event_id})",
                )
            seen_edges.add(edge)
            relationships.append(relationship)
            _apply_relationship(state, event, relationship)
            if relationship.type.value == "depends_on":
                dependent = state[relationship.source_id]
                if dependent.status is LifecycleStatus.ACTIVE and not _dependency_met(
                    state, relationship.target_id
                ):
                    dependent.history.append(
                        HistoryStep(
                            event_id=event.event_id,
                            from_status=dependent.status.value,
                            to_status=LifecycleStatus.BLOCKED.value,
                            recorded_at=event.recorded_at,
                            note=f"dependency_unmet: {relationship.target_id}",
                        )
                    )
                    dependent.status = LifecycleStatus.BLOCKED
                    dependent.updated_at = event.recorded_at
        else:  # pragma: no cover - EventType is closed; from_dict rejects the rest
            raise LedgerError("unsupported_schema", f"unknown event: {event.event.value}")

    frozen = tuple(
        ProjectedItem(
            item=m.record,
            status=m.status,
            verification=m.verification,
            created_at=m.created_at,
            updated_at=m.updated_at,
            statement_digest=m.statement_digest,
            superseded_by=m.superseded_by,
            contradicted_by=m.contradicted_by,
            evidence=tuple(m.evidence),
            depends_on=tuple(m.depends_on),
            history=tuple(m.history),
        )
        for _, m in sorted(state.items())
    )
    return LedgerState(
        items=frozen,
        relationships=tuple(relationships),
        event_ids=tuple(event.event_id for event in events),
    )


def _apply_relationship(
    state: dict[str, _MutableItem], event: LedgerEvent, relationship: Relationship
) -> None:
    from project_context.ledger.relationships import RelationshipType

    if relationship.type is RelationshipType.DEPENDS_ON:
        dependent = state[relationship.source_id]
        if relationship.target_id not in dependent.depends_on:
            dependent.depends_on.append(relationship.target_id)
    elif relationship.type is RelationshipType.SUPERSEDES:
        old = state[relationship.target_id]
        old.superseded_by = relationship.source_id
        _set_status(
            old,
            event,
            LifecycleStatus.SUPERSEDED,
            f"superseded_by {relationship.source_id}",
        )
    elif relationship.type is RelationshipType.CONTRADICTS:
        target = state[relationship.target_id]
        target.contradicted_by = relationship.source_id
        _set_status(
            target,
            event,
            LifecycleStatus.CONTRADICTED,
            f"contradicted_by {relationship.source_id}",
        )
        target.verification = VerificationState.CONTRADICTED
    # blocks / verifies / derived_from are recorded lineage in Stage 6A;
    # they change no lifecycle state.
