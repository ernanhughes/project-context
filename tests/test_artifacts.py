"""Run artifact write/validate round trips and tamper detection."""

from project_context.domain.evaluation import EvaluationLog
from project_context.domain.runs import RunManifest
from project_context.runs.artifacts import validate_artifact, write_artifact

CREATED_AT = "2026-09-23T00:00:00Z"


def _manifest() -> RunManifest:
    return RunManifest(
        run_id="run-demo",
        experiment_id="smoke",
        experiment_version="0",
        git_commit="deadbeef",
        timestamp=CREATED_AT,
        provider="synthetic",
        model="synthetic-deterministic-v1",
        evidence_class="synthetic",
    )


def test_write_and_validate_round_trip(tmp_path):
    run_dir = write_artifact(
        tmp_path,
        _manifest(),
        EvaluationLog(),
        {"metrics": {}},
        readme_text="# smoke run\n\nSYNTHETIC — NOT BOOK RESULT\n",
    )
    assert validate_artifact(run_dir) == []


def test_missing_manifest_detected(tmp_path):
    run_dir = write_artifact(
        tmp_path,
        _manifest(),
        EvaluationLog(),
        {"metrics": {}},
        readme_text="# smoke run\n",
    )
    (run_dir / "manifest.json").unlink()
    errors = validate_artifact(run_dir)
    assert any("manifest.json" in error for error in errors)


def test_synthetic_claiming_provider_evidence_detected(tmp_path):
    run_dir = write_artifact(
        tmp_path,
        _manifest(),
        EvaluationLog(),
        {"metrics": {}, "telemetry_source": "provider"},
        readme_text="# smoke run\n",
    )
    errors = validate_artifact(run_dir)
    assert any("provider" in error for error in errors)


def test_secret_patterns_detected(tmp_path):
    run_dir = write_artifact(
        tmp_path,
        _manifest(),
        EvaluationLog(),
        {"metrics": {}},
        readme_text="# smoke run\nAKIAIOSFODNN7EXAMPLE\n",
    )
    errors = validate_artifact(run_dir)
    assert any("secret" in error for error in errors)
