"""Tests for the signup event emitter."""

import json

from signup import build


def test_payload_carries_identity_and_method() -> None:
    payload = build("u-9", "sso")
    assert json.loads(json.dumps(payload)) == {"user_id": "u-9", "method": "sso"}
