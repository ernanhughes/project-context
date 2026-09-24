"""Checkout rollout flags.

Controls which checkout version each region receives and which
regional store serves their data.
"""

from __future__ import annotations

CHECKOUT_V2 = False
STORE_REGION = "us"


def checkout_for(region: str) -> str:
    """Return the checkout version label for a region."""
    if region == "eu" and CHECKOUT_V2:
        return "v2"
    return "v1"
