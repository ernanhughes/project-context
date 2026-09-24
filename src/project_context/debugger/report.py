"""Debugger reporting: deterministic text (humans) and JSON (future UI).

Default output is structural only: no raw content, no raw session
identifiers, no hashes. Raw content requires show_content=True (explicit
local flag); raw identifiers require include_identifiers=True.
"""

from __future__ import annotations

from typing import Any

from project_context.debugger.analyse import (
    ObservedRequest,
    _sequence_of,
    compare_bundles,
    composition,
    invocation_view,
    item_history,
    largest_contributors,
    session_growth_multiple,
    totals,
    within_repetition,
)
from project_context.debugger.doctor import doctor_invocation, doctor_session
from project_context.debugger.domain import (
    DEBUGGER_VERSION,
    OBSERVED_BOUNDARY,
    OBSERVED_BOUNDARY_NOTE,
    UNOBSERVED_CATEGORIES,
    DoctorReport,
    Observation,
)
from project_context.debugger.query import summarise
from project_context.opencode.prevalence import bundle_bytes, structural_shared_prefix


def _rule(width: int = 56) -> str:
    return "-" * width


def _fmt_tokens(value: int) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def report_latest(
    session_key: str,
    ordinal: int,
    ordered: list[ObservedRequest],
    *,
    thresholds: dict[str, float] | None = None,
) -> tuple[str, dict[str, Any]]:
    index = len(ordered) - 1
    observed = ordered[index]
    sequence = _sequence_of(observed, index)
    view = invocation_view(observed, session_ordinal=ordinal, sequence=sequence)
    bundle = observed.bundle
    size = totals(bundle)
    comp = {s.category: s for s in composition(bundle)}
    doc: dict[str, Any] = view.to_dict()
    if index > 0:
        previous = ordered[index - 1]
        cmp = compare_bundles(previous.bundle, bundle)
        doc["change_since_previous"] = cmp
        prefix_ratio = cmp["shared_prefix_ratio"]
        first_div = cmp["first_divergence"]
    else:
        doc["change_since_previous"] = None
        prefix_ratio = None
        first_div = None
    rep = within_repetition(bundle)
    doc["repeated_content"] = rep
    doc["largest_contributors"] = largest_contributors(bundle)
    observations = doctor_invocation(ordered, index, thresholds=thresholds)
    doc["observations"] = [o.to_dict() for o in observations]
    doc["not_assessed"] = ["relevance", "usefulness", "behavioural harm", "safe removability"]
    doc["context_modified"] = False

    lines = [
        "Context Debugger",
        _rule(),
        "",
        "Boundary",
        f"  {OBSERVED_BOUNDARY}",
        "  NOT provider wire payload",
        "",
        f"Session        local:{ordinal}",
        f"Invocation     {_sequence_of(observed, index)}",
        f"Model          {view.model}",
        f"Agent          {view.agent or 'unknown'}",
        "",
        "Observed context",
    ]
    display_order = (
        "system",
        "user",
        "assistant",
        "tool_definition",
        "tool_call",
        "tool_result",
        "other",
    )
    for category in display_order:
        sl = comp[category]
        lines.append(f"  {category:22s} {sl.approx_tokens:8d} approx. tokens")
    lines += [
        "                               " + "-" * 7,
        f"  {'total':22s} {size['approx_tokens']:8d} approx.",
        "",
        f"Exact size     {size['bytes']} bytes / {size['chars']} chars",
        "Token provenance  approximation",
        "",
    ]
    if index > 0:
        assert doc["change_since_previous"] is not None
        delta = doc["change_since_previous"]["size_delta"]
        membership = doc["change_since_previous"]["membership"]
        lines += [
            "Change since previous invocation",
            f"  {delta['approx_tokens']:+d} approx. tokens",
            f"  +{membership['added']} items / -{membership['removed']} items",
        ]
        if prefix_ratio is not None:
            lines.append(f"  stable prefix: {prefix_ratio:.0%}")
        if first_div is not None:
            lines.append(f"  first divergence: item {first_div}")
        lines.append("")
    lines += [
        "Observed conditions",
    ]
    if observations:
        for obs in observations:
            lines.append(f"  {obs.code:22s} {obs.measurement}")
    else:
        lines.append("  none surfaced under current thresholds")
    lines += [
        "",
        "Unobserved",
    ]
    for category in UNOBSERVED_CATEGORIES:
        lines.append(f"  {category}")
    lines += [
        "",
        "No context was modified.",
        "",
    ]
    return "\n".join(lines), doc


def report_inspect(
    session_key: str,
    ordinal: int,
    ordered: list[ObservedRequest],
    sequence: int,
    *,
    show_content: bool = False,
) -> tuple[str, dict[str, Any]]:
    found = next((o for i, o in enumerate(ordered) if _sequence_of(o, i) == sequence), None)
    if found is None:
        raise ValueError(f"unknown invocation sequence: {sequence}")
    view = invocation_view(found, session_ordinal=ordinal, sequence=sequence)
    bundle = found.bundle
    rows = []
    for item in bundle.items:
        rows.append(
            {
                "position": item.position,
                "kind": item.kind,
                "bytes": len(item.content.encode("utf-8")),
                "approx_tokens": item.token_count,
                "token_provenance": item.token_provenance,
                "ref": item.ref,
                **({"content": item.content} if show_content else {}),
            }
        )
    doc: dict[str, Any] = view.to_dict()
    doc["items"] = rows
    doc["content_shown"] = show_content
    doc["context_modified"] = False

    lines = [
        "Context Debugger — inspect",
        _rule(),
        f"Session local:{ordinal}  invocation {sequence}",
        f"Model {view.model}  agent {view.agent or 'unknown'}",
        f"Boundary {OBSERVED_BOUNDARY} (NOT provider wire payload)",
        "",
        f"Items: {len(rows)}",
    ]
    for row in rows:
        lines.append(
            f"  [{row['position']:3d}] {row['kind']:22s} "
            f"{row['bytes']:7d} B  {row['approx_tokens']:6d} approx.  ref={row['ref']}"
        )
        if show_content:
            preview = str(row.get("content", ""))[:200].replace("\n", "\\n")
            lines.append(f"         content: {preview}")
    if show_content:
        lines += ["", "WARNING: raw content printed locally only. Never share this output."]
    lines += ["", "No context was modified.", ""]
    return "\n".join(lines), doc


def report_timeline(
    session_key: str, ordinal: int, ordered: list[ObservedRequest]
) -> tuple[str, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    from project_context.opencode.prevalence import fingerprint as _fp

    previous = None
    for index, observed in enumerate(ordered):
        sequence = _sequence_of(observed, index)
        bundle = observed.bundle
        size = totals(bundle)
        new_bytes = 0
        for item in bundle.items:
            digest = _fp(item.content)
            if digest not in seen:
                new_bytes += len(item.content.encode("utf-8"))
                seen.add(digest)
        comp = {s.category: s for s in composition(bundle)}
        tool_def = comp["tool_definition"].bytes
        tool_res = comp["tool_result"].bytes
        rep = within_repetition(bundle)
        prefix = structural_shared_prefix(previous, bundle) if previous else None
        if prefix and prefix.get("comparable") and len(bundle.items):
            ratio = (int(prefix.get("shared_item_count") or 0)) / len(bundle.items)
            first_div = prefix.get("first_divergence_index")
        else:
            ratio, first_div = None, None
        delta = None
        if previous is not None:
            delta = bundle_bytes(bundle) - bundle_bytes(previous)
        rows.append(
            {
                "sequence": sequence,
                "items": len(bundle.items),
                "bytes": size["bytes"],
                "approx_tokens": size["approx_tokens"],
                "delta_bytes": delta,
                "new_bytes": new_bytes,
                "tool_definition_bytes": tool_def,
                "tool_result_bytes": tool_res,
                "repeated_bytes": rep["duplicate_bytes"],
                "shared_prefix_ratio": ratio,
                "first_divergence": first_div,
            }
        )
        previous = bundle
    growth = session_growth_multiple(ordered)
    doc = {
        "debugger_version": DEBUGGER_VERSION,
        "session_ordinal": ordinal,
        "boundary": OBSERVED_BOUNDARY,
        "growth_multiple": growth,
        "turns": rows,
        "context_modified": False,
    }
    lines = [
        "Context Debugger — timeline",
        _rule(),
        f"Session local:{ordinal}  turns: {len(rows)}",
        f"Boundary {OBSERVED_BOUNDARY} (NOT provider wire payload)",
        "",
        f"  {'turn':>4}  {'bytes':>8}  {'delta':>8}  {'new':>8}  {'prefix':>7}  tokens",
    ]
    for row in rows:
        delta = "-" if row["delta_bytes"] is None else f"{row['delta_bytes']:+d}"
        prefix = "-" if row["shared_prefix_ratio"] is None else f"{row['shared_prefix_ratio']:.0%}"
        lines.append(
            f"  {row['sequence']:>4}  {row['bytes']:>8d}  {delta:>8}  "
            f"{row['new_bytes']:>8d}  {prefix:>7}  {row['approx_tokens']} approx."
        )
    lines += ["", "No context was modified.", ""]
    return "\n".join(lines), doc


def report_compare(
    ordinal: int,
    ordered: list[ObservedRequest],
    sequence_a: int,
    sequence_b: int,
) -> tuple[str, dict[str, Any]]:
    def find(sequence: int) -> ObservedRequest:
        for i, o in enumerate(ordered):
            if _sequence_of(o, i) == sequence:
                return o
        raise ValueError(f"unknown invocation sequence: {sequence}")

    earlier, later = find(sequence_a), find(sequence_b)
    cmp = compare_bundles(earlier.bundle, later.bundle)
    from project_context.debugger.analyse import tool_surface_change

    surface = tool_surface_change(earlier.bundle, later.bundle)
    cmp["tool_surface"] = surface
    doc = {
        "debugger_version": DEBUGGER_VERSION,
        "session_ordinal": ordinal,
        "sequence_a": sequence_a,
        "sequence_b": sequence_b,
        "comparison": cmp,
        "boundary": OBSERVED_BOUNDARY,
        "boundary_note": OBSERVED_BOUNDARY_NOTE,
        "cache_claim": "No claim is made about provider cache behaviour.",
        "context_modified": False,
    }
    size_a, size_b = cmp["size_before"], cmp["size_after"]
    size_delta = size_b["bytes"] - size_a["bytes"]
    lines = [
        "Context Debugger — compare",
        _rule(),
        f"Session local:{ordinal}  #{sequence_a} vs #{sequence_b}",
        "",
        f"  {'':22s} {'before':>8}  {'after':>8}  delta",
        f"  {'bytes':22s} {size_a['bytes']:>8d}  {size_b['bytes']:>8d}  {size_delta:+d}",
        f"  {'approx tokens':22s} {size_a['approx_tokens']:>8d}  "
        f"{size_b['approx_tokens']:>8d}  {size_b['approx_tokens'] - size_a['approx_tokens']:+d}",
        f"  {'items':22s} {size_a['items']:>8d}  {size_b['items']:>8d}  "
        f"{size_b['items'] - size_a['items']:+d}",
        "",
        "Membership (by exact content identity)",
        f"  unchanged: {cmp['membership']['unchanged']}",
        f"  added:     {cmp['membership']['added']}",
        f"  removed:   {cmp['membership']['removed']}",
        "",
    ]
    if cmp["prefix_comparable"]:
        ratio = cmp["shared_prefix_ratio"]
        lines.append(f"Shared prefix  {ratio:.0%}" if ratio is not None else "Shared prefix  n/a")
        lines.append(f"First divergence  item {cmp['first_divergence']}")
    else:
        lines.append("Shared prefix  not comparable (scope refused)")
    lines += [
        f"Tool surface  {surface['before']} -> {surface['after']} definitions",
    ]
    if surface["added"]:
        lines.append(f"  added: {', '.join(surface['added'])}")
    if surface["removed"]:
        lines.append(f"  removed: {', '.join(surface['removed'])}")
    lines += [
        "",
        "No claim is made about provider cache behaviour.",
        "No context was modified.",
        "",
    ]
    return "\n".join(lines), doc


def report_explain(
    session_key: str,
    ordinal: int,
    ordered: list[ObservedRequest],
    item_id: str,
) -> tuple[str, dict[str, Any]]:
    history = item_history({"s": ordered} | {session_key: ordered}, session_key, item_id)
    if history is None:
        raise ValueError(f"unknown item: {item_id}")
    from project_context.debugger.domain import EPISTEMIC_KNOWN, EPISTEMIC_UNKNOWN

    doc = {
        "debugger_version": DEBUGGER_VERSION,
        "session_ordinal": ordinal,
        "item": {k: v for k, v in history.items() if k != "positions"},
        "positions": history["positions"],
        "known": list(EPISTEMIC_KNOWN),
        "unknown": list(EPISTEMIC_UNKNOWN),
        "boundary": OBSERVED_BOUNDARY,
        "context_modified": False,
    }
    lines = [
        "Context Debugger — explain",
        _rule(),
        "Item",
        f"  kind: {history['kind']}",
        f"  position: {history['position']} / {history['bundle_items']}",
        f"  approx tokens: {history['approx_tokens']} [approximation]",
        f"  bytes: {history['bytes']}",
        "",
        "Origin",
        f"  {OBSERVED_BOUNDARY}",
        f"  session: local:{ordinal}",
        f"  invocation: {history['sequence']}",
        f"  ref: {history['ref']}",
        "",
        "History",
        f"  first observed: invocation {history['first_seen_sequence']}",
        f"  recurrences: {history['recurrence_sequences']}",
        f"  occurrences: {history['recurrence_count']}",
        "",
        "Known",
    ]
    for known in EPISTEMIC_KNOWN:
        lines.append(f"  {known}")
    lines.append("")
    lines.append("Unknown")
    for unknown in EPISTEMIC_UNKNOWN:
        lines.append(f"  {unknown}")
    lines += ["", "No context was modified.", ""]
    return "\n".join(lines), doc


def report_query(
    ordinal: int, results: list[dict[str, Any]], summary: dict[str, Any], describe: str
) -> tuple[str, dict[str, Any]]:
    doc = {
        "debugger_version": DEBUGGER_VERSION,
        "session_ordinal": ordinal,
        "filter": describe,
        "summary": summarise(results) | summary,
        "items": [{k: v for k, v in r.items() if k != "content"} for r in results],
        "token_provenance": "approximation",
        "context_modified": False,
    }
    total = summarise(results)
    lines = [
        "Context Debugger — query",
        _rule(),
        f"Session local:{ordinal}  filter: {describe}",
        "",
        f"{total['items']} items  {total['approx_tokens']} approx. tokens  "
        f"{total['bytes']} bytes  largest {total['largest_bytes']} bytes",
    ]
    for row in results[:50]:
        lines.append(
            f"  seq={row['sequence']} pos={row['position']} {row['kind']:22s} "
            f"{row['bytes']} B ref={row['ref']} x{row['recurrences']}"
        )
    if len(results) > 50:
        lines.append(f"  ... and {len(results) - 50} more (see JSON)")
    lines += ["", "No context was modified.", ""]
    return "\n".join(lines), doc


def report_doctor(
    ordinal: int,
    ordered: list[ObservedRequest],
    *,
    sequence: int | None = None,
    thresholds: dict[str, float] | None = None,
) -> tuple[str, dict[str, Any]]:
    observations: list[Observation] = []
    if sequence is None:
        observations.extend(doctor_session(ordered, thresholds=thresholds))
        for index in range(len(ordered)):
            observations.extend(doctor_invocation(ordered, index, thresholds=thresholds))
        scope = "session"
    else:
        index = next((i for i, o in enumerate(ordered) if _sequence_of(o, i) == sequence), None)
        if index is None:
            raise ValueError(f"unknown invocation sequence: {sequence}")
        observations.extend(doctor_invocation(ordered, index, thresholds=thresholds))
        scope = f"invocation {sequence}"
    # De-duplicate by (code, measurement) preserving order.
    seen: set[tuple[str, str]] = set()
    unique: list[Observation] = []
    for obs in observations:
        key = (obs.code, obs.measurement)
        if key not in seen:
            seen.add(key)
            unique.append(obs)
    report = DoctorReport(session_ordinal=ordinal, sequence=sequence, observations=tuple(unique))
    doc = report.to_dict()
    doc["scope"] = scope
    doc["context_modified"] = False
    lines = [
        "Context Debugger — doctor",
        _rule(),
        f"Session local:{ordinal}  scope: {scope}",
        f"Boundary {OBSERVED_BOUNDARY} (NOT provider wire payload)",
        "",
        "Observed conditions",
        "",
    ]
    if unique:
        for obs in unique:
            lines.append(f"{obs.prominence:7s}  {obs.code}")
            lines.append(f"         {obs.measurement}")
            if obs.investigation:
                lines.append(f"         {obs.investigation} (intervention earned: NO)")
    else:
        lines.append("  none surfaced under current thresholds")
    lines += [
        "",
        "Not assessed",
        "  relevance",
        "  usefulness",
        "  behavioural harm",
        "  safe removability",
        "",
        "Observations, not recommendations. No context was modified.",
        "",
    ]
    return "\n".join(lines), doc
