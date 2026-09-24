"""Candidate metadata, policy and verdict types for eligibility derivation.

Three separate things, kept apart on purpose:

    candidate metadata  ->  eligibility derivation  ->  assembly policy

This module holds the first and the shapes of the second. It knows nothing about
hidden truth, generators, checkers or assembly. (`tests/test_independence.py`
pins that.)

A note on `directs`: a directive item states an instruction as structure, for
example ("forbid", "edit_generated"). Turning prose into that structure is the job
of a source adapter and is the boundary where real systems need judgement; the
resolver only reasons over the structure it is given. Where the structure is
absent the resolver says UNKNOWN, it does not guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"  # metadata needed for the decision is missing


class Role(str, Enum):
    CONTROL = "control"  # may direct behaviour
    DATA = "data"  # may inform, never direct
    EXCLUDED = "excluded"  # must not be admitted


class ConflictStatus(str, Enum):
    RESOLVED = "RESOLVED"  # policy names a winner
    UNRESOLVED = "UNRESOLVED"  # policy is silent: preserve, do not pick


@dataclass(frozen=True)
class CandidateMetadata:
    item_id: str
    channel: str  # system, project, user, delegated, tool_output, quoted, declared, document
    source_id: str
    scope: str | None  # None = not recorded (never means "global")
    version: int | None = None  # source version, not a timestamp
    revision: str | None = None  # source revision, for delegation checks
    claim_key: str | None = None  # what factual claim the item makes
    claim_value: str | None = None
    directs: tuple[str, str] | None = None  # ("do" | "forbid", action)
    # Order in which the item was captured. Recorded because a naive policy might trust
    # it; the resolver never does.
    observed_at: int | None = None


@dataclass(frozen=True)
class Policy:
    """Declared policy. The resolver applies it; it does not invent it."""

    active_scope: str
    # Channels that may direct behaviour, highest authority first.
    authority_order: tuple[str, ...] = ("system", "project", "user")
    # Scopes that legitimately serve every world (shared dependencies).
    shared_scopes: tuple[str, ...] = ()
    # Source id -> the revision that was vetted for delegated authority.
    vetted_revisions: tuple[tuple[str, str], ...] = ()
    # Claim key -> source id that is canonical for it. Absent means policy is silent.
    canonical_sources: tuple[tuple[str, str], ...] = ()
    # None = the current state; otherwise the version the question is about.
    as_of_version: int | None = None


@dataclass(frozen=True)
class Verdict:
    item_id: str
    status: Status
    role: Role
    reason: str  # short machine code, always derived from metadata
    conflict_group: str | None = None


@dataclass(frozen=True)
class Conflict:
    group: str
    kind: str  # "instruction" or "factual"
    members: tuple[str, ...]
    status: ConflictStatus
    winner: str | None = None


@dataclass(frozen=True)
class Resolution:
    verdicts: tuple[Verdict, ...]
    conflicts: tuple[Conflict, ...] = ()

    def verdict_for(self, item_id: str) -> Verdict:
        for verdict in self.verdicts:
            if verdict.item_id == item_id:
                return verdict
        raise KeyError(item_id)

    def admitted_ids(self) -> tuple[str, ...]:
        """Items the resolver allows into a bundle, in candidate order."""
        return tuple(v.item_id for v in self.verdicts if v.role is not Role.EXCLUDED)
