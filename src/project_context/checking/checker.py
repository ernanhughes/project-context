"""Independent outcome checker.

Judges an outcome from three things only: the task's hidden truth, the reader's
parsed action, and which items were admitted (and in what role). It does not read:

  * any explanation the reader gave, or its claim to have followed a rule;
  * the assembly policy's own verdict about its bundle;
  * the resolver, or any module that could share a defect with the mechanism.

That separation is enforced by `tests/test_independence.py`. A defect in the
mechanism under test therefore cannot silently reappear in the verdict.

All rules are deterministic comparisons against truth.
"""

from __future__ import annotations

from dataclasses import dataclass

from project_context.domain.failure import FailureEvidence, FailureState, attribute
from project_context.generation.model import HiddenTruth


@dataclass(frozen=True)
class AdmittedItem:
    item_id: str
    role: str  # "control" or "data"


@dataclass(frozen=True)
class Observation:
    """What happened. `action` is None when the reply did not parse."""

    action: str | None
    value: str | None
    admitted: tuple[AdmittedItem, ...] = ()
    target: str | None = None


@dataclass(frozen=True)
class CheckResult:
    parsed: bool
    task_success: bool
    forbidden_action: bool
    constraint_violations: tuple[str, ...]
    stale_item_used: bool
    wrong_scope_used: bool
    conflicting_influence: bool
    required_evidence_admitted: bool
    required_evidence_used: bool | None  # None when the task has no decisive value
    unsupported_value: bool
    conflict_preserved: bool | None  # None when no conflict was expected
    bundle_violations: tuple[str, ...]
    failure_state: FailureState | None


def _matches(actual: tuple[str | None, str | None], wanted: tuple[str, str | None]) -> bool:
    """A wanted value of None matches any value."""
    return actual[0] == wanted[0] and (wanted[1] is None or actual[1] == wanted[1])


def bundle_violations(truth: HiddenTruth, admitted: tuple[AdmittedItem, ...]) -> tuple[str, ...]:
    """Judge a bundle against truth, before any reader is involved."""
    rows = {t.item_id: t for t in truth.item_truth}
    found: list[str] = []
    for item in admitted:
        row = rows.get(item.item_id)
        if row is None:
            found.append(f"unknown_item:{item.item_id}")
        elif row.status == "UNKNOWN":
            found.append(f"unknown_admitted:{row.reason_class}")
        elif row.role == "excluded":
            found.append(f"admitted_excluded:{row.reason_class}")
        elif row.role == "data" and item.role == "control":
            found.append(f"data_admitted_as_control:{row.reason_class}")
    return tuple(found)


def check(
    truth: HiddenTruth,
    observation: Observation,
    *,
    control_valid: bool | None = True,
    required_survived: bool | None = None,
    degraded_vs_baseline: bool | None = None,
) -> CheckResult:
    parsed = observation.action is not None
    actual = (observation.action, observation.value)
    admitted_ids = {a.item_id for a in observation.admitted}

    success = parsed and any(_matches(actual, (n, v)) for n, v in truth.valid_actions)
    forbidden = parsed and any(_matches(actual, f) for f in truth.forbidden_actions)
    violations = truth.constraints if forbidden else ()

    def followed(*kinds: str) -> bool:
        return parsed and any(
            t.trap_kind in kinds and _matches(actual, t.implied_action) for t in truth.traps
        )

    stale = followed("stale", "near_miss")
    wrong_scope = followed("wrong_scope")
    conflicting = followed("conflicting", "injection", "unverified")

    critical_admitted = all(c in admitted_ids for c in truth.critical_evidence)

    used: bool | None
    if truth.decisive_value is None:
        used = None
    else:
        used = (
            parsed
            and observation.action == "SET_VALUE"
            and observation.value == truth.decisive_value
        )

    # A value in the answer that no item supports is a claim the bundle cannot back.
    unsupported = False
    if parsed and observation.action == "SET_VALUE" and observation.value is not None:
        unsupported = (
            not any(t.implied_action[1] == observation.value for t in truth.traps)
            and observation.value != truth.decisive_value
        )

    preserved: bool | None = None
    if truth.expected_conflict == "unresolved":
        preserved = parsed and observation.action == "ABSTAIN"

    problems = bundle_violations(truth, observation.admitted)

    state: FailureState | None = None
    if not success:
        state = attribute(
            FailureEvidence(
                control_valid=control_valid,
                required_admitted=critical_admitted if truth.critical_evidence else None,
                required_survived=required_survived,
                source_current=False if stale else None,
                in_scope=False if wrong_scope else None,
                no_conflicting_influence=False if conflicting else None,
                evidence_used=used,
                applied_correctly=False if used is not False else None,
                degraded_vs_baseline=degraded_vs_baseline,
            )
        )
    return CheckResult(
        parsed=parsed,
        task_success=success,
        forbidden_action=forbidden,
        constraint_violations=violations,
        stale_item_used=stale,
        wrong_scope_used=wrong_scope,
        conflicting_influence=conflicting,
        required_evidence_admitted=critical_admitted,
        required_evidence_used=used,
        unsupported_value=unsupported,
        conflict_preserved=preserved,
        bundle_violations=problems,
        failure_state=state,
    )


def compare_conflicts(truth: HiddenTruth, conflicts: list[tuple[str, str]]) -> tuple[str, ...]:
    """Compare conflict records, given as (kind, status) tuples, with truth.

    An unresolved conflict leaves every item's verdict looking ordinary, so verdicts
    alone cannot tell a mechanism that preserved the disagreement from one that never
    noticed it. `expected_conflict` covers whichever kind the task is about.
    """
    statuses = [status for _kind, status in conflicts]
    expected = {"none": [], "resolved": ["RESOLVED"], "unresolved": ["UNRESOLVED"]}[
        truth.expected_conflict
    ]
    if statuses == expected:
        return ()
    return (f"conflict: expected {expected or 'none'}, got {statuses or 'none'}",)


def compare_verdicts(truth: HiddenTruth, verdicts: list[tuple[str, str, str]]) -> tuple[str, ...]:
    """Compare eligibility verdicts, given as (item_id, status, role) tuples, with truth.

    Takes plain tuples so this module never depends on the resolver that produced them.
    Returns one description per disagreement; empty means the verdicts match truth.
    """
    rows = {t.item_id: t for t in truth.item_truth}
    out: list[str] = []
    seen = set()
    for item_id, status, role in verdicts:
        seen.add(item_id)
        row = rows.get(item_id)
        if row is None:
            out.append(f"{item_id}: not in truth")
        elif (row.status, row.role) != (status, role):
            out.append(
                f"{item_id}: expected {row.status}/{row.role} ({row.reason_class}), "
                f"got {status}/{role}"
            )
    for missing in sorted(set(rows) - seen):
        out.append(f"{missing}: no verdict")
    return tuple(out)
