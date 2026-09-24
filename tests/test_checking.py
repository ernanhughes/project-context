"""Independent checker: judgements against hidden truth, without the mechanism."""

from project_context.checking.checker import (
    AdmittedItem,
    Observation,
    bundle_violations,
    check,
    compare_conflicts,
    compare_verdicts,
)
from project_context.domain.failure import FailureState
from project_context.generation.generator import FAMILIES, generate_task

SEEDS = range(25)


def perfect(task) -> Observation:
    """An observation that does the right thing, admitting exactly the truthful bundle."""
    admitted = tuple(
        AdmittedItem(t.item_id, "control" if t.role == "control" else "data")
        for t in task.truth.item_truth
        if t.role != "excluded" and t.status == "ELIGIBLE"
    )
    action, value = task.truth.valid_actions[0]
    return Observation(action, value, admitted)


def test_a_correct_action_with_a_truthful_bundle_passes_everywhere():
    for family in FAMILIES:
        for seed in SEEDS:
            task = generate_task(family, seed)
            result = check(task.truth, perfect(task))
            assert result.task_success and not result.forbidden_action, (family, seed)
            assert result.bundle_violations == ()
            assert result.failure_state is None
            assert not (result.stale_item_used or result.wrong_scope_used)
            assert not result.conflicting_influence


def test_following_each_trap_is_named_as_that_kind_of_failure():
    kinds = {
        "authority": "conflicting_influence",
        "scope": "wrong_scope_used",
        "freshness": "stale_item_used",
        "provenance": "conflicting_influence",
    }
    for family, flag in kinds.items():
        for seed in SEEDS:
            task = generate_task(family, seed)
            trap = task.truth.traps[0]
            action, value = trap.implied_action
            result = check(task.truth, Observation(action, value, perfect(task).admitted))
            assert not result.task_success, (family, seed)
            assert result.forbidden_action, (family, seed)
            assert getattr(result, flag), (family, seed, flag)
            assert result.constraint_violations == task.truth.constraints


def test_an_unparseable_reply_is_a_failure_not_a_pass_or_a_violation():
    task = generate_task("scope", 1)
    result = check(task.truth, Observation(None, None))
    assert not result.parsed and not result.task_success
    assert not result.forbidden_action and result.constraint_violations == ()


def test_the_checker_ignores_everything_but_action_value_and_admission():
    """There is nowhere to put an explanation or a self-verdict, by construction."""
    task = generate_task("freshness", 2)
    fields = set(Observation.__dataclass_fields__)
    assert fields == {"action", "value", "admitted", "target"}
    trap = task.truth.traps[0].implied_action
    assert not check(task.truth, Observation(*trap)).task_success


def test_a_value_no_item_supports_is_flagged_unsupported():
    task = generate_task("evidence", 4, n_distractors=3)
    result = check(task.truth, Observation("SET_VALUE", "definitely-not-a-value"))
    assert result.unsupported_value and not result.task_success
    assert not check(task.truth, perfect(task)).unsupported_value


def test_missing_required_evidence_is_absent_before_it_is_misused():
    task = generate_task("evidence", 4, n_distractors=3)
    action, value = "SET_VALUE", "0"
    result = check(task.truth, Observation(action, value, ()))
    assert not result.required_evidence_admitted
    assert result.failure_state is FailureState.ABSENT


def test_unresolved_provenance_is_preserved_only_by_abstaining():
    for seed in SEEDS:
        task = generate_task("provenance", seed, policy="silent")
        assert check(task.truth, Observation("ABSTAIN", None)).conflict_preserved is True
        pick = check(task.truth, Observation("SET_VALUE", task.truth.traps[0].implied_action[1]))
        assert pick.conflict_preserved is False and pick.forbidden_action


def test_bundle_violations_name_the_class_of_error():
    task = generate_task("scope", 3)
    truth_rows = {t.item_id: t for t in task.truth.item_truth}
    excluded = next(i for i, t in truth_rows.items() if t.role == "excluded")
    problems = bundle_violations(task.truth, (AdmittedItem(excluded, "data"),))
    assert problems == (f"admitted_excluded:{truth_rows[excluded].reason_class}",)
    authority = generate_task("authority", 3)
    data_row = next(t for t in authority.truth.item_truth if t.role == "data")
    assert bundle_violations(authority.truth, (AdmittedItem(data_row.item_id, "control"),)) == (
        f"data_admitted_as_control:{data_row.reason_class}",
    )
    assert bundle_violations(task.truth, (AdmittedItem("i-nope", "data"),)) == (
        "unknown_item:i-nope",
    )


def test_verdict_and_conflict_comparison_report_every_disagreement():
    task = generate_task("provenance", 5, policy="silent")
    right = [(t.item_id, t.status, t.role) for t in task.truth.item_truth]
    assert compare_verdicts(task.truth, right) == ()
    assert compare_verdicts(task.truth, right[:-1])  # a missing verdict is a disagreement
    assert compare_verdicts(task.truth, [(i, "INELIGIBLE", "excluded") for i, _, _ in right])
    assert compare_conflicts(task.truth, [("factual", "UNRESOLVED")]) == ()
    assert compare_conflicts(task.truth, []) != ()
    assert compare_conflicts(task.truth, [("factual", "RESOLVED")]) != ()
