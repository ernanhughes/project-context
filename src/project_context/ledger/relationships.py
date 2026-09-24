"""Typed relationships between ledger items. Direction matters:

    A --depends_on--> B     A needs B resolved first.
    A --blocks--> B         A currently prevents B (informational in 6A).
    A --supersedes--> B     A replaces B; B becomes superseded.
    A --contradicts--> B    A is evidence against B; B becomes contradicted.
    A --verifies--> B       A supports B (informational in 6A; only a
                            `verified` event changes verification state).
    A --derived_from--> B   A was derived from B (lineage, informational).

Stage 6A records relationships and applies the deterministic effects of
`supersedes` and `contradicts`. It never infers a relationship from
prose; fixtures and explicit events supply them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from project_context.ledger.events import LedgerError


class RelationshipType(str, Enum):
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    VERIFIES = "verifies"
    DERIVED_FROM = "derived_from"


@dataclass(frozen=True)
class Relationship:
    type: RelationshipType
    source_id: str
    target_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "source_id": self.source_id,
            "target_id": self.target_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Relationship":
        if not isinstance(data, dict):
            raise LedgerError("broken_reference", f"invalid relationship: {data!r}")
        unknown = set(data) - {"type", "source_id", "target_id"}
        if unknown:
            raise LedgerError("broken_reference", f"unknown relationship keys: {sorted(unknown)}")
        try:
            rel_type = RelationshipType(data["type"])
        except ValueError:
            raise LedgerError(
                "broken_reference", f"unknown relationship type: {data.get('type')!r}"
            )
        source_id = data.get("source_id")
        target_id = data.get("target_id")
        for field, value in (("source_id", source_id), ("target_id", target_id)):
            if not isinstance(value, str) or not value.strip():
                raise LedgerError("broken_reference", f"invalid {field}: {value!r}")
        if source_id == target_id:
            raise LedgerError("broken_reference", "relationship source and target must differ")
        return cls(type=rel_type, source_id=source_id, target_id=target_id)
