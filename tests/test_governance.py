"""Eligibility resolver: does deriving verdicts from visible metadata reproduce truth?

The truth is written by the generator by construction. The resolver never sees it,
and the comparison is made by the independent checker.
"""

from project_context.checking.checker import compare_conflicts, compare_verdicts
from project_context.generation.generator import FAMILIES, generate_task
from project_context.governance.heuristics import heuristic_resolve
from project_context.governance.model import (
    CandidateMetadata,
    ConflictStatus,
    Policy,
    Role,
    Status,
)
from project_context.governance.resolver import derive_flags, resolve
from tests.test_generation import OPTION_GRID, SEEDS


def as_tuples(resolution):
    return [(v.item_id, v.status.value, v.role.value) for v in resolution.verdicts]


def disagreements(truth, resolution):
    conflicts = [(c.kind, c.status.value) for c in resolution.conflicts]
    return compare_verdicts(truth, as_tuples(resolution)) + compare_conflicts(truth, conflicts)


def adversarial_cases():
    for family in ("authority", "scope", "freshness", "provenance"):
        for options in OPTION_GRID[family]:
            if options.get("control"):
                continue
            for seed in SEEDS:
                yield family, seed, options


def test_resolver_reproduces_truth_on_every_generated_task():
    checked = 0
    for family in FAMILIES:
        for options in OPTION_GRID[family]:
            for seed in SEEDS:
                task = generate_task(family, seed, **options)
                view = task.visible()
                resolution = resolve(view.candidates(), view.policy)
                diff = disagreements(task.truth, resolution)
                assert diff == (), (family, seed, options, diff)
                checked += 1
    assert checked == 40 * sum(len(v) for v in OPTION_GRID.values())


def test_unresolved_provenance_is_preserved_not_resolved():
    for seed in SEEDS:
        for mode in ("silent", "equal"):
            view = generate_task("provenance", seed, policy=mode).visible()
            resolution = resolve(view.candidates(), view.policy)
            factual = [c for c in resolution.conflicts if c.kind == "factual"]
            assert len(factual) == 1
            assert factual[0].status is ConflictStatus.UNRESOLVED and factual[0].winner is None
            assert all(v.role is Role.DATA for v in resolution.verdicts)


def test_a_canonical_source_resolves_the_conflict_by_policy():
    for seed in SEEDS:
        view = generate_task("provenance", seed, policy="canonical").visible()
        conflict = next(
            c for c in resolve(view.candidates(), view.policy).conflicts if c.kind == "factual"
        )
        assert conflict.status is ConflictStatus.RESOLVED and conflict.winner is not None


def test_unknown_metadata_is_never_defaulted():
    policy = Policy(active_scope="proj:a")
    items = [
        CandidateMetadata("x1", "document", "s", scope=None),
        CandidateMetadata(
            "x2", "delegated", "runbook", scope="proj:a", revision=None, directs=("do", "z")
        ),
        CandidateMetadata(
            "x3", "document", "s", scope="proj:a", claim_key="k", claim_value="1", version=None
        ),
        CandidateMetadata(
            "x4", "document", "s", scope="proj:a", claim_key="k", claim_value="2", version=3
        ),
    ]
    by_id = {v.item_id: v for v in resolve(items, policy).verdicts}
    assert by_id["x1"].status is Status.UNKNOWN and by_id["x1"].reason == "scope_missing"
    assert by_id["x2"].status is Status.UNKNOWN and by_id["x2"].reason == "delegation_unverifiable"
    assert by_id["x3"].status is Status.UNKNOWN and by_id["x3"].reason == "version_missing"
    assert by_id["x4"].status is Status.ELIGIBLE
    assert all(v.role is not Role.CONTROL for v in by_id.values())


def test_self_declared_authority_and_capture_order_confer_nothing():
    policy = Policy(active_scope="proj:a")
    items = [
        CandidateMetadata("rule", "project", "rules", scope="proj:a", directs=("forbid", "act")),
        CandidateMetadata(
            "boast", "declared", "doc", scope="proj:a", directs=("do", "act"), observed_at=99
        ),
    ]
    by_id = {v.item_id: v for v in resolve(items, policy).verdicts}
    assert by_id["boast"].role is Role.DATA and by_id["boast"].reason == "no_instruction_authority"
    assert by_id["rule"].role is Role.CONTROL


def test_equal_authority_directives_are_left_unresolved():
    policy = Policy(active_scope="proj:a")
    items = [
        CandidateMetadata("p1", "project", "rules-1", scope="proj:a", directs=("do", "act")),
        CandidateMetadata("p2", "project", "rules-2", scope="proj:a", directs=("forbid", "act")),
    ]
    resolution = resolve(items, policy)
    (conflict,) = resolution.conflicts
    assert conflict.kind == "instruction" and conflict.status is ConflictStatus.UNRESOLVED


def test_derive_flags_marks_the_reason_class_that_failed():
    view = generate_task("scope", 3).visible()
    flags = derive_flags(view.candidates(), view.policy)
    rejected = [f for f in flags.values() if not f["scope_eligible"]]
    assert rejected and all(f["freshness_eligible"] and f["authority_eligible"] for f in rejected)


def test_naive_shortcuts_fail_where_the_fixture_is_meant_to_expose_them():
    """Fixture validity, per configuration.

    A configuration on which the shortcut does well teaches nothing about the mechanism,
    so each adversarial configuration must defeat the shortcut on nearly every seed. The
    one configuration where capture order happens to agree with version order is a known
    exception, and is asserted to be one: it must not be used to claim the mechanism matters.
    """
    naive_passes_by_design = {("freshness", ())}
    groups: dict[tuple, list[bool]] = {}
    for family, seed, options in adversarial_cases():
        task = generate_task(family, seed, **options)
        view = task.visible()
        naive = heuristic_resolve(view.candidates(), view.policy)
        failed = bool(disagreements(task.truth, naive))
        groups.setdefault((family, tuple(sorted(options.items()))), []).append(failed)
    for (family, options), hits in groups.items():
        rate = sum(hits) / len(hits)
        if (family, options) in naive_passes_by_design:
            assert rate <= 0.1, (family, options, rate)
        else:
            assert rate >= 0.9, (family, options, rate)
