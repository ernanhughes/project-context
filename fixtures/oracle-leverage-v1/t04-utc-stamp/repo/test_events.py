"""Tests for the event recorder."""

import json

from events import record


def test_record_returns_parseable_line(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    line = record("deploy")
    assert json.loads(line)["event"] == "deploy"
