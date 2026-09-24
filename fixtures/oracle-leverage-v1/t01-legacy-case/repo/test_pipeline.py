"""Tests for the import pipeline normalisation."""

from pipeline import normalise, run


def test_normalise_strips_and_lowers() -> None:
    assert normalise("  AbC-123 ") == "abc-123"


def test_run_normalises_every_row() -> None:
    rows = [{"legacy_id": "X-1"}, {"legacy_id": " y-2 "}]
    assert run(rows) == [{"legacy_id": "x-1"}, {"legacy_id": "y-2"}]
