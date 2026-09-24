"""Tests for the checkout rollout flags."""

from rollout import checkout_for


def test_default_region_gets_v1() -> None:
    assert checkout_for("us") == "v1"
