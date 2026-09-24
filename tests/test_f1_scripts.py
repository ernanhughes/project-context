"""The F1 command-line tools: the dry-run script and the session-index manager."""

import importlib.util
import json
from pathlib import Path

import pytest

from project_context.corpus.session_index import ECOLOGICAL, SessionIndex


def load(name):
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_dry_run_script_passes_and_says_it_is_synthetic(capsys):
    dry = load("f1_dry_run")
    assert dry.main() == 0
    out = capsys.readouterr().out
    assert "synthetic" in out.lower() and "ALL PASSED" in out and "FAIL]" not in out


@pytest.fixture
def session_tool(tmp_path, monkeypatch):
    tool = load("f1_session")
    monkeypatch.setattr(tool, "SESSION_INDEX", tmp_path / "session-index.json")
    monkeypatch.setattr(tool, "PUBLIC", tmp_path / "public.json")
    monkeypatch.setattr(tool, "DERIVATIVES", tmp_path / "derivatives")
    return tool, tmp_path


def test_init_creates_an_empty_session_index_once(session_tool, capsys):
    tool, tmp = session_tool
    assert tool.cmd_init(None) == 0
    index = SessionIndex.load(tmp / "session-index.json", ECOLOGICAL)
    assert index.entries == [] and index.genuine_count() == 0
    public = json.loads((tmp / "public.json").read_text(encoding="utf-8"))
    assert public["sessions_recorded"] == 0 and public["entries"] == []
    with pytest.raises(Exception):
        tool.cmd_init(None)


class Args:
    def __init__(self, spool, sidecar, session_id, key="ses-real-key"):
        self.spool, self.sidecar, self.session_id = str(spool), str(sidecar), session_id
        self.session_key, self.sensitive_terms, self.opencode_db = key, "", None


def write_spool(tmp, records):
    spool = tmp / "spool.jsonl"
    spool.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    sidecar = tmp / "sidecar.json"
    sidecar.write_text(json.dumps({"language_family": "python"}), encoding="utf-8")
    return spool, sidecar


def test_process_refuses_synthetic_material(session_tool):
    tool, tmp = session_tool
    tool.cmd_init(None)
    from project_context.corpus.session_index import SessionIndexError
    from project_context.corpus.synthetic import growth_session

    spool, sidecar = write_spool(tmp, growth_session()[0])
    with pytest.raises(SessionIndexError):
        tool.cmd_process(Args(spool, sidecar, "synthetic-growth", key="synthetic-growth"))
    assert SessionIndex.load(tmp / "session-index.json", ECOLOGICAL).entries == []


def test_process_selects_one_session_and_refuses_an_unknown_one(session_tool):
    tool, tmp = session_tool
    tool.cmd_init(None)
    from project_context.corpus.session_index import SessionIndexError
    from project_context.corpus.synthetic import growth_session, long_session

    spool, sidecar = write_spool(tmp, growth_session()[0] + long_session(4))
    with pytest.raises(SessionIndexError):
        tool.cmd_process(Args(spool, sidecar, "ses-that-is-not-there"))


def test_a_registered_calibration_session_cannot_enter_under_any_key(session_tool, monkeypatch):
    tool, tmp = session_tool
    tool.cmd_init(None)
    from project_context.corpus.session_index import SessionIndexError
    from project_context.corpus.synthetic import growth_session

    records = growth_session()[0]
    registry = tmp / "sessions.json"
    registry.write_text(json.dumps([records[0]["session_id"]]), encoding="utf-8")
    monkeypatch.setattr(tool, "CALIBRATION_REGISTRY", registry)
    spool, sidecar = write_spool(tmp, records)
    with pytest.raises(SessionIndexError):
        # a key that looks perfectly genuine: the registry, not the key, decides
        tool.cmd_process(Args(spool, sidecar, records[0]["session_id"], key="ses-genuine-looking"))
    assert SessionIndex.load(tmp / "session-index.json", ECOLOGICAL).entries == []


def test_the_calibration_spool_is_not_a_source_for_the_corpus(session_tool, monkeypatch):
    tool, tmp = session_tool
    tool.cmd_init(None)
    from project_context.corpus.session_index import SessionIndexError

    fake = tmp / "calibration"
    (fake / "spool").mkdir(parents=True)
    monkeypatch.setattr(tool, "CALIBRATION_DIR", fake)
    _, sidecar = write_spool(tmp, [])
    with pytest.raises(SessionIndexError):
        tool.cmd_process(Args(fake / "spool", sidecar, "anything"))


def test_the_committed_public_projection_is_the_ecological_one():
    public = Path("experiments/f1/session-index.public.json")
    assert public.exists()
    body = json.loads(public.read_text(encoding="utf-8"))
    assert body["kind"] == ECOLOGICAL
    assert body["sessions_recorded"] == len(body["entries"])
