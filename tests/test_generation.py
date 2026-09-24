"""Task generator: determinism, structure, validity, and the truth boundary."""

import itertools
import json

import pytest

from project_context.generation.generator import FAMILIES, generate_task, validate_task
from project_context.generation.model import VisibleTask

SEEDS = range(40)

OPTION_GRID = {
    "authority": [
        {},
        {"tool_imperative": True, "rhetoric": True, "quoted": True},
        {"delegation": "vetted"},
        {"delegation": "changed"},
        {"control": True},
    ],
    "scope": [{}, {"missing_scope": True}, {"control": True}],
    "freshness": [
        {},
        {"standpoint": "historical"},
        {"variant": "fast_change"},
        {"control": True},
    ],
    "provenance": [{}, {"policy": "silent"}, {"policy": "equal"}, {"control": True}],
    "evidence": [
        {},
        {"n_distractors": 6, "distractor_kind": "plausible"},
        {"n_distractors": 6, "distractor_kind": "near_miss"},
        {"n_distractors": 4, "evidence_position": 0.0},
        {"n_distractors": 4, "evidence_position": 1.0},
    ],
}


def cases():
    for family in FAMILIES:
        for options in OPTION_GRID[family]:
            for seed in SEEDS:
                yield family, seed, options


def test_every_generated_task_is_self_consistent():
    total = 0
    for family, seed, options in cases():
        task = generate_task(family, seed, **options)
        assert validate_task(task) == [], (family, seed, options)
        total += 1
    assert total == 40 * sum(len(v) for v in OPTION_GRID.values())


def test_generation_is_deterministic_and_content_addressed():
    for family in FAMILIES:
        first = generate_task(family, 7)
        second = generate_task(family, 7)
        assert first == second
        assert first.task_id == second.task_id
        assert first.task_id.startswith("t-") and len(first.task_id) == 14
        assert all(i.item_id.startswith("i-") for i in first.items)


def test_different_seeds_and_options_give_different_tasks():
    ids = {generate_task(f, s).task_id for f in FAMILIES for s in SEEDS}
    assert len(ids) == len(FAMILIES) * len(SEEDS)
    a = generate_task("evidence", 3, n_distractors=2)
    b = generate_task("evidence", 3, n_distractors=5)
    assert a.task_id != b.task_id


def test_moving_the_decisive_item_leaves_the_content_identical():
    """The position experiment must move identical content, nothing else."""
    for seed in range(15):
        ids = [
            {
                i.item_id
                for i in generate_task("evidence", seed, n_distractors=6, evidence_position=p).items
            }
            for p in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]
        assert all(group == ids[0] for group in ids)


def test_a_larger_volume_extends_a_smaller_one():
    """The volume sweep adds distractors to an identical base."""
    for kind in ("irrelevant", "plausible", "near_miss"):
        for seed in range(15):
            small = generate_task("evidence", seed, n_distractors=3, distractor_kind=kind)
            large = generate_task("evidence", seed, n_distractors=9, distractor_kind=kind)
            assert {i.item_id for i in small.items} <= {i.item_id for i in large.items}
            assert small.truth.decisive_value == large.truth.decisive_value


def test_visible_view_exposes_no_truth():
    for family, seed, options in itertools.islice(cases(), 0, None, 37):
        task = generate_task(family, seed, **options)
        view = task.visible()
        assert isinstance(view, VisibleTask)
        assert not hasattr(view, "truth")
        blob = json.dumps(view, default=lambda o: getattr(o, "__dict__", str(o)))
        for label in (
            "trap_kind",
            "implied_action",
            "valid_actions",
            "forbidden_actions",
            "critical_evidence",
        ):
            assert label not in blob
        # No item text carries a truth label such as "stale" used as a marker.
        for item in view.items:
            assert "TRAP" not in item.content and "hidden" not in item.content.lower()


def test_critical_evidence_is_present_among_the_items():
    for family, seed, options in cases():
        task = generate_task(family, seed, **options)
        ids = {i.item_id for i in task.items}
        assert set(task.truth.critical_evidence) <= ids


def test_evidence_position_places_the_decisive_item():
    for seed in range(10):
        first = generate_task("evidence", seed, n_distractors=8, evidence_position=0.0)
        last = generate_task("evidence", seed, n_distractors=8, evidence_position=1.0)
        crit = first.truth.critical_evidence[0]
        assert first.items[0].item_id == crit
        assert last.items[-1].item_id == last.truth.critical_evidence[0]


def test_distractor_kinds_produce_the_requested_shape():
    plausible = generate_task("evidence", 5, n_distractors=6, distractor_kind="plausible")
    keyed = [
        i
        for i in plausible.items
        if i.meta.claim_key and i.item_id not in plausible.truth.critical_evidence
    ]
    assert len(keyed) == 6
    irrelevant = generate_task("evidence", 5, n_distractors=6, distractor_kind="irrelevant")
    assert all(
        i.meta.claim_key is None
        for i in irrelevant.items
        if i.item_id not in irrelevant.truth.critical_evidence
    )


def test_adversarial_tasks_have_traps_and_controls_do_not_forbid_the_right_answer():
    for seed in SEEDS:
        adversarial = generate_task("authority", seed)
        assert adversarial.truth.traps and adversarial.truth.forbidden_actions
        control = generate_task("authority", seed, control=True)
        assert ("PROCEED", None) in control.truth.valid_actions
        assert not control.truth.traps
        scope_control = generate_task("scope", seed, control=True)
        assert any(t.reason_class == "scope" for t in scope_control.truth.item_truth)


def test_unresolved_provenance_expects_abstention():
    for seed in SEEDS:
        for mode in ("silent", "equal"):
            task = generate_task("provenance", seed, policy=mode)
            assert task.truth.expected_conflict == "unresolved"
            assert task.truth.valid_actions == (("ABSTAIN", None),)


def test_unknown_family_is_refused():
    with pytest.raises(ValueError):
        generate_task("nope", 1)
