"""Publication gate for approved synthetic runs, and run-location resolution.
All in temp directories; nothing real is read or written."""

import importlib.util
import json
from pathlib import Path

import pytest

from project_context.runs.locate import frozen_run_dir

SCRIPT = Path("scripts") / "publish_evidence_runs.py"


@pytest.fixture()
def tool(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("publish_evidence_runs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "LOCAL", tmp_path / "local")
    monkeypatch.setattr(module, "PUBLISHED", tmp_path / "published")
    monkeypatch.setattr(module, "APPROVED", (("exp", "run-1"),))
    return module


def _make_run(tool, files=None, evidence_class="synthetic"):
    run = tool.LOCAL / "exp" / "run-1"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(
        json.dumps({"evidence_class": evidence_class}), encoding="utf-8"
    )
    for name, text in (files or {"results.json": '{"ok": 1}'}).items():
        (run / name).write_text(text, encoding="utf-8")
    return run


def test_clean_synthetic_run_is_published_byte_for_byte(tool, monkeypatch):
    run = _make_run(tool)
    monkeypatch.setattr("sys.argv", ["publish"])
    assert tool.main() == 0
    for name in ("manifest.json", "results.json"):
        assert (tool.PUBLISHED / "exp" / "run-1" / name).read_bytes() == (run / name).read_bytes()
    # Idempotent: a second run copies nothing and does not fail.
    assert tool.main() == 0


@pytest.mark.parametrize(
    "leak",
    [
        r"C:\Users\someone\project",
        "/home/someone/project",
        "person@example.org",
        "http://localhost:11434/v1",
        "host 10.1.2.3",
        "sk-abcdefghijklmnop1234",
        "Bearer abcdefghijkl",
        "api_key = 'x'",
    ],
)
def test_gate_refuses_leaks(tool, monkeypatch, leak):
    _make_run(tool, {"results.json": json.dumps({"note": leak})})
    monkeypatch.setattr("sys.argv", ["publish"])
    assert tool.main() == 1
    assert not tool.PUBLISHED.exists()  # nothing copied on refusal


def test_gate_refuses_non_synthetic(tool, monkeypatch):
    _make_run(tool, evidence_class="provider-observed")
    monkeypatch.setattr("sys.argv", ["publish"])
    assert tool.main() == 1


def test_publish_never_overwrites_a_differing_file(tool, monkeypatch):
    run = _make_run(tool)
    monkeypatch.setattr("sys.argv", ["publish"])
    assert tool.main() == 0
    (run / "results.json").write_text('{"ok": 2}', encoding="utf-8")
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        tool.main()


def test_frozen_run_dir_prefers_local_then_published(tmp_path):
    published = tmp_path / "evidence" / "runs" / "e" / "r"
    published.mkdir(parents=True)
    assert frozen_run_dir("e", "r", root=tmp_path) == published
    local = tmp_path / ".local" / "runs" / "e" / "r"
    local.mkdir(parents=True)
    assert frozen_run_dir("e", "r", root=tmp_path) == local
    assert frozen_run_dir("e", "missing", root=tmp_path).parts[-4:] == (
        "evidence",
        "runs",
        "e",
        "missing",
    )
