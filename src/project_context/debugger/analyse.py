"""Debugger analysis: pure structural views over ingested V2 captures.

No model calls, no network, no mutation. All sizes exact (bytes/chars);
token figures are local approximations, always labelled as such.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_context.debugger.domain import (
    CATEGORIES,
    CompositionSlice,
    InvocationView,
    category_of,
)
from project_context.domain.bundles import ContextBundle
from project_context.domain.invocations import ModelInvocation
from project_context.opencode.bridge import (
    CAPTURE_STAGE_V2,
    load_capture_dir,
    load_capture_file,
    validate_record,
)
from project_context.opencode.ingest import SequenceTracker, ingest_record
from project_context.opencode.prevalence import (
    bundle_bytes,
    bundle_chars,
    fingerprint,
    structural_shared_prefix,
)

PRIMARY_KIND = "context"


@dataclass(frozen=True)
class ObservedRequest:
    bundle: ContextBundle
    invocation: ModelInvocation
    request_kind: str
    agent: str | None
    model_limits: dict[str, Any] | None = None


@dataclass
class DebuggerStore:
    """Ordered primary observations grouped by session scope."""

    sessions: dict[str, list[ObservedRequest]]
    session_order: list[str]
    skipped_lines: int = 0
    invalid_records: int = 0
    files: int = 0
    auxiliary_excluded: int = 0

    def ordinals(self) -> dict[str, int]:
        return {key: index + 1 for index, key in enumerate(self.session_order)}


def _request_kind(record: dict[str, Any], bundle: ContextBundle) -> str:
    raw = record.get("request_kind")
    if isinstance(raw, str) and raw:
        return raw
    if bundle.provenance is not None and bundle.provenance.request_kind:
        return bundle.provenance.request_kind
    return PRIMARY_KIND


def load_spool(path: str | Path, *, primary_only: bool = True) -> DebuggerStore:
    """Load a spool file/dir of V2 JSONL captures into ordered session
    observations. Raw files are only read, never modified. V1 records
    are counted invalid, never coerced."""
    root = Path(path)
    if root.is_dir():
        records, stats = load_capture_dir(root)
    else:
        recs, skipped = load_capture_file(root)
        records, stats = recs, {"files": 1, "skipped_lines": skipped}
    tracker = SequenceTracker()
    grouped: dict[str, list[ObservedRequest]] = {}
    invalid = 0
    auxiliary = 0
    for record in records:
        if validate_record(record):
            invalid += 1
            continue
        bundle, invocation = ingest_record(record, tracker)
        kind = _request_kind(record, bundle)
        if primary_only and kind != PRIMARY_KIND:
            auxiliary += 1
            continue
        session = bundle.provenance.session_ref if bundle.provenance else None
        key = session if session else f"unlinked:{bundle.id}"
        agent = record.get("agent") if isinstance(record.get("agent"), str) else None
        limits = record.get("model_limits")
        grouped.setdefault(key, []).append(
            ObservedRequest(
                bundle=bundle,
                invocation=invocation,
                request_kind=kind,
                agent=agent,
                model_limits=dict(limits) if isinstance(limits, dict) else None,
            )
        )
    for ordered in grouped.values():
        ordered.sort(
            key=lambda r: (
                r.bundle.provenance.sequence_index
                if r.bundle.provenance and r.bundle.provenance.sequence_index is not None
                else 0,
                r.bundle.created_at,
                r.bundle.id,
            )
        )
    linked = sorted(k for k in grouped if not k.startswith("unlinked:"))
    unlinked = sorted(k for k in grouped if k.startswith("unlinked:"))
    return DebuggerStore(
        sessions={k: grouped[k] for k in linked + unlinked},
        session_order=linked,
        skipped_lines=stats["skipped_lines"],
        invalid_records=invalid,
        files=stats["files"],
        auxiliary_excluded=auxiliary,
    )


def composition(bundle: ContextBundle) -> list[CompositionSlice]:
    """Per-category structural composition of one bundle."""
    acc: dict[str, CompositionSlice] = {c: CompositionSlice(category=c) for c in CATEGORIES}
    for item in bundle.items:
        category = category_of(item.kind)
        current = acc[category]
        size = len(item.content.encode("utf-8"))
        acc[category] = CompositionSlice(
            category=category,
            items=current.items + 1,
            bytes=current.bytes + size,
            chars=current.chars + len(item.content),
            approx_tokens=current.approx_tokens + item.token_count,
        )
    return [acc[c] for c in CATEGORIES]


def totals(bundle: ContextBundle) -> dict[str, int]:
    return {
        "bytes": bundle_bytes(bundle),
        "chars": bundle_chars(bundle),
        "approx_tokens": sum(item.token_count for item in bundle.items),
        "items": len(bundle.items),
    }


def invocation_view(
    observed: ObservedRequest, *, session_ordinal: int, sequence: int
) -> InvocationView:
    bundle = observed.bundle
    invocation = observed.invocation
    parts = composition(bundle)
    size = totals(bundle)
    model = invocation.model if invocation.model != "unknown" else "unknown"
    return InvocationView(
        session_ordinal=session_ordinal,
        sequence=sequence,
        capture_id=bundle.provenance.capture_id if bundle.provenance else bundle.id,
        bundle_id=bundle.id,
        model=f"{invocation.provider} / {model}",
        provider=invocation.provider,
        agent=observed.agent,
        request_kind=observed.request_kind,
        created_at=bundle.created_at,
        composition=tuple(parts),
        total_bytes=size["bytes"],
        total_chars=size["chars"],
        total_approx_tokens=size["approx_tokens"],
        item_count=size["items"],
        model_limits=observed.model_limits,
    )


def _multiset(digests: list[str]) -> Counter[str]:
    return Counter(digests)


def membership_diff(earlier: ContextBundle, later: ContextBundle) -> dict[str, Any]:
    """Added/removed/unchanged item counts by content fingerprint
    (multiset). Order-insensitive; see compare for order/prefix."""
    first = _multiset([fingerprint(i.content) for i in earlier.items])
    second = _multiset([fingerprint(i.content) for i in later.items])
    unchanged = sum((first & second).values())
    added = sum((second - first).values())
    removed = sum((first - second).values())
    return {"unchanged": unchanged, "added": added, "removed": removed}


def compare_bundles(earlier: ContextBundle, later: ContextBundle) -> dict[str, Any]:
    """Structural comparison between two bundles of one session."""
    size_a = totals(earlier)
    size_b = totals(later)
    comp_a = {s.category: s for s in composition(earlier)}
    comp_b = {s.category: s for s in composition(later)}
    delta_before = {c: getattr(comp_a[c], "approx_tokens") for c in CATEGORIES}
    delta_after = {c: getattr(comp_b[c], "approx_tokens") for c in CATEGORIES}
    delta = {
        c: {
            "before": delta_before[c],
            "after": delta_after[c],
            "delta": delta_after[c] - delta_before[c],
        }
        for c in CATEGORIES
    }
    prefix = structural_shared_prefix(earlier, later)
    comparable = bool(prefix.get("comparable"))
    shared = int(prefix.get("shared_item_count") or 0) if comparable else 0
    later_items = len(later.items)
    prefix_ratio = (shared / later_items) if (comparable and later_items) else None
    first_divergence = prefix.get("first_divergence_index") if comparable else None
    membership = membership_diff(earlier, later)
    rep = repetition_between(earlier, later)
    size_keys = ("bytes", "chars", "approx_tokens", "items")
    size_delta = {k: size_b[k] - size_a[k] for k in size_keys}
    return {
        "size_before": size_a,
        "size_after": size_b,
        "size_delta": size_delta,
        "composition_delta": delta,
        "membership": membership,
        "shared_prefix_items": shared if comparable else None,
        "shared_prefix_ratio": prefix_ratio,
        "first_divergence": first_divergence,
        "prefix_comparable": comparable,
        "repeated_across": rep,
    }


def repetition_between(earlier: ContextBundle, later: ContextBundle) -> dict[str, Any]:
    """Byte-identical content recurring from the earlier bundle into the
    later one. Measurable recurrence — never a claim of redundancy."""
    seen = {fingerprint(i.content) for i in earlier.items}
    repeated_items = 0
    repeated_bytes = 0
    for item in later.items:
        if fingerprint(item.content) in seen:
            repeated_items += 1
            repeated_bytes += len(item.content.encode("utf-8"))
    return {"repeated_items": repeated_items, "repeated_bytes": repeated_bytes}


def within_repetition(bundle: ContextBundle) -> dict[str, Any]:
    seen: set[str] = set()
    duplicates = 0
    duplicate_bytes = 0
    for item in bundle.items:
        digest = fingerprint(item.content)
        if digest in seen:
            duplicates += 1
            duplicate_bytes += len(item.content.encode("utf-8"))
        else:
            seen.add(digest)
    return {"duplicate_items": duplicates, "duplicate_bytes": duplicate_bytes}


def largest_contributors(bundle: ContextBundle, limit: int = 5) -> list[dict[str, Any]]:
    ranked = sorted(bundle.items, key=lambda i: len(i.content.encode("utf-8")), reverse=True)[
        :limit
    ]
    out = []
    for item in ranked:
        out.append(
            {
                "position": item.position,
                "kind": item.kind,
                "category": category_of(item.kind),
                "bytes": len(item.content.encode("utf-8")),
                "approx_tokens": item.token_count,
                "ref": item.ref,
            }
        )
    return out


def item_history(
    sessions: dict[str, list[ObservedRequest]], session_key: str, item_id: str
) -> dict[str, Any] | None:
    """Trace one item across its session: first observation, recurrences
    of byte-identical content, position movement, stable-prefix status."""
    ordered = sessions.get(session_key)
    if not ordered:
        return None
    target = None
    target_bundle_index = None
    for index, observed in enumerate(ordered):
        for item in observed.bundle.items:
            if item.id == item_id:
                target = item
                target_bundle_index = index
                break
        if target is not None:
            break
    if target is None or target_bundle_index is None:
        return None
    digest = fingerprint(target.content)
    first_seen: int | None = None
    recurrences: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    for index, observed in enumerate(ordered):
        matches = [i for i in observed.bundle.items if fingerprint(i.content) == digest]
        if matches:
            sequence = _sequence_of(observed, index)
            if first_seen is None:
                first_seen = sequence
            recurrences.append(sequence)
            for match in matches:
                positions.append({"sequence": sequence, "position": match.position})
    in_prefix = _in_stable_prefix(ordered[target_bundle_index].bundle, target)
    return {
        "item_id": target.id,
        "kind": target.kind,
        "category": category_of(target.kind),
        "position": target.position,
        "bundle_items": len(ordered[target_bundle_index].bundle.items),
        "bytes": len(target.content.encode("utf-8")),
        "approx_tokens": target.token_count,
        "token_provenance": target.token_provenance,
        "ref": target.ref,
        "sequence": _sequence_of(ordered[target_bundle_index], target_bundle_index),
        "first_seen_sequence": first_seen,
        "recurrence_sequences": recurrences,
        "recurrence_count": len(recurrences),
        "positions": positions,
        "in_stable_prefix": in_prefix,
    }


def _sequence_of(observed: ObservedRequest, index: int) -> int:
    if observed.bundle.provenance and observed.bundle.provenance.sequence_index is not None:
        return observed.bundle.provenance.sequence_index
    return index + 1


def _in_stable_prefix(bundle: ContextBundle, target: Any) -> bool | None:
    # Single-bundle view: prefix status is relative to the previous
    # bundle, resolved by callers. Here: whether the item sits at
    # position 0..k contiguous from start is unknowable alone -> None
    # unless it is the first item.
    _ = bundle
    if target.position == 0:
        return True
    return None


def session_growth_multiple(ordered: list[ObservedRequest]) -> float | None:
    if len(ordered) < 2:
        return None
    first = bundle_bytes(ordered[0].bundle)
    last = bundle_bytes(ordered[-1].bundle)
    if first == 0:
        return None
    return last / first


def tool_surface_change(earlier: ContextBundle, later: ContextBundle) -> dict[str, Any]:
    before = sorted(i.ref for i in earlier.items if i.kind == "tool_definition" and i.ref)
    after = sorted(i.ref for i in later.items if i.kind == "tool_definition" and i.ref)
    before_set, after_set = set(before), set(after)
    return {
        "before": len(before),
        "after": len(after),
        "added": sorted(after_set - before_set),
        "removed": sorted(before_set - after_set),
    }


def describe_unobserved() -> list[str]:
    from project_context.debugger.domain import UNOBSERVED_CATEGORIES

    return list(UNOBSERVED_CATEGORIES)


def capture_boundary() -> str:
    return CAPTURE_STAGE_V2


def structural_json_ready(value: Any) -> Any:
    """Round-trip helper keeping debugger JSON deterministic."""
    return json.loads(json.dumps(value, sort_keys=True))
