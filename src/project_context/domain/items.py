"""A single identifiable unit participating in a context bundle.

Book mapping: one rendered element of the current context (Chapter 1).
Later-earned fields (retention_class, recoverability, exactness, freshness,
group relationships) are deliberately absent in Stage 0; they enter only when
an experiment requires them. See specs/architecture.md.

Identity rule (book Chapter 11/12 preparation): `id` identifies this
representation instance; `semantic_id` optionally identifies the underlying
information across representations. Neither is ever derived from secret or
private content (see specs/privacy.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "project_context.context_item.v1"


@dataclass(frozen=True)
class ContextItem:
    id: str
    source: str
    kind: str
    content: str
    position: int = 0
    token_count: int = 0
    token_provenance: str = "approximation"
    authority: str | None = None
    scope: str | None = None
    observed_at: str | None = None
    semantic_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "source": self.source,
            "kind": self.kind,
            "content": self.content,
            "position": self.position,
            "token_count": self.token_count,
            "token_provenance": self.token_provenance,
            "authority": self.authority,
            "scope": self.scope,
            "observed_at": self.observed_at,
            "semantic_id": self.semantic_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextItem":
        version = data.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported ContextItem schema: {version!r}")
        return cls(
            id=data["id"],
            source=data["source"],
            kind=data["kind"],
            content=data["content"],
            position=data.get("position", 0),
            token_count=data.get("token_count", 0),
            token_provenance=data.get("token_provenance", "approximation"),
            authority=data.get("authority"),
            scope=data.get("scope"),
            observed_at=data.get("observed_at"),
            semantic_id=data.get("semantic_id"),
        )


def estimate_tokens(text: str) -> tuple[int, str]:
    """Naive local token estimate. NOT a real tokenizer.

    Returns (estimate, provenance). Rule: max(1, round(words * 1.3)) for
    non-empty text, else 0. Provenance is always "approximation". Never
    store this as provider-observed telemetry (see telemetry.TokenCount).
    """
    words = len(text.split())
    if words == 0:
        return 0, "approximation"
    return max(1, round(words * 1.3)), "approximation"


def make_item(
    *,
    id: str,
    source: str,
    kind: str,
    content: str,
    authority: str | None = None,
    scope: str | None = None,
    semantic_id: str | None = None,
) -> ContextItem:
    """Build an item with a local token estimate. Position is assigned by
    the bundle builder, not here."""
    count, provenance = estimate_tokens(content)
    return ContextItem(
        id=id,
        source=source,
        kind=kind,
        content=content,
        token_count=count,
        token_provenance=provenance,
        authority=authority,
        scope=scope,
        semantic_id=semantic_id,
    )


# Re-exported for tests that guard the Stage 0 boundary.
_FIELD_NAMES = frozenset(field.name for field in __import__("dataclasses").fields(ContextItem))
