"""One rendered context for one model invocation (book Chapter 1: context is
per-computation). Bundles are immutable once recorded and preserve exact
rendering order (book Chapter 6: a bundle is not a set)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from project_context.domain.items import SCHEMA_VERSION as ITEM_SCHEMA
from project_context.domain.items import ContextItem

SCHEMA_VERSION = "project_context.context_bundle.v1"


@dataclass(frozen=True)
class ContextBundle:
    id: str
    items: tuple[ContextItem, ...]
    created_at: str
    layout_trace: tuple[str, ...]
    evidence_class: str = "synthetic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "items": [item.to_dict() for item in self.items],
            "created_at": self.created_at,
            "layout_trace": list(self.layout_trace),
            "evidence_class": self.evidence_class,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextBundle":
        version = data.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported ContextBundle schema: {version!r}")
        items = tuple(ContextItem.from_dict(raw) for raw in data["items"])
        bundle = cls(
            id=data["id"],
            items=items,
            created_at=data["created_at"],
            layout_trace=tuple(data["layout_trace"]),
            evidence_class=data.get("evidence_class", "synthetic"),
        )
        bundle._check_layout()
        return bundle

    def _check_layout(self) -> None:
        rendered = [item.id for item in self.items]
        if list(self.layout_trace) != rendered:
            raise ValueError("layout_trace must equal item order exactly")

    def rendered_token_total(self) -> int:
        return sum(item.token_count for item in self.items)

    def content_hash(self) -> str:
        """Order-sensitive identity over rendered content. [A,B,C] and
        [C,B,A] hash differently even with identical membership."""
        digest = hashlib.sha256()
        for item in self.items:
            digest.update(item.id.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(item.content.encode("utf-8"))
            digest.update(b"\x00")
        return digest.hexdigest()


def build_bundle(
    items: list[ContextItem],
    *,
    bundle_id: str | None = None,
    created_at: str,
    evidence_class: str = "synthetic",
) -> ContextBundle:
    """Assign positions 0..n in given order and freeze. Live captures pass
    bundle_id=None to get a UUID; deterministic fixtures pass stable ids."""
    ordered = tuple(
        ContextItem(
            id=item.id,
            source=item.source,
            kind=item.kind,
            content=item.content,
            position=index,
            token_count=item.token_count,
            token_provenance=item.token_provenance,
            authority=item.authority,
            scope=item.scope,
            observed_at=item.observed_at,
            semantic_id=item.semantic_id,
        )
        for index, item in enumerate(items)
    )
    bundle = ContextBundle(
        id=bundle_id or f"bundle-{uuid.uuid4().hex[:12]}",
        items=ordered,
        created_at=created_at,
        layout_trace=tuple(item.id for item in ordered),
        evidence_class=evidence_class,
    )
    bundle._check_layout()
    return bundle


ITEM_SCHEMA_VERSION = ITEM_SCHEMA
