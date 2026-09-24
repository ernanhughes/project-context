"""Ledger records: one durable state item plus its scope and provenance.

Conventions follow the Stage 0 domain records: frozen dataclasses,
stable schema IDs, JSON round-trips, strict loaders that reject unknown
keys. Fixture items use authored stable IDs; live items use UUIDs.
Neither is ever derived from secret or private content.

Authority vocabulary maps to the governance channels in
`project_context.governance.model` rather than duplicating them:

    ledger USER    -> governance channel "user"
    ledger SYSTEM  -> "system"
    ledger PROJECT -> "project"
    ledger TOOL    -> "tool_output" (tool observation; data, never directive)
    ledger AGENT   -> "declared" (agent-authored; must earn admission)
    ledger DERIVED -> "declared" (ledger-derived; must earn admission)

Lifecycle status and verification state are separate dimensions: an
obligation can be lifecycle-active while verification-unverified, and a
result can be lifecycle-active only after verification-verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

LEDGER_ITEM_SCHEMA = "project_context.ledger_item.v1"


class ItemKind(str, Enum):
    OBLIGATION = "obligation"
    CONSTRAINT = "constraint"
    DECISION = "decision"
    ASSUMPTION = "assumption"
    UNRESOLVED_FAILURE = "unresolved_failure"
    DEPENDENCY = "dependency"
    PENDING_VERIFICATION = "pending_verification"
    RESULT = "result"


class LifecycleStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    SATISFIED = "satisfied"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    CONTRADICTED = "contradicted"


class Authority(str, Enum):
    USER = "user"
    SYSTEM = "system"
    PROJECT = "project"
    TOOL = "tool"
    AGENT = "agent"
    DERIVED = "derived"


class VerificationState(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"


TERMINAL_STATUSES = frozenset(
    {
        LifecycleStatus.SATISFIED,
        LifecycleStatus.FAILED,
        LifecycleStatus.SUPERSEDED,
        LifecycleStatus.CANCELLED,
        LifecycleStatus.EXPIRED,
        LifecycleStatus.CONTRADICTED,
    }
)


@dataclass(frozen=True)
class LedgerScope:
    """Where a ledger item may later be relevant. All fields optional;
    nothing is inferred. Stage 6A records scope; activation (Stage 6B)
    will use it."""

    repo: str | None = None
    workspace: str | None = None
    branch: str | None = None
    paths: tuple[str, ...] = ()
    component: str | None = None
    task: str | None = None
    session: str | None = None
    agent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "workspace": self.workspace,
            "branch": self.branch,
            "paths": list(self.paths),
            "component": self.component,
            "task": self.task,
            "session": self.session,
            "agent": self.agent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LedgerScope":
        if not isinstance(data, dict):
            raise ValueError(f"invalid ledger scope: {data!r}")
        unknown = set(data) - {
            "repo",
            "workspace",
            "branch",
            "paths",
            "component",
            "task",
            "session",
            "agent",
        }
        if unknown:
            raise ValueError(f"unknown ledger scope keys: {sorted(unknown)}")
        return cls(
            repo=data.get("repo"),
            workspace=data.get("workspace"),
            branch=data.get("branch"),
            paths=tuple(data.get("paths", [])),
            component=data.get("component"),
            task=data.get("task"),
            session=data.get("session"),
            agent=data.get("agent"),
        )


@dataclass(frozen=True)
class SourceProvenance:
    """Where a ledger item came from. Session/invocation locate the
    origin; they never carry hidden evaluator truth."""

    session: str | None = None
    invocation: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"session": self.session, "invocation": self.invocation, "note": self.note}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceProvenance":
        if not isinstance(data, dict):
            raise ValueError(f"invalid ledger provenance: {data!r}")
        unknown = set(data) - {"session", "invocation", "note"}
        if unknown:
            raise ValueError(f"unknown ledger provenance keys: {sorted(unknown)}")
        return cls(
            session=data.get("session"),
            invocation=data.get("invocation"),
            note=data.get("note"),
        )


@dataclass(frozen=True)
class LedgerItem:
    """The creation-time record for one durable state item. Current
    lifecycle and verification state live in the projection
    (`ProjectedItem`), derived from the event stream; this record is
    what `item_created` carries and never changes afterwards."""

    item_id: str
    kind: ItemKind
    statement: str
    authority: Authority
    scope: LedgerScope
    source: SourceProvenance

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LEDGER_ITEM_SCHEMA,
            "item_id": self.item_id,
            "kind": self.kind.value,
            "statement": self.statement,
            "authority": self.authority.value,
            "scope": self.scope.to_dict(),
            "source": self.source.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LedgerItem":
        version = data.get("schema_version", LEDGER_ITEM_SCHEMA)
        if version != LEDGER_ITEM_SCHEMA:
            raise ValueError(f"unsupported LedgerItem schema: {version!r}")
        unknown = set(data) - {
            "schema_version",
            "item_id",
            "kind",
            "statement",
            "authority",
            "scope",
            "source",
        }
        if unknown:
            raise ValueError(f"unknown LedgerItem keys: {sorted(unknown)}")
        item_id = data["item_id"]
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(f"invalid ledger item id: {item_id!r}")
        return cls(
            item_id=item_id,
            kind=ItemKind(data["kind"]),
            statement=data["statement"],
            authority=Authority(data["authority"]),
            scope=LedgerScope.from_dict(data.get("scope", {})),
            source=SourceProvenance.from_dict(data.get("source", {})),
        )
