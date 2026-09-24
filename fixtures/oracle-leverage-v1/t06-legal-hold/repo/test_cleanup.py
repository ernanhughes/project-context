"""Tests for session cleanup."""

from cleanup import RETENTION_DAYS


def test_retention_window_is_thirty_days() -> None:
    assert RETENTION_DAYS == 30
