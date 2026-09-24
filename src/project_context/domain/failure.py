"""Shared failure taxonomy for evidence runs (specs/failure-taxonomy.md).

Every failed or degraded outcome in an evidence run is attributed to exactly
one primary state by walking an ordered ladder over recorded facts. The ladder
answers "at which stage did the information stop doing its job?", so a failure
is never reported as just "wrong answer".

The functions here decide from booleans that the run's own deterministic
checks produced. They never look at a model's account of why it failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FailureState(str, Enum):
    CONTROL_FAILURE = "CONTROL_FAILURE"  # the experiment itself is confounded or invalid
    ABSENT = "ABSENT"  # information was never admitted
    LOST = "LOST"  # entered, but a transformation destroyed it
    STALE = "STALE"  # once valid, no longer current
    SCOPE_LEAK = "SCOPE_LEAK"  # wrong project, task or world affected behaviour
    OVERRIDDEN = "OVERRIDDEN"  # a conflicting or higher-authority item changed behaviour
    UNRECOVERED = "UNRECOVERED"  # survived, but the reader did not locate or use it
    MISAPPLIED = "MISAPPLIED"  # recovered, but used incorrectly
    INTERFERENCE = "INTERFERENCE"  # extra context degraded otherwise viable behaviour


# Order in which attribution is attempted. Earlier states explain more than
# later ones: if information was never admitted, nothing downstream matters.
ATTRIBUTION_ORDER: tuple[FailureState, ...] = (
    FailureState.CONTROL_FAILURE,
    FailureState.ABSENT,
    FailureState.LOST,
    FailureState.STALE,
    FailureState.SCOPE_LEAK,
    FailureState.OVERRIDDEN,
    FailureState.UNRECOVERED,
    FailureState.MISAPPLIED,
    FailureState.INTERFERENCE,
)


@dataclass(frozen=True)
class FailureEvidence:
    """Deterministic facts about one failed or degraded case.

    `None` means the run did not establish the fact; an unestablished fact
    never triggers a state (unavailable is not false).
    """

    # matched conditions, verified bundle digests, and a grader that ran
    control_valid: bool | None = True
    # the required information was in the admitted set
    required_admitted: bool | None = True
    # and survived any transformation, exactly where exactness is required
    required_survived: bool | None = True
    # the admitted claim still described the current state
    source_current: bool | None = True
    # everything admitted belonged to the active world
    in_scope: bool | None = True
    # no conflicting or higher-authority item drove the action
    no_conflicting_influence: bool | None = True
    # the action shows the required information was located and used
    evidence_used: bool | None = True
    # and used correctly
    applied_correctly: bool | None = True
    # worse than the same reader given the minimal bundle
    degraded_vs_baseline: bool | None = False


def attribute(evidence: FailureEvidence) -> FailureState | None:
    """Return the primary failure state, or None when no state applies.

    Only an explicit False (or, for `degraded_vs_baseline`, an explicit True)
    triggers a state.
    """
    if evidence.control_valid is False:
        return FailureState.CONTROL_FAILURE
    if evidence.required_admitted is False:
        return FailureState.ABSENT
    if evidence.required_survived is False:
        return FailureState.LOST
    if evidence.source_current is False:
        return FailureState.STALE
    if evidence.in_scope is False:
        return FailureState.SCOPE_LEAK
    if evidence.no_conflicting_influence is False:
        return FailureState.OVERRIDDEN
    if evidence.evidence_used is False:
        return FailureState.UNRECOVERED
    if evidence.applied_correctly is False:
        return FailureState.MISAPPLIED
    if evidence.degraded_vs_baseline is True:
        return FailureState.INTERFERENCE
    return None
