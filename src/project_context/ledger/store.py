"""Append-only JSONL store for ledger events. Deliberately boring:
one canonical JSON object per line, no mutation of written lines, no
silent drops. Live stores live under `.local/ledger/` (git-ignored);
committed fixtures live under `fixtures/ledger-v1/`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_context.ledger.events import LedgerError, LedgerEvent

LIVE_STORE_DIR = Path(".local") / "ledger"


def append_event(path: str | Path, event: LedgerEvent) -> None:
    """Validate then append one event as a single JSON line. Creates
    parent directories; never modifies existing lines."""
    if not isinstance(event, LedgerEvent):
        raise LedgerError("unsupported_schema", "append_event requires a LedgerEvent")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event.to_dict(), sort_keys=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_events(path: str | Path) -> list[LedgerEvent]:
    """Load and validate every event in a JSONL store. Corruption fails
    loudly: malformed lines, bad schemas, and duplicate event IDs all
    raise `LedgerError`. Reference and transition checks belong to
    projection, not to loading."""
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise LedgerError("broken_reference", f"ledger store not found: {target}")
    events: list[LedgerEvent] = []
    seen: set[str] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw: Any = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError("unsupported_schema", f"line {lineno} is not JSON: {exc}")
        if not isinstance(raw, dict):
            raise LedgerError("unsupported_schema", f"line {lineno} is not an object")
        event = LedgerEvent.from_dict(raw)
        if event.event_id in seen:
            raise LedgerError("duplicate_event", f"duplicate event id: {event.event_id!r}")
        seen.add(event.event_id)
        events.append(event)
    return events
