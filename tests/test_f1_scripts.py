"""The F1 command-line tools: the dry-run script and the ledger manager."""

import importlib.util
import json
from pathlib import Path

import pytest

from project_context.corpus.ledger import ECOLOGICAL, Ledger


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
    monkeypatch.setattr(tool, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(tool, "PUBLIC", tmp_path / "public.json")
    monkeypatch.setattr(tool, "DERIVATIVES", tmp_path / "derivatives")
    return tool, tmp_path


def test_init_creates_an_empty_ecological_ledger_once(session_tool, capsys):
    tool, tmp = session_tool
    assert tool.cmd_init(None) == 0
    ledger = Ledger.load(tmp / "ledger.json", ECOLOGICAL)
    assert ledger.entries == [] and ledger.genuine_count() == 0
    public = json.loads((tmp / "public.json").read_text(encoding="utf-8"))
    assert public["sessions_recorded"] == 0 and public["entries"] == []
    with pytest.raises(Exception):
        tool.cmd_init(None)


def test_process_refuses_synthetic_material(session_tool, tmp_path):
    tool, tmp = session_tool
    tool.cmd_init(None)
    from project_context.corpus.synthetic import growth_session

    spool = tmp / "spool.jsonl"
    spool.write_text("\n".join(json.dumps(r) for r in growth_session()[0]), encoding="utf-8")
    sidecar = tmp / "sidecar.json"
    sidecar.write_text(json.dumps({"language_family": "python"}), encoding="utf-8")

    class Args:
        pass

    args = Args()
    args.spool, args.sidecar = str(spool), str(sidecar)
    args.session_key, args.sensitive_terms = "synthetic-growth", ""
    from project_context.corpus.ledger import LedgerError

    with pytest.raises(LedgerError):
        tool.cmd_process(args)
    assert Ledger.load(tmp / "ledger.json", ECOLOGICAL).entries == []


def test_the_committed_public_ledger_is_the_ecological_one():
    public = Path("experiments/f1/ledger.public.json")
    assert public.exists()
    body = json.loads(public.read_text(encoding="utf-8"))
    assert body["kind"] == ECOLOGICAL
    assert body["sessions_recorded"] == len(body["entries"])
