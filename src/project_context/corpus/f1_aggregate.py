"""Across-session aggregates (tier L2) from per-session derivatives.

The rule that matters here: a session where a quantity was UNOBSERVED is not a zero. It
leaves the calculation and is counted, so every summary states both how many sessions it
used and how many it could not. A quantity that is unobserved in every session yields
``UNOBSERVED``, not an empty or zero summary.

Sessions are the unit. Requests inside a session are never pooled.
"""

from __future__ import annotations

import statistics
from typing import Any

from project_context.corpus.completeness import UNOBSERVED

# Session-level numeric quantities that are summarised across sessions.
SUMMARISED = (
    "primary_requests",
    "duration_minutes",
    "tools_available_first_request",
    "growth_ratio_last_over_first",
    "first_request_tool_definition_share",
    "first_request_system_share",
    "last_request_redundant_payload_share",
    "last_request_carry_over_share",
    "last_request_tool_result_share",
    "last_request_user_share",
    "largest_tool_result_share_max",
    "prefix_fraction_median",
    "window_fraction_max",
    "history_rewrite_events",
    "identities_with_differing_bytes",
)


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def summarise(values: list[Any]) -> dict[str, Any]:
    """Median, quartiles and range over the observed values, with both counts stated.

    Quartiles need at least four observed sessions; below that only the range is given, so a
    summary never implies more precision than the sample has.
    """
    observed = sorted(float(v) for v in values if _numeric(v))
    unobserved = len(values) - len(observed)
    if not observed:
        return {"used": 0, "unobserved": unobserved, "value": UNOBSERVED}
    out: dict[str, Any] = {
        "used": len(observed),
        "unobserved": unobserved,
        "median": round(statistics.median(observed), 6),
        "min": round(observed[0], 6),
        "max": round(observed[-1], 6),
    }
    if len(observed) >= 4:
        q1, _, q3 = statistics.quantiles(observed, n=4, method="inclusive")
        out["q1"], out["q3"] = round(q1, 6), round(q3, 6)
    return out


def aggregate(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Summaries of each quantity across the `session` sections of usable derivatives."""
    return {
        "sessions": len(sessions),
        "quantities": {
            name: summarise([s.get(name, UNOBSERVED) for s in sessions]) for name in SUMMARISED
        },
        "growth_shapes": _counts(s["growth_shape"] for s in sessions),
        "sessions_with_compaction": sum(1 for s in sessions if s["compaction_records"] > 0),
    }


def _counts(items: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return dict(sorted(out.items()))
