"""Future intervention concepts. DOCUMENTED SHELLS ONLY.

The book has earned PruneDecision, CompactionArtifact, and
FidelityRepresentation as future records. Stage 0 records their names,
kinds, and the rule that they do not exist yet as behaviour.

There are deliberately NO functions here named prune, compact, decay,
retrieve, or assemble. If such a function appears in this module, the
Stage 0 architecture is violated; tests enforce this (see
tests/test_invariants.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InterventionKind(str, Enum):
    """Names reserved for later stages. No behaviour attached."""

    PRUNE = "PRUNE"
    COMPACT = "COMPACT"
    DECAY = "DECAY"
    EXTERNALISE = "EXTERNALISE"
    RECALL = "RECALL"
    ASSEMBLE = "ASSEMBLE"


@dataclass(frozen=True)
class InterventionProposal:
    """A proposal record only. Proposing is not applying: Stage 0 has no
    code path that turns a proposal into a changed bundle."""

    kind: InterventionKind
    target_item_ids: tuple[str, ...]
    reason: str
    policy_version: str
    created_at: str
