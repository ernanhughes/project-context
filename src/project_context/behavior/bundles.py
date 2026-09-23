"""Bundle reconstruction and interventional bundle surgery.

Primary B1–BO bundles are never recompiled: they are re-rendered
deterministically from frozen run-001 traces plus committed fixture
contents, then digest-verified against run-001 before any reader call.
Interventional bundles (MA/MR/MT/MW) are explicit derivations with
their own identities — never recompiled, never silent.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

from project_context.compiler.domain import ContextCandidate, ContextRequest
from project_context.compiler.engine import (
    _SEPARATOR_TOKENS,
    SEPARATOR,
    _decoration_tokens,
    header_tokens,
)
from project_context.domain.bundles import ContextBundle, build_bundle
from project_context.domain.items import estimate_tokens, make_item

ORDER_ROLES = ("instruction", "task", "state", "evidence", "support", "tool")


def render_from_trace(
    admitted_ids: list[str],
    candidates: list[ContextCandidate],
    request: ContextRequest,
    order_roles: tuple[str, ...] = ORDER_ROLES,
) -> ContextBundle:
    """Re-render a bundle from admitted record IDs. Deterministic: role
    order, then candidate_id. Must reproduce run-001 bytes exactly."""
    by_id = {c.candidate_id: c for c in candidates}
    rank = {role: index for index, role in enumerate(order_roles)}
    ordered = sorted(
        (by_id[cid] for cid in admitted_ids),
        key=lambda c: (rank.get(c.order_role, len(rank)), c.candidate_id),
    )
    exacted = [
        dataclasses.replace(
            make_item(id=c.candidate_id, source=c.source_kind, kind=c.kind, content=c.content),
            token_count=c.token_count + _decoration_tokens(c),
        )
        for c in ordered
    ]
    return build_bundle(
        exacted,
        bundle_id=f"{request.request_id}-bundle",
        created_at=request.created_at,
        evidence_class="synthetic",
    )


def bundle_render_tokens(bundle: ContextBundle, request: ContextRequest) -> int:
    total = sum(item.token_count for item in bundle.items)
    total += max(0, len(bundle.items) - 1) * _SEPARATOR_TOKENS
    total += header_tokens(request)
    return total


def derive_bundle(
    *,
    parent: ContextBundle,
    remove_ids: list[str],
    add_records: list[dict[str, Any]],
    bundle_id: str,
) -> tuple[ContextBundle, list[str], list[str]]:
    """Deterministic bundle surgery. Kept items preserve parent order and
    exact rendered costs; added records append in listed order with local
    estimates. Returns (bundle, removed, added). An empty diff rebuilds
    byte-identically (the MR restoration property)."""
    removed_set = set(remove_ids)
    kept = [item for item in parent.items if item.id not in removed_set]
    removed = [item.id for item in parent.items if item.id in removed_set]
    added: list[str] = []
    new_items = list(kept)
    for record in add_records:
        count, _ = estimate_tokens(record["content"])
        made = make_item(
            id=record["candidate_id"],
            source=record.get("source_kind", "synthetic-intervention"),
            kind=record.get("kind", "evidence"),
            content=record["content"],
        )
        new_items.append(dataclasses.replace(made, token_count=count))
        added.append(record["candidate_id"])
    bundle = build_bundle(
        new_items,
        bundle_id=bundle_id,
        created_at=parent.created_at,
        evidence_class="synthetic",
    )
    return bundle, removed, added


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_visible(bundle: ContextBundle) -> str:
    """Exact reader-visible context payload: ordered contents joined."""
    return SEPARATOR.join(item.content for item in bundle.items)
