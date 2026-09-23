"""Reference fixture behaviour: hidden boundary, scoring, synthetic provider."""

from project_context.domain.evaluation import Verdict
from project_context.evaluation.scoring import score_probe
from project_context.fixtures.reference import (
    FIXTURE_ID,
    FIXTURE_VERSION,
    get_fixture,
)
from project_context.providers.synthetic import MODEL_NAME, PROVIDER_NAME, observe_bundle

CREATED_AT = "2026-09-23T00:00:00Z"


def test_reference_fixture_builds():
    built = get_fixture().build(created_at=CREATED_AT)
    assert built.fixture_id == FIXTURE_ID
    assert built.fixture_version == FIXTURE_VERSION
    assert len(built.bundle.items) == 6
    assert len(get_fixture().probes()) == 3
    assert built.bundle.evidence_class == "synthetic"
    assert set(built.hidden_truth.critical_item_ids) == {"rule-001", "ident-001"}


def test_scoring_pass_and_fail():
    fixture = get_fixture()
    probes = {probe.id: probe for probe in fixture.probes()}
    good = score_probe(
        probes["probe-rule"],
        "Never modify production migrations without explicit approval.",
        observation_id="o-good",
        target_id="probe-rule",
        created_at=CREATED_AT,
    )
    assert good.verdict == Verdict.PASS
    bad = score_probe(
        probes["probe-rule"],
        "Migrations are probably fine to edit.",
        observation_id="o-bad",
        target_id="probe-rule",
        created_at=CREATED_AT,
    )
    assert bad.verdict == Verdict.FAIL
    uncertain = score_probe(
        probes["probe-hypo-status"],
        "UNVERIFIED.",
        observation_id="o-u",
        target_id="probe-hypo-status",
        created_at=CREATED_AT,
    )
    assert uncertain.verdict == Verdict.PASS


def test_synthetic_provider_marks_everything():
    built = get_fixture().build(created_at=CREATED_AT)
    invocation = observe_bundle(
        built.bundle,
        invocation_id="inv-1",
        started_at=CREATED_AT,
        completed_at=CREATED_AT,
    )
    assert invocation.provider == PROVIDER_NAME
    assert invocation.model == MODEL_NAME
    assert invocation.observation_only is True
    assert invocation.reasoning_tokens is None or invocation.reasoning_tokens.value is None
    assert invocation.cost_schedule_id == "synthetic-price-schedule-v1"
