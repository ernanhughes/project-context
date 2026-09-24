"""Tests for the catalogue client paging."""

from catalogue import PAGE_SIZE


def test_page_size_is_fifty() -> None:
    assert PAGE_SIZE == 50
