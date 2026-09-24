"""Session cleanup.

Removes expired guest sessions from the session store to reclaim space.
Sessions older than thirty days are considered expired. Each row carries
a status field used by the support dashboard.
"""

from __future__ import annotations

import json
import time

STORE = "sessions.json"
RETENTION_DAYS = 30


def load() -> list[dict]:
    try:
        with open(STORE, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return []


def save(rows: list[dict]) -> None:
    with open(STORE, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2)


def seed() -> None:
    """Write a small example store."""
    save(
        [
            {"id": "s-1", "status": "active", "last_seen": time.time()},
            {"id": "s-2", "status": "disputed", "last_seen": time.time() - 60 * 86400},
            {"id": "s-3", "status": "active", "last_seen": time.time() - 60 * 86400},
        ]
    )


def cleanup(now: float | None = None) -> int:
    """Delete expired sessions. Returns the number removed."""
    moment = now if now is not None else time.time()
    cutoff = moment - RETENTION_DAYS * 86400
    rows = load()
    kept = [row for row in rows if row["last_seen"] >= cutoff]
    save(kept)
    return len(rows) - len(kept)
