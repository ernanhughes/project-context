"""Evidence-manifest tool: recomputation from artifacts and drift detection.
Uses a tiny synthetic run in a temp directory; touches no real artifact."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path("scripts") / "evidence_manifest.py"


@pytest.fixture()
def tool(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("evidence_manifest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS_ROOT", tmp_path / "runs")
    monkeypatch.setattr(module, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(module, "RUNS", (("compiler-v1", "run-x", (23,)),))
    monkeypatch.setattr(module, "git_subject", lambda commit: "subject")
    return module


def _write_run(root: Path, status_correct=True) -> Path:
    run_dir = root / "runs" / "compiler-v1" / "run-x"
    run_dir.mkdir(parents=True)
    row = {
        "fixture": "f1",
        "strategy": "staged",
        "budget": "tight",
        "status_correct": status_correct,
        "distractor_admission": 2,
        "harmful_admission": 1,
        "illegal_admission": 0,
        **{
            key: 0
            for key in (
                "authority_violations",
                "dependency_violations",
                "floor_violations",
                "freshness_violations",
                "group_violations",
                "scope_violations",
            )
        },
    }
    (run_dir / "results.json").write_text(
        json.dumps({"evaluations": [row], "budgets": ["tight"], "strategies": ["staged"]}),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "git_commit": "abc",
                "evidence_class": "synthetic",
                "experiment_version": "1",
                "fixture_version": "1",
                "policy_version": "p",
                "environment": [["token_mode", "estimate"]],
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_manifest_recomputes_numbers_and_pins_files(tool, tmp_path):
    _write_run(tmp_path)
    manifest = tool.build_manifest("compiler-v1", "run-x", (23,))
    staged = manifest["recomputed_summary"]["per_strategy"]["staged"]
    assert staged["status_correct"] == 1 and staged["distractor_admission"] == 2
    assert staged["harmful_admission"] == 1
    names = {f["name"]: f for f in manifest["artifact_files"]}
    assert set(names) == {"results.json", "manifest.json"}
    assert len(names["results.json"]["sha256"]) == 64
    assert manifest["cited_by_book_chapters"] == [23]
    assert any("byte-for-byte published copy" in note for note in manifest["known_limitations"])


def test_generation_is_deterministic(tool, tmp_path):
    _write_run(tmp_path)
    first = tool.dump(tool.build_manifest("compiler-v1", "run-x", (23,)))
    second = tool.dump(tool.build_manifest("compiler-v1", "run-x", (23,)))
    assert first == second


def test_verify_detects_drift_and_missing_artifacts(tool, tmp_path, monkeypatch, capsys):
    run_dir = _write_run(tmp_path)
    monkeypatch.setattr("sys.argv", ["evidence_manifest.py"])
    assert tool.main() == 0
    monkeypatch.setattr("sys.argv", ["evidence_manifest.py", "--verify"])
    assert tool.main() == 0

    # Tamper with a frozen artifact: verification must fail.
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    results["evaluations"][0]["status_correct"] = False
    (run_dir / "results.json").write_text(json.dumps(results), encoding="utf-8")
    assert tool.main() == 1
    assert "differ from committed manifest" in capsys.readouterr().out

    # Artifact absent locally: unverifiable, not silently passing.
    (run_dir / "results.json").unlink()
    (run_dir / "manifest.json").unlink()
    run_dir.rmdir()
    assert tool.main() == 2
