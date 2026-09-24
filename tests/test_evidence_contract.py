"""Failure ladder and evidence-run contract."""

import pytest

from project_context.domain.failure import (
    ATTRIBUTION_ORDER,
    FailureEvidence,
    FailureState,
    attribute,
)
from project_context.runs.contract import (
    REQUIRED_EVIDENCE_KEYS,
    REQUIRED_LIVE_KEYS,
    check_evidence_manifest,
)


def test_ladder_covers_every_state_exactly_once():
    assert set(ATTRIBUTION_ORDER) == set(FailureState)
    assert len(ATTRIBUTION_ORDER) == len(set(ATTRIBUTION_ORDER)) == 9
    assert ATTRIBUTION_ORDER[0] is FailureState.CONTROL_FAILURE


def test_clean_case_has_no_failure_state():
    assert attribute(FailureEvidence()) is None


@pytest.mark.parametrize(
    "field,value,state",
    [
        ("control_valid", False, FailureState.CONTROL_FAILURE),
        ("required_admitted", False, FailureState.ABSENT),
        ("required_survived", False, FailureState.LOST),
        ("source_current", False, FailureState.STALE),
        ("in_scope", False, FailureState.SCOPE_LEAK),
        ("no_conflicting_influence", False, FailureState.OVERRIDDEN),
        ("evidence_used", False, FailureState.UNRECOVERED),
        ("applied_correctly", False, FailureState.MISAPPLIED),
        ("degraded_vs_baseline", True, FailureState.INTERFERENCE),
    ],
)
def test_each_fact_maps_to_its_state(field, value, state):
    assert attribute(FailureEvidence(**{field: value})) is state


def test_earlier_states_explain_later_ones():
    # Never admitted AND misapplied: the primary state is ABSENT, not MISAPPLIED.
    both = FailureEvidence(required_admitted=False, applied_correctly=False)
    assert attribute(both) is FailureState.ABSENT
    # An invalid control outranks everything.
    invalid = FailureEvidence(control_valid=False, required_admitted=False)
    assert attribute(invalid) is FailureState.CONTROL_FAILURE


def test_unestablished_facts_never_trigger_a_state():
    unknown = FailureEvidence(
        required_admitted=None,
        required_survived=None,
        evidence_used=None,
        applied_correctly=None,
    )
    assert attribute(unknown) is None


def _manifest(**env):
    base = {
        "run_purpose": "evidence",
        "experiment_family": "F5",
        "preregistration": "experiments/preregistrations/F5.md@abc123",
        "fixture_revision": "fx1",
        "configuration_revision": "cfg1",
        "task_population": "gen-v1",
    }
    base.update(env)
    return {
        "git_commit": "c",
        "experiment_id": "e",
        "experiment_version": "1",
        "evidence_class": "synthetic",
        "environment": [[k, v] for k, v in base.items()],
    }


LIVE_ENV = {
    "reader_model": "m:7b",
    "reader_model_digest": "d",
    "reader_model_identity_source": "ollama-api-tags",
    "reader_model_alias_moving": "False",
    "temperature": "0.0",
    "decoding_seed": "1",
}


def test_complete_deterministic_manifest_passes():
    assert check_evidence_manifest(_manifest(), live=False) == []


def test_missing_keys_are_named():
    manifest = _manifest()
    manifest["environment"] = [e for e in manifest["environment"] if e[0] != "fixture_revision"]
    assert check_evidence_manifest(manifest, live=False) == [
        "missing environment key: fixture_revision"
    ]


def test_evidence_run_needs_a_preregistration_commit():
    problems = check_evidence_manifest(_manifest(preregistration="F5.md"), live=False)
    assert problems == ["preregistration must be '<path>@<commit>'"]


def test_live_evidence_run_needs_pinned_identity():
    assert check_evidence_manifest(_manifest(**LIVE_ENV), live=True) == []
    moving = check_evidence_manifest(
        _manifest(**{**LIVE_ENV, "reader_model_alias_moving": "True"}), live=True
    )
    assert "evidence run used a moving model alias" in moving
    nodigest = check_evidence_manifest(
        _manifest(**{**LIVE_ENV, "reader_model_digest": "unavailable"}), live=True
    )
    assert "evidence run has no recorded reader model digest" in nodigest
    assert check_evidence_manifest(_manifest(), live=True)  # live keys missing


def test_exploratory_runs_are_exempt_but_must_be_labelled():
    exploratory = _manifest(run_purpose="exploratory", preregistration="")
    assert check_evidence_manifest(exploratory, live=True) == []
    assert check_evidence_manifest({"environment": []}, live=False)  # unlabelled: refused
    assert set(REQUIRED_LIVE_KEYS).isdisjoint(REQUIRED_EVIDENCE_KEYS)
