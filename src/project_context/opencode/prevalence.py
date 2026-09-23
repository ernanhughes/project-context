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


def export_report(report: dict[str, Any]) -> dict[str, Any]:
    """Produce a publishable aggregate: session-keyed growth series are
    re-keyed to opaque ordinals (shape preserved, identities removed).
    Everything else in our analyses is already aggregate numerics."""
    exported = json.loads(json.dumps(report, sort_keys=True))
    growth = exported.get("growth_by_session")
    if isinstance(growth, dict):
        relabelled = {}
        for index, key in enumerate(sorted(growth), start=1):
            relabelled[f"session-{index:03d}"] = growth[key]
        exported["growth_by_session"] = relabelled
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
                if str(key).lower() == "growth_by_session" and isinstance(value, dict):
                    for sub in value:
                        if not re.fullmatch(r"session-\d{3}", str(sub)):
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
