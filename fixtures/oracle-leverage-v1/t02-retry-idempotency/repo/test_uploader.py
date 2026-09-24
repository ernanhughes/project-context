"""Tests for the order uploader retry behaviour."""

from uploader import MAX_ATTEMPTS


def test_retry_budget_is_bounded() -> None:
    assert MAX_ATTEMPTS == 3
