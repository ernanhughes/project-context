"""Tests for the leaderboard printer."""

from board import render


def test_ties_listed_alphabetically() -> None:
    rows = [("bran", 55), ("cale", 55)]
    assert render(rows) == "bran 55\ncale 55\n"
