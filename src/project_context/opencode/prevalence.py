"""Ecological prevalence analysis over ingested OpenCode captures.

Aggregates only. No function here returns raw content, identifiers, or
hashes; export candidates pass through `assert_exportable`, which rejects
anything but aggregate numerics plus version metadata. A smoke capture is
labelled smoke; prevalence claims require a corpus (see the collection
protocol in specs/opencode-capture-protocol.md).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from project_context.corpus.manifest import scan_text_for_secrets
from project_context.domain.bundles import ContextBundle

ANALYSER_VERSION = "0.1.0"

UNOBSERVED = "UNOBSERVED"
"""First-class unobserved marker. Rendered in reports wherever the V1
boundary cannot see a category (e.g. tool definitions). Never zero."""


def dist(values: list[float]) -> dict[str, Any]:
    """Distribution summary. High percentiles only with n>=20; small
    samples report min/median/max to avoid implying population precision."""
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    summary: dict[str, Any] = {
        "n": len(ordered),
        "min": ordered[0],
        "median": ordered[len(ordered) // 2],
        "max": ordered[-1],
    }
    if len(ordered) >= 20:
        summary["p75"] = ordered[int(len(ordered) * 0.75)]
        summary["p90"] = ordered[int(len(ordered) * 0.90)]
    return summary


def fingerprint(text: str) -> str:
    """Canonical local fingerprint for repetition analysis. Local-only:
    fingerprints must never appear in exported reports."""
    normalised = " ".join(text.split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def bundle_bytes(bundle: ContextBundle) -> int:
    return sum(len(item.content.encode("utf-8")) for item in bundle.items)


def bundle_chars(bundle: ContextBundle) -> int:
    return sum(len(item.content) for item in bundle.items)


def _kind_of(item: Any) -> str:
    return str(item.kind)


ROLE_CATEGORIES = (
    "system",
    "user",
    "assistant",
    "tool_call",
    "tool_result",
    "other",
)


def role_of_kind(kind: str) -> str:
    """Map ingester kinds to prevalence roles. Unknown kinds fall into
    other/opaque; never inferred beyond the mapping."""
    mapping = {
        "system_instruction": "system",
        "conversation_user": "user",
        "conversation_assistant": "assistant",
        "text_part": "other",
        "reasoning_part": "assistant",
        "tool_call": "tool_call",
        "tool_result": "tool_result",
        "other_message_part": "other",
    }
    return mapping.get(kind, "other")


def composition_report(bundles: list[ContextBundle]) -> dict[str, Any]:
    """Share by role category in bytes, chars, and item counts. Tool
    definitions are UNOBSERVED at the V1 boundary: reported as such,
    never as zero."""
    bytes_by_role: Counter[str] = Counter()
    items_by_role: Counter[str] = Counter()
    for bundle in bundles:
        for item in bundle.items:
            role = role_of_kind(item.kind)
            size = len(item.content.encode("utf-8"))
            bytes_by_role[role] += size
            items_by_role[role] += 1
    total = sum(bytes_by_role.values())
    return {
        "analyser_version": ANALYSER_VERSION,
        "bytes_by_role": dict(sorted(bytes_by_role.items())),
        "items_by_role": dict(sorted(items_by_role.items())),
        "total_bytes": total,
        "tool_definitions": UNOBSERVED,
        "tool_definitions_note": (
            "Tool definitions are not exposed by the OpenCode 1.18.27/V1 "
            "public hook boundary; unobserved is not zero."
        ),
    }


def analyse_bundles(bundles: list[ContextBundle]) -> dict[str, Any]:
    """Aggregate structural analysis. Returned dict contains numerics,
    category labels, and version metadata only."""
    by_kind_bytes: Counter[str] = Counter()
    by_kind_items: Counter[str] = Counter()
    by_source_bytes: Counter[str] = Counter()
    sizes: list[int] = []
    per_session_sizes: dict[str, list[int]] = {}
    sessions: set[str] = set()
    tool_result_bytes = 0
    system_bytes = 0

    for bundle in bundles:
        size = bundle_bytes(bundle)
        sizes.append(size)
        for item in bundle.items:
            by_kind_bytes[_kind_of(item)] += len(item.content.encode("utf-8"))
            by_kind_items[_kind_of(item)] += 1
            by_source_bytes[str(item.source)] += len(item.content.encode("utf-8"))
            if item.kind == "tool_result":
                tool_result_bytes += len(item.content.encode("utf-8"))
            if item.kind == "system_instruction":
                system_bytes += len(item.content.encode("utf-8"))
        session = None
        if bundle.provenance is not None:
            session = bundle.provenance.session_ref
        if session:
            sessions.add(session)
            per_session_sizes.setdefault(session, []).append(size)

    growth: dict[str, Any] = {}
    for session, ordered in per_session_sizes.items():
        deltas = [later - earlier for earlier, later in zip(ordered, ordered[1:])]
        growth[session] = {
            "invocations": len(ordered),
            "sizes": ordered,
            "deltas": deltas,
        }

    total = sum(sizes)
    return {
        "analyser_version": ANALYSER_VERSION,
        "bundles": len(bundles),
        "sessions_observed": len(sessions),
        "total_bytes": total,
        "size_min": min(sizes) if sizes else 0,
        "size_max": max(sizes) if sizes else 0,
        "size_mean": (total / len(sizes)) if sizes else 0,
        "bytes_by_kind": dict(sorted(by_kind_bytes.items())),
        "items_by_kind": dict(sorted(by_kind_items.items())),
        "bytes_by_source": dict(sorted(by_source_bytes.items())),
        "tool_result_bytes": tool_result_bytes,
        "system_bytes": system_bytes,
        "growth_by_session": growth,
    }


def repetition_report(bundles: list[ContextBundle]) -> dict[str, Any]:
    """Within-bundle duplicates and cross-turn recurrences, counted via
    local fingerprints. Returns counts and byte totals only."""
    within_duplicates = 0
    within_bytes = 0
    seen_global: dict[str, int] = {}
    for bundle in bundles:
        seen_local: set[str] = set()
        for item in bundle.items:
            digest = fingerprint(item.content)
            size = len(item.content.encode("utf-8"))
            if digest in seen_local:
                within_duplicates += 1
                within_bytes += size
            else:
                seen_local.add(digest)
            seen_global[digest] = seen_global.get(digest, 0) + 1
    recurring = sum(1 for count in seen_global.values() if count > 1)
    return {
        "analyser_version": ANALYSER_VERSION,
        "within_bundle_duplicate_items": within_duplicates,
        "within_bundle_duplicate_bytes": within_bytes,
        "distinct_contents": len(seen_global),
        "recurring_contents": recurring,
    }


def structural_shared_prefix(earlier: ContextBundle, later: ContextBundle) -> dict[str, Any]:
    """Provider-neutral shared-prefix measurement over item content
    fingerprints. This is structural reuse at the observer boundary, NOT
    a provider cache hit (book Chapter 9). Requires both bundles to carry
    the same non-null session scope; otherwise refuses with a reason."""
    scope_a = earlier.provenance.session_ref if earlier.provenance else None
    scope_b = later.provenance.session_ref if later.provenance else None
    if not scope_a or scope_a != scope_b:
        return {
            "comparable": False,
            "reason": "different or missing session scope; no shared-prefix claim",
        }
    first = [fingerprint(item.content) for item in earlier.items]
    second = [fingerprint(item.content) for item in later.items]
    shared = 0
    for left, right in zip(first, second):
        if left != right:
            break
        shared += 1
    shared_bytes = sum(len(item.content.encode("utf-8")) for item in later.items[:shared])
    return {
        "comparable": True,
        "shared_item_count": shared,
        "shared_bytes": shared_bytes,
        "first_divergence_index": shared if shared < len(second) else None,
        "earlier_items": len(first),
        "later_items": len(second),
    }


EXPORT_NOTE = (
    "Session identifiers are removed by export_report before gating; "
    "assert_exportable verifies the exported shape only."
)


SESSION_SECTIONS = (
    "growth_by_session",
    "timelines",
    "churn_positions",
    "prefix_survival",
    "durations_minutes",
)


def export_report(report: dict[str, Any]) -> dict[str, Any]:
    """Produce a publishable aggregate: session-keyed mappings are
    re-keyed to opaque publication ids (S01, S02, ...) shared across
    sections so series stay joinable without identities."""
    exported = json.loads(json.dumps(report, sort_keys=True))
    union: list[str] = []
    for section in SESSION_SECTIONS:
        mapping = exported.get(section)
        if isinstance(mapping, dict):
            for key in mapping:
                if key not in union:
                    union.append(key)
    relabel = {key: f"S{i:02d}" for i, key in enumerate(sorted(union), start=1)}
    for section in SESSION_SECTIONS:
        mapping = exported.get(section)
        if isinstance(mapping, dict):
            exported[section] = {
                relabel.get(key, f"S00-{index}"): value
                for index, (key, value) in enumerate(sorted(mapping.items()))
            }
    return exported


FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "content",
        "text",
        "prompt",
        "secret",
        "digest",
        "sha256",
        "hash",
        "fingerprint",
        "session_id",
        "message_id",
        "call_id",
    }
)


def assert_exportable(report: dict[str, Any]) -> list[str]:
    """Gate for anything leaving the machine. Rejects exact structural
    markers of raw content, identifiers, hashes, and secrets. Call on
    export_report() output. Returns error strings; empty means
    exportable."""
    errors: list[str] = []
    blob = json.dumps(report, sort_keys=True)
    text_keys: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).lower() in FORBIDDEN_FIELD_NAMES:
                    text_keys.append(path + "/" + str(key))
                if str(key).lower() in SESSION_SECTIONS and isinstance(value, dict):
                    for sub in value:
                        if not re.fullmatch(r"S\d{2}", str(sub)):
                            text_keys.append(f"{path}/{key}/{sub} (unrelabelled session)")
                walk(value, path + "/" + str(key))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(report, "")
    if text_keys:
        errors.append(f"report carries non-aggregate fields: {sorted(set(text_keys))[:8]}")
    if scan_text_for_secrets(blob):
        errors.append("report matches secret patterns")
    return errors


def session_bundles(
    bundles: list[ContextBundle],
) -> dict[str, list[ContextBundle]]:
    """Group bundles by session scope. Unlinked bundles (no session_ref)
    are returned under their own per-bundle scope so they never merge
    into a fictitious session."""
    grouped: dict[str, list[ContextBundle]] = {}
    for bundle in bundles:
        session = bundle.provenance.session_ref if bundle.provenance else None
        key = session if session else f"unlinked:{bundle.id}"
        grouped.setdefault(key, []).append(bundle)
    return grouped


def session_timeline(session: str, ordered: list[ContextBundle]) -> list[dict[str, object]]:
    """Per-invocation structural timeline: sizes, composition, novelty,
    and shared prefix against the previous bundle. Content-free."""
    seen: set[str] = set()
    timeline: list[dict[str, object]] = []
    previous: ContextBundle | None = None
    for index, bundle in enumerate(ordered):
        kinds: dict[str, int] = {}
        new_bytes = 0
        size = 0
        for item in bundle.items:
            size += len(item.content.encode("utf-8"))
            kinds[item.kind] = kinds.get(item.kind, 0) + 1
            digest = fingerprint(item.content)
            if digest not in seen:
                new_bytes += len(item.content.encode("utf-8"))
                seen.add(digest)
        prefix = structural_shared_prefix(previous, bundle) if previous else None
        timeline.append(
            {
                "invocation_index": index + 1,
                "items": len(bundle.items),
                "bytes": size,
                "chars": bundle_chars(bundle),
                "kinds": kinds,
                "new_bytes": new_bytes,
                "shared_prefix": prefix,
            }
        )
        previous = bundle
    _ = session
    return timeline


def churn_positions(ordered: list[ContextBundle]) -> list[float | None]:
    """Normalised first-divergence position per consecutive pair: 0.0 at
    the beginning, 1.0 at the end, None when fully identical."""
    positions: list[float | None] = []
    for earlier, later in zip(ordered, ordered[1:]):
        result = structural_shared_prefix(earlier, later)
        if not result.get("comparable"):
            positions.append(None)
            continue
        later_items = result.get("later_items") or 0
        if later_items == 0:
            positions.append(None)
            continue
        shared = result.get("shared_item_count") or 0
        if shared >= later_items:
            positions.append(None)
        else:
            positions.append(shared / later_items)
    return positions


def prefix_survival(ordered: list[ContextBundle], horizon: int) -> int | None:
    """Longest shared prefix surviving across the first `horizon`
    invocations: the minimum consecutive shared-item count. None when
    the session is shorter than the horizon or scopes refuse."""
    if len(ordered) < horizon or horizon < 2:
        return None
    shared_counts: list[int] = []
    for earlier, later in zip(ordered[:horizon], ordered[1:horizon]):
        result = structural_shared_prefix(earlier, later)
        if not result.get("comparable"):
            return None
        shared_counts.append(int(result.get("shared_item_count") or 0))
    return min(shared_counts) if shared_counts else None


def tool_result_stats(bundles: list[ContextBundle]) -> dict[str, object]:
    """Tool-result prevalence: counts, bytes, share, growth, largest
    item, recurrence. Contents never leave this function except as
    numbers; tool arguments and paths are not separate fields anywhere
    in Stage 1 records."""
    sizes: list[int] = []
    largest = 0
    seen: set[str] = set()
    recurring_bytes = 0
    for bundle in bundles:
        for item in bundle.items:
            if item.kind != "tool_result":
                continue
            size = len(item.content.encode("utf-8"))
            sizes.append(size)
            largest = max(largest, size)
            digest = fingerprint(item.content)
            if digest in seen:
                recurring_bytes += size
            else:
                seen.add(digest)
    total_tool = sum(sizes)
    return {
        "analyser_version": ANALYSER_VERSION,
        "items": len(sizes),
        "bytes": total_tool,
        "size_dist": dist([float(v) for v in sizes]),
        "largest_item_bytes": largest,
        "recurring_bytes": recurring_bytes,
        "distinct_payloads": len(seen),
    }


def session_weighted_tool_share(
    sessions: dict[str, list[ContextBundle]],
) -> dict[str, object]:
    """Tool-result byte share computed two ways. Invocation-weighted
    divides global tool bytes by global bytes (long sessions dominate).
    Session-weighted averages per-session shares (each session one vote).
    Both denominators are stated; neither is 'the' share."""
    global_tool = 0
    global_total = 0
    per_session: list[float] = []
    for ordered in sessions.values():
        session_tool = 0
        session_total = 0
        for bundle in ordered:
            for item in bundle.items:
                size = len(item.content.encode("utf-8"))
                session_total += size
                if item.kind == "tool_result":
                    session_tool += size
        global_tool += session_tool
        global_total += session_total
        if session_total > 0:
            per_session.append(session_tool / session_total)
    return {
        "analyser_version": ANALYSER_VERSION,
        "invocation_weighted_share": (global_tool / global_total) if global_total else 0.0,
        "session_weighted_share": (sum(per_session) / len(per_session)) if per_session else 0.0,
        "sessions": len(per_session),
    }


def duration_minutes(records: list[dict[str, object]]) -> float | None:
    """Normalised duration between first and last capture timestamps in
    a session's records. Absolute timestamps never leave the spool;
    only this duration may be exported."""
    stamps: list[str] = []
    for record in records:
        captured = record.get("captured_at")
        if isinstance(captured, str):
            stamps.append(captured)
    if len(stamps) < 2:
        return None
    try:
        from datetime import datetime, timezone

        parsed = [
            datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
            for s in stamps
        ]
    except ValueError:
        return None
    delta = (max(parsed) - min(parsed)).total_seconds() / 60.0
    return max(0.0, delta)
