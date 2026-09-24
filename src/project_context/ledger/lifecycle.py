"""Ledger lifecycle: explicit deterministic status transitions.

Terminal states never silently return to active. Reopening is modelled
as a new item and a new event, never as a mutation of history.
"""

from project_context.ledger.records import LifecycleStatus as S

TRANSITIONS: dict[S, frozenset[S]] = {
    S.ACTIVE: frozenset(
        {
            S.BLOCKED,
            S.SATISFIED,
            S.FAILED,
            S.SUPERSEDED,
            S.CANCELLED,
            S.EXPIRED,
            S.CONTRADICTED,
        }
    ),
    S.BLOCKED: frozenset(
        {
            S.ACTIVE,
            S.SATISFIED,
            S.FAILED,
            S.SUPERSEDED,
            S.CANCELLED,
            S.EXPIRED,
            S.CONTRADICTED,
        }
    ),
    S.SATISFIED: frozenset(),
    S.FAILED: frozenset(),
    S.SUPERSEDED: frozenset(),
    S.CANCELLED: frozenset(),
    S.EXPIRED: frozenset(),
    S.CONTRADICTED: frozenset(),
}


def is_legal(from_status: S, to_status: S) -> bool:
    """Whether a direct transition is allowed."""
    return to_status in TRANSITIONS.get(from_status, frozenset())


def legal_targets(from_status: S) -> tuple[S, ...]:
    """Deterministic listing of legal targets (enum order)."""
    return tuple(s for s in S if s in TRANSITIONS.get(from_status, frozenset()))
