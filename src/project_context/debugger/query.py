"""Deterministic structural querying over debugger sessions.

No LLM, no ranking, no inference. Composable structural filters only.
Content search is local-only and requires an explicit flag; by default
only identities and structural metadata are returned, never raw text.
"""

from __future__ import annotations

from typing import Any

from project_context.debugger.analyse import ObservedRequest, _sequence_of
from project_context.debugger.domain import category_of
from project_context.opencode.prevalence import fingerprint


class ContentSearchNotAllowedError(ValueError):
    """Raised when --contains is used without the explicit local flag."""


def query_items(
    ordered: list[ObservedRequest],
    *,
    kind: str | None = None,
    category: str | None = None,
    min_bytes: int | None = None,
    min_tokens: int | None = None,
    repeated: bool = False,
    introduced_after: int | None = None,
    changed: bool = False,
    contains: str | None = None,
    allow_content_search: bool = False,
) -> list[dict[str, Any]]:
    """Return structural metadata for items matching ALL given filters."""
    if contains is not None and not allow_content_search:
        raise ContentSearchNotAllowedError(
            "content search is local-only: pass allow_content_search=True "
            "(CLI: --allow-content-search)"
        )
    # Global content census for the repeated filter.
    counts: dict[str, int] = {}
    for observed in ordered:
        for item in observed.bundle.items:
            digest = fingerprint(item.content)
            counts[digest] = counts.get(digest, 0) + 1
    # First-seen sequence per digest for introduced_after/changed.
    first_seen: dict[str, int] = {}
    for index, observed in enumerate(ordered):
        sequence = _sequence_of(observed, index)
        for item in observed.bundle.items:
            digest = fingerprint(item.content)
            if digest not in first_seen:
                first_seen[digest] = sequence
    results: list[dict[str, Any]] = []
    for index, observed in enumerate(ordered):
        sequence = _sequence_of(observed, index)
        for item in observed.bundle.items:
            digest = fingerprint(item.content)
            size = len(item.content.encode("utf-8"))
            item_category = category_of(item.kind)
            if kind is not None and item.kind != kind:
                continue
            if category is not None and item_category != category:
                continue
            if min_bytes is not None and size < min_bytes:
                continue
            if min_tokens is not None and item.token_count < min_tokens:
                continue
            if repeated and counts.get(digest, 0) < 2:
                continue
            if introduced_after is not None and first_seen.get(digest, 0) <= introduced_after:
                continue
            if changed and counts.get(digest, 0) < 2:
                # Stage 1 'changed' means: byte-identical content recurs
                # across invocations (position/shape may have moved).
                continue
            if contains is not None and contains not in item.content:
                continue
            results.append(
                {
                    "item_id": item.id,
                    "sequence": sequence,
                    "position": item.position,
                    "kind": item.kind,
                    "category": item_category,
                    "bytes": size,
                    "chars": len(item.content),
                    "approx_tokens": item.token_count,
                    "token_provenance": item.token_provenance,
                    "ref": item.ref,
                    "recurrences": counts.get(digest, 0),
                    "first_seen_sequence": first_seen.get(digest),
                }
            )
    return results


def summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    total_bytes = sum(r["bytes"] for r in results)
    total_tokens = sum(r["approx_tokens"] for r in results)
    largest = max((r["bytes"] for r in results), default=0)
    return {
        "items": len(results),
        "bytes": total_bytes,
        "approx_tokens": total_tokens,
        "token_provenance": "approximation",
        "largest_bytes": largest,
    }
