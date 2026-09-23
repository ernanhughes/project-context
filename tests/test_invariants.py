"""Architecture invariant tests. These pin Stage 0 guarantees; a failing
test here means the observation/intervention separation broke."""

import dataclasses

import pytest

from project_context.corpus.manifest import (
    SANITISATION_APPROVED_PUBLIC,
    SANITISATION_RAW_LOCAL,
    SANITISATION_SANITISED,
    CorpusManifest,
    UnsanitisedCorpusError,
    assert_publishable,
)
from project_context.domain import bundles, evaluation, interventions, items, runs
from project_context.domain.evaluation import EvaluationLog, EvaluationObservation, Verdict
from project_context.fixtures.reference import get_fixture
from project_context.providers.base import ProviderObservation
from project_context.telemetry import TokenCount


def _manifest(**overrides):
    base = {
        "run_id": "run-1",
        "experiment_id": "exp-1",
        "experiment_version": "1",
        "git_commit": "abc123",
        "timestamp": "2026-09-23T00:00:00Z",
        "provider": "synthetic",
        "model": "synthetic-deterministic-v1",
        "evidence_class": "synthetic",
    }
    base.update(overrides)
    return runs.RunManifest(**base)


def test_bundle_preserves_ordering():
    made = [
        items.make_item(id=f"i-{n}", source="s", kind="k", content=f"content {n}") for n in range(3)
    ]
    bundle = bundles.build_bundle(made, bundle_id="b", created_at="2026-09-23T00:00:00Z")
    assert [item.id for item in bundle.items] == ["i-0", "i-1", "i-2"]
    assert [item.position for item in bundle.items] == [0, 1, 2]
    assert list(bundle.layout_trace) == ["i-0", "i-1", "i-2"]


def test_bundle_identity_changes_with_ordering():
    made = [
        items.make_item(id=f"i-{n}", source="s", kind="k", content=f"content {n}") for n in range(3)
    ]
    forward = bundles.build_bundle(made, bundle_id="b", created_at="2026-09-23T00:00:00Z")
    backward = bundles.build_bundle(
        list(reversed(made)), bundle_id="b", created_at="2026-09-23T00:00:00Z"
    )
    assert forward.content_hash() != backward.content_hash()


def test_hidden_truth_never_rendered():
    built = get_fixture().build(created_at="2026-09-23T00:00:00Z")
    from project_context.fixtures.base import render_visible_text

    visible = render_visible_text(built.bundle)
    for probe in get_fixture().probes():
        assert probe.question not in visible
        assert probe.id not in visible
    assert "oracle" not in visible
    assert "hidden" not in visible


def test_unavailable_metrics_stay_unavailable():
    obs = ProviderObservation.from_mapping("x", "y", {})
    assert obs.input_tokens.value is None
    assert obs.reasoning_tokens is None or obs.reasoning_tokens.value is None
    assert obs.cached_read_tokens is None or obs.cached_read_tokens.value is None
    assert TokenCount.unavailable().value is None


def test_manifest_reconstructable():
    first = _manifest()
    second = _manifest()
    assert first == second
    third = _manifest(timestamp="2026-09-24T00:00:00Z")
    assert third != first
    assert third.same_configuration(first)


def test_evidence_append_only():
    log = EvaluationLog()
    obs = EvaluationObservation(
        id="o1",
        target_type="probe",
        target_id="p1",
        metric="m",
        value="v",
        verdict=Verdict.PASS,
        evidence="e",
        evaluator="t",
        created_at="2026-09-23T00:00:00Z",
    )
    log2 = log.append(obs)
    assert len(log.observations) == 0
    assert len(log2.observations) == 1


def test_export_refuses_unsanitised():
    for status in (SANITISATION_RAW_LOCAL, SANITISATION_SANITISED):
        manifest = CorpusManifest(
            corpus_id="c",
            trace_id="t",
            source_type="opencode",
            captured_at="2026-09-23T00:00:00Z",
            turn_count=3,
            tool_call_count=5,
            rendered_token_min=100,
            rendered_token_max=900,
            sanitisation_status=status,
            content_hash="withheld-local",
        )
        with pytest.raises(UnsanitisedCorpusError):
            assert_publishable(manifest)
    ok_manifest = CorpusManifest(
        corpus_id="c",
        trace_id="t",
        source_type="opencode",
        captured_at="2026-09-23T00:00:00Z",
        turn_count=3,
        tool_call_count=5,
        rendered_token_min=100,
        rendered_token_max=900,
        sanitisation_status=SANITISATION_APPROVED_PUBLIC,
        content_hash="sha256:abc",
    )
    assert_publishable(ok_manifest)


def test_cli_inspection_deterministic(capsys):
    from project_context.cli.main import main

    assert main(["fixture", "inspect", "reference"]) == 0
    first = capsys.readouterr().out
    assert main(["fixture", "inspect", "reference"]) == 0
    second = capsys.readouterr().out
    assert first == second
    assert "[SYNTHETIC]" in first


def test_no_intervention_alters_bundle():
    made = [items.make_item(id="i", source="s", kind="k", content="c")]
    bundle = bundles.build_bundle(made, bundle_id="b", created_at="2026-09-23T00:00:00Z")
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.items = ()  # type: ignore[misc]
    for forbidden in ("prune", "compact", "decay", "retrieve", "assemble"):
        assert not hasattr(interventions, forbidden), forbidden


def test_json_round_trips():
    item = items.make_item(id="i", source="s", kind="k", content="hello")
    assert items.ContextItem.from_dict(item.to_dict()) == item
    bundle = bundles.build_bundle([item], bundle_id="b", created_at="t")
    assert bundles.ContextBundle.from_dict(bundle.to_dict()) == bundle
    manifest = _manifest()
    assert runs.RunManifest.from_dict(manifest.to_dict()) == manifest
    obs = EvaluationObservation(
        id="o",
        target_type="t",
        target_id="t",
        metric="m",
        value="v",
        verdict=Verdict.INCONCLUSIVE,
        evidence="e",
        evaluator="ev",
        created_at="t",
    )
    assert evaluation.EvaluationObservation.from_dict(obs.to_dict()) == obs


def test_later_fields_absent_in_stage_zero():
    item = items.make_item(id="i", source="s", kind="k", content="c")
    for absent in (
        "retention_class",
        "recoverability",
        "exactness",
        "freshness",
        "group",
        "fidelity_level",
    ):
        assert not hasattr(item, absent), absent
