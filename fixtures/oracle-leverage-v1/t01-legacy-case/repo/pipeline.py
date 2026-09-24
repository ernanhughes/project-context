"""Import pipeline with identifier normalisation.

Legacy identifiers arrive from partner feeds with varying letter case.
The pipeline normalises them for internal matching.
"""

from __future__ import annotations


def normalise(identifier: str) -> str:
    """Normalise one identifier for internal matching."""
    return identifier.strip().lower()


def run(records: list[dict[str, str]]) -> list[dict[str, str]]:
    """Normalise the ``legacy_id`` field of every record."""
    out = []
    for record in records:
        row = dict(record)
        row["legacy_id"] = normalise(row["legacy_id"])
        out.append(row)
    return out
