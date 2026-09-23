"""Deterministic action parser. Extracts the first balanced JSON object
from raw model text and validates the action enum for the task family.
Malformed output is an observed outcome (parse-failure), never repaired.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

PARSER_VERSION = "action-parser-v1"


@dataclass(frozen=True)
class ParsedAction:
    action: str
    target: str | None
    value: str | None
    reason_code: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "value": self.value,
            "reason_code": self.reason_code,
        }


def extract_json_object(text: str) -> str | None:
    """Return the first balanced {...} span, or None if unbalanced."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_action(raw_text: str, allowed_actions: list[str]) -> tuple[ParsedAction | None, str]:
    """Parse one structured action. Returns (action_or_None, parse_status)
    where status is 'ok' or 'parse-failure'. The action enum is strict;
    all other fields accept any string or null."""
    span = extract_json_object(raw_text)
    if span is None:
        return None, "parse-failure"
    try:
        data = json.loads(span)
    except json.JSONDecodeError:
        return None, "parse-failure"
    if not isinstance(data, dict):
        return None, "parse-failure"
    action = data.get("action")
    if not isinstance(action, str) or action not in allowed_actions:
        return None, "parse-failure"

    def opt(key: str) -> str | None:
        value = data.get(key)
        return value if isinstance(value, str) or value is None else None

    if any(
        not isinstance(data.get(key), (str, type(None)))
        for key in ("target", "value", "reason_code")
    ):
        return None, "parse-failure"
    return (
        ParsedAction(
            action=action,
            target=opt("target"),
            value=opt("value"),
            reason_code=opt("reason_code"),
        ),
        "ok",
    )
