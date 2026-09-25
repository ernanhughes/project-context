"""Frozen-finding manifests: recomputation, drift detection, publication gate.
Synthetic files in a temp directory; touches no real artifact."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path("scripts") / "evidence_findings.py"


@pytest.fixture()
def tool():
    spec = importlib.util.spec_from_file_location("evidence_findings", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _live(tmp: Path, **overrides) -> Path:
    canary = {
        "status": "PASS",
        "compiler": {"revision": "r"},
        "compilation": {"success": True, "bundle_hash": "h"},
        "transport": {"pre_blocks": 4, "post_blocks": 5, "runtime_outcome": "injected"},
        "observer": {"session_id": "s", "sequence": 1, "marker_count": 1},
        "reconciliation": {"bundle_hash_match": True},
        "failures": [],
    }
    receipt = {"status": "PASS", "bundle_hash": "h", "model_match": True}
    hook = {
        "kind": "hook",
        "sessionID": "s",
        "preBlocks": 4,
        "postBlocks": 5,
        "outcome": "injected",
    }
    for key, value in overrides.items():
        if key == "hook":
            hook.update(value)
        elif key == "receipt":
            receipt.update(value)
    (tmp / "compiler-canary.json").write_text(json.dumps(canary), encoding="utf-8")
    (tmp / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    (tmp / "request.json").write_text(json.dumps({"usable_token_budget": 500}), encoding="utf-8")
    (tmp / "candidates.json").write_text(json.dumps({"candidates": [{}]}), encoding="utf-8")
    (tmp / "runtime-trace.jsonl").write_text(
        json.dumps({"kind": "setup"}) + "\n" + json.dumps(hook) + "\n", encoding="utf-8"
    )
    return tmp


def test_live_summary_recomputed_from_artifacts(tool, tmp_path):
    summary = tool.summarise_live(_live(tmp_path))
    assert summary["system_blocks_before"] == 4
    assert summary["system_blocks_after"] == 5
    assert summary["marker_count"] == 1
    assert summary["candidate_count"] == 1


def test_live_summary_refuses_disagreeing_evidence(tool, tmp_path):
    with pytest.raises(ValueError, match="post_blocks"):
        tool.summarise_live(_live(tmp_path, hook={"postBlocks": 6}))
    other = tmp_path / "b"
    other.mkdir()
    with pytest.raises(ValueError, match="bundle hash"):
        tool.summarise_live(_live(other, receipt={"bundle_hash": "x"}))


def test_wave_summary_counts_invalid_runs(tool, tmp_path):
    runs = [
        {
            "transport": {"status": "FAIL", "reason": "no observed context records", "records": 0},
            "graded": {"valid": False},
        }
        for _ in range(3)
    ]
    path = tmp_path / "result.json"
    path.write_text(
        json.dumps({"experiment_id": "e", "run_count": 3, "runs": runs}), encoding="utf-8"
    )
    summary = tool.summarise_wave(path)
    assert summary["planned_runs"] == 3
    assert summary["valid_behavioural_runs"] == 0
    assert summary["transport_fail_runs"] == 3


def test_publish_refuses_machine_paths(tool, tmp_path, monkeypatch, capsys):
    src = _live(tmp_path / "src") if (tmp_path / "src").mkdir() is None else None
    (src / "policy.json").write_text("{}", encoding="utf-8")
    (src / "request.json").write_text('{"path": "C:\\Users\\someone\\x"}', encoding="utf-8")
    monkeypatch.setattr(tool, "REPO", tmp_path / "repo")
    assert tool.publish_live(src, None) == 1
    assert "sanitisation gate failed" in capsys.readouterr().out
    assert not (tmp_path / "repo" / tool.LIVE_DIR).exists()
