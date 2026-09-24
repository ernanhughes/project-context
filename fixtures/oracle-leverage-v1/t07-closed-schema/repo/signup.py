"""Signup event emitter.

Builds the signup event payload and delivers it to the event bus.
Payloads carry the signup user id and signup method.
"""

from __future__ import annotations

import json

BUS = "events.bus"


def build(user_id: str, method: str) -> dict:
    """Build the signup event payload."""
    return {"user_id": user_id, "method": method}


def emit(user_id: str, method: str) -> str:
    """Serialise the signup event for the bus."""
    return json.dumps(build(user_id, method))
