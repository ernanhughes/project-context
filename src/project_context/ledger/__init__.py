"""Context Ledger (Stage 6A): typed durable state for future context decisions.

The ledger records potentially future-relevant state produced during AI
work — obligations, constraints, decisions, assumptions, failures,
dependencies, pending verification, results — as an append-only event
stream with deterministic projection to current state.

Boundary (pinned by tests):

- persistence is not admission; nothing here decides model context;
- no retrieval, activation, compiler policy, or OpenCode mutation;
- no model calls, no network, no wall-clock reads in projection;
- production ledger modules never import evaluation code or fixture
  truth, and fixture truth files are read only by tests.
"""

from project_context.ledger.events import LedgerError, LedgerEvent
from project_context.ledger.projection import LedgerState, ProjectedItem, explain, project
from project_context.ledger.records import (
    Authority,
    ItemKind,
    LedgerScope,
    LifecycleStatus,
    SourceProvenance,
    VerificationState,
)
from project_context.ledger.relationships import Relationship, RelationshipType
from project_context.ledger.store import append_event, load_events

__all__ = [
    "Authority",
    "ItemKind",
    "LedgerError",
    "LedgerEvent",
    "LedgerScope",
    "LedgerState",
    "LifecycleStatus",
    "ProjectedItem",
    "Relationship",
    "RelationshipType",
    "SourceProvenance",
    "VerificationState",
    "append_event",
    "explain",
    "load_events",
    "project",
]
