"""Debugger doctor: deterministic observations, never recommendations.

Every detector is structurally measurable at the V2 boundary. Severity
words (INFO/NOTICE/HIGH) describe measured magnitude only — never
usefulness, harm, or safe removability. Thresholds are explicit,
versioned policy inputs (see domain.DEFAULT_THRESHOLDS).
"""

from __future__ import annotations

from project_context.debugger.analyse import (
    ObservedRequest,
    _sequence_of,
    composition,
    membership_diff,
    repetition_between,
    session_growth_multiple,
    totals,
    within_repetition,
)
from project_context.debugger.domain import (
    DEFAULT_THRESHOLDS,
    DOCTOR_POLICY_VERSION,
    Observation,
)
from project_context.opencode.prevalence import (
    bundle_bytes,
    structural_shared_prefix,
)

CHAPTERS = {
    "REPEATED_CONTENT": (("9", "10"), "pruning/reuse"),
    "LARGE_ITEM": (("4", "13"), "budget/result shaping"),
    "LARGE_TOOL_RESULT": (("13", "17"), "externalisation/result shaping"),
    "LARGE_TOOL_SURFACE": (("17",), "tool-surface review"),
    "SESSION_GROWTH": (("4", "11", "12"), "budget/compaction/fidelity"),
    "EARLY_PREFIX_CHURN": (("9",), "prefix-stability timing"),
    "LOW_PREFIX_SURVIVAL": (("9",), "prefix-stability timing"),
    "HIGH_TOOL_RESULT_SHARE": (("13", "17"), "externalisation/result shaping"),
    "HIGH_HISTORY_SHARE": (("11", "12"), "relevance/budget"),
    "OLD_HISTORY_GROWTH": (("11", "12"), "relevance/budget"),
}


def _observation(
    code: str,
    prominence: str,
    measurement: str,
    evidence: str,
) -> Observation:
    chapters, investigation = CHAPTERS.get(code, ((), ""))
    return Observation(
        code=code,
        prominence=prominence,
        measurement=measurement,
        evidence=evidence,
        chapters=tuple(chapters),
        investigation=f"possible investigation: {investigation}" if investigation else "",
        intervention_earned=False,
    )


def doctor_invocation(
    ordered: list[ObservedRequest],
    index: int,
    *,
    thresholds: dict[str, float] | None = None,
) -> list[Observation]:
    """Observations for one invocation (with previous-invocation change)."""
    policy = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        policy.update(thresholds)
    observed = ordered[index]
    bundle = observed.bundle
    size = totals(bundle)
    out: list[Observation] = []
    if size["bytes"] == 0:
        return out

    rep = within_repetition(bundle)
    share = policy["repetition_share"]
    if rep["duplicate_bytes"] >= size["bytes"] * share and rep["duplicate_items"]:
        prominence = "HIGH" if rep["duplicate_bytes"] >= size["bytes"] * 0.15 else "NOTICE"
        out.append(
            _observation(
                "REPEATED_CONTENT",
                prominence,
                f"{rep['duplicate_items']} byte-identical items recur in this request "
                f"({rep['duplicate_bytes']} bytes)",
                f"exact content identity within invocation; {rep['duplicate_bytes']} of "
                f"{size['bytes']} observed bytes",
            )
        )

    for item in bundle.items:
        item_bytes = len(item.content.encode("utf-8"))
        if item_bytes >= size["bytes"] * policy["large_item_share"] and len(bundle.items) > 1:
            out.append(
                _observation(
                    "LARGE_ITEM",
                    "NOTICE",
                    f"item at position {item.position} ({item.kind}) occupies "
                    f"{item_bytes} bytes ({item_bytes / size['bytes']:.0%} of observed context)",
                    "single-item share of observed bytes; large is measurable, "
                    "harm is not assessed",
                )
            )
            break

    comp = {s.category: s for s in composition(bundle)}
    tool_result_bytes = comp.get("tool_result").bytes if comp.get("tool_result") else 0
    if tool_result_bytes >= size["bytes"] * policy["large_tool_result_share"]:
        out.append(
            _observation(
                "LARGE_TOOL_RESULT",
                "HIGH" if tool_result_bytes >= size["bytes"] * 0.25 else "NOTICE",
                f"tool results occupy {tool_result_bytes} bytes "
                f"({tool_result_bytes / size['bytes']:.0%} of observed context)",
                "tool_result category share of observed bytes",
            )
        )
        out.append(
            _observation(
                "HIGH_TOOL_RESULT_SHARE",
                "NOTICE",
                f"tool-result share {tool_result_bytes / size['bytes']:.0%}",
                "same measurement, chapter pointer for result-shaping investigation",
            )
        )
    tool_surface = comp.get("tool_definition").bytes if comp.get("tool_definition") else 0
    if tool_surface and tool_surface >= size["bytes"] * policy["large_tool_surface_share"]:
        out.append(
            _observation(
                "LARGE_TOOL_SURFACE",
                "NOTICE",
                f"tool-definition surface is {tool_surface} bytes "
                f"({tool_surface / size['bytes']:.0%} of observed context)",
                "exposed tool definitions; availability is not utility",
            )
        )
    history_bytes = sum((comp.get(c).bytes if comp.get(c) else 0) for c in ("user", "assistant"))
    if history_bytes >= size["bytes"] * policy["high_history_share"]:
        out.append(
            _observation(
                "HIGH_HISTORY_SHARE",
                "INFO",
                f"conversation history occupies {history_bytes} bytes "
                f"({history_bytes / size['bytes']:.0%} of observed context)",
                "user plus assistant category share; age is measurable, staleness is not",
            )
        )

    if index > 0:
        previous = ordered[index - 1].bundle
        prefix = structural_shared_prefix(previous, bundle)
        if prefix.get("comparable") and len(bundle.items):
            shared = int(prefix.get("shared_item_count") or 0)
            ratio = shared / len(bundle.items)
            if ratio <= policy["early_divergence"]:
                out.append(
                    _observation(
                        "EARLY_PREFIX_CHURN",
                        "NOTICE",
                        f"stable prefix ends at item {shared} of {len(bundle.items)} "
                        f"({ratio:.0%} stable)",
                        "structural shared prefix; NOT a provider cache claim",
                    )
                )
        membership = membership_diff(previous, bundle)
        cross = repetition_between(previous, bundle)
        cross_share = policy["repetition_share"]
        if cross["repeated_bytes"] >= size["bytes"] * cross_share and cross["repeated_items"]:
            out.append(
                _observation(
                    "REPEATED_CONTENT",
                    "NOTICE",
                    f"{cross['repeated_items']} items ({cross['repeated_bytes']} bytes) "
                    f"recur from the previous invocation",
                    "cross-invocation exact content identity; recurrence is not redundancy",
                )
            )
        _ = membership
    return out


def doctor_session(
    ordered: list[ObservedRequest],
    *,
    thresholds: dict[str, float] | None = None,
) -> list[Observation]:
    """Session-scope observations: growth, prefix survival, old history."""
    policy = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        policy.update(thresholds)
    out: list[Observation] = []
    if len(ordered) < 2:
        return out
    growth = session_growth_multiple(ordered)
    if growth is not None and growth >= policy["session_growth_multiple"]:
        out.append(
            _observation(
                "SESSION_GROWTH",
                "HIGH" if growth >= policy["session_growth_multiple"] * 1.5 else "NOTICE",
                f"session context has grown {growth:.1f}x since turn 1 "
                f"({bundle_bytes(ordered[0].bundle)} to {bundle_bytes(ordered[-1].bundle)} bytes)",
                "first-to-last observed byte ratio; growth is measurable, pressure is not proven",
            )
        )
    # Prefix survival: minimum consecutive shared-item ratio.
    ratios: list[float] = []
    for earlier_obs, later_obs in zip(ordered, ordered[1:]):
        prefix = structural_shared_prefix(earlier_obs.bundle, later_obs.bundle)
        if prefix.get("comparable") and len(later_obs.bundle.items):
            ratios.append(int(prefix.get("shared_item_count") or 0) / len(later_obs.bundle.items))
    if ratios and min(ratios) <= policy["low_prefix_survival"]:
        out.append(
            _observation(
                "LOW_PREFIX_SURVIVAL",
                "NOTICE",
                f"minimum consecutive stable-prefix ratio is {min(ratios):.0%} "
                f"across {len(ratios)} transitions",
                "structural prefix only; NOT a provider cache claim",
            )
        )
    # Old-history growth: consecutive turns where observed bytes grow.
    consecutive = 0
    best = 0
    for earlier_obs, later_obs in zip(ordered, ordered[1:]):
        if bundle_bytes(later_obs.bundle) > bundle_bytes(earlier_obs.bundle):
            consecutive += 1
            best = max(best, consecutive)
        else:
            consecutive = 0
    if best >= int(policy["old_history_turns"]):
        out.append(
            _observation(
                "OLD_HISTORY_GROWTH",
                "NOTICE",
                f"observed context grew for {best} consecutive turns",
                "monotonic byte growth streak; age is measurable, staleness is not",
            )
        )
    sequences = [_sequence_of(o, i) for i, o in enumerate(ordered)]
    _ = sequences
    return out


def policy_version() -> str:
    return DOCTOR_POLICY_VERSION
