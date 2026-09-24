"""Event recorder.

Appends one JSON line per event to events.jsonl with the event name
and the moment it was recorded.
"""

from __future__ import annotations

import json
from datetime import datetime

STORE = "events.jsonl"


def record(name: str) -> str:
    """Record an event, returning the stored line."""
    line = json.dumps({"event": name, "at": datetime.now().isoformat()})
    with open(STORE, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return line
