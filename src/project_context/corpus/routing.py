"""F1 operational routing triggers.

These four numbers decide which later experiments the programme runs next. They are
**routing** thresholds. They are not empirical thresholds and they are not evidence that a
mechanism matters, and three different things must never be confused:

* the **activation threshold**: the size at which a later experiment is worth running;
* the **effect threshold**: the size of a change that would matter to behaviour, which F1
  cannot observe and does not estimate;
* the **success criterion** of that later experiment, set in its own preregistration.

Reaching a trigger means "go and test this". Missing it means "do not spend the effort
yet", or, where the metric could not be evaluated, "we could not tell". It never means the
mechanism helps, and it never means the mechanism is unimportant.

The values are fixed before any data exists. Nothing here reads the data to choose them, and
the measurement code is versioned so that it cannot be tuned to cross a line.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from project_context.corpus.completeness import UNOBSERVED

ROUTING_VERSION = "1.0.0"

TOOL_DEFINITION_SHARE = 0.10
DUPLICATE_SHARE = 0.10
WINDOW_FRACTION = 0.60
STABLE_PREFIX_FRACTION = 0.50
# Companion counts, part of the same rule.
WINDOW_SESSIONS_REQUIRED = 2
STABLE_PREFIX_SESSION_PROPORTION = 0.50
MIN_SESSIONS_TO_EVALUATE = 3

BORDERLINE_RELATIVE = 0.25  # within a quarter of the threshold is "worth review", not settled

MEANING = "activates a later experiment; says nothing about effect size or whether it succeeds"

TRIGGERED = "TRIGGERED"
NOT_TRIGGERED = "NOT_TRIGGERED"
NOT_EVALUABLE = "NOT_EVALUABLE"


@dataclass(frozen=True)
class Record:
    trigger: str
    routes_to: str
    metric: str
    observed_value: float | str
    routing_threshold: float
    status: str
    distance: float | str  # observed minus threshold, in the metric's own units
    relative_distance: float | str  # distance as a fraction of the threshold
    band: str  # clear | borderline | not_evaluable
    sessions_used: int
    sessions_unobserved: int
    leave_one_out_flips: int | str
    meaning: str = MEANING
    basis: str = ""  # which measurement the status rests on (T3 only)
    other_bases: dict[str, Any] = field(default_factory=dict)  # the other measurements, beside it
    borderline_bases: list[str] = field(default_factory=list)  # which of them sit near the line

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _band(observed: float | str, threshold: float) -> tuple[float | str, float | str, str]:
    if observed == UNOBSERVED or not isinstance(observed, (int, float)):
        return UNOBSERVED, UNOBSERVED, "not_evaluable"
    distance = round(observed - threshold, 6)
    relative = round(distance / threshold, 6)
    return distance, relative, "borderline" if abs(relative) <= BORDERLINE_RELATIVE else "clear"


def _numbers(values: list[Any]) -> list[float]:
    return [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _finish(
    trigger: str,
    routes_to: str,
    metric: str,
    observed: float | str,
    threshold: float,
    status: str,
    used: int,
    unobserved: int,
    flips: int | str,
) -> Record:
    distance, relative, band = _band(observed, threshold)
    return Record(
        trigger,
        routes_to,
        metric,
        observed,
        threshold,
        status,
        distance,
        relative,
        band if status != NOT_EVALUABLE else "not_evaluable",
        used,
        unobserved,
        flips,
    )


def _median_trigger(
    trigger: str,
    routes_to: str,
    metric: str,
    values: list[Any],
    threshold: float,
) -> Record:
    nums = _numbers(values)
    unobserved = len(values) - len(nums)
    if len(nums) < MIN_SESSIONS_TO_EVALUATE:
        return _finish(
            trigger,
            routes_to,
            metric,
            UNOBSERVED,
            threshold,
            NOT_EVALUABLE,
            len(nums),
            unobserved,
            UNOBSERVED,
        )
    observed = round(statistics.median(nums), 6)
    status = TRIGGERED if observed >= threshold else NOT_TRIGGERED
    flips = 0
    for i in range(len(nums)):
        rest = nums[:i] + nums[i + 1 :]
        alt = TRIGGERED if statistics.median(rest) >= threshold else NOT_TRIGGERED
        flips += int(alt != status)
    return _finish(
        trigger, routes_to, metric, observed, threshold, status, len(nums), unobserved, flips
    )


def evaluate(sessions: list[dict[str, Any]], long_flags: list[bool]) -> list[Record]:
    """Evaluate the four triggers over per-session L1 summaries.

    `sessions` are the `session` sections of usable derivatives; `long_flags[i]` says whether
    session i is a long session (stratum S6). Values that are UNOBSERVED lower the number of
    sessions used and are counted, never treated as zero.
    """
    long_sessions = [s for s, long in zip(sessions, long_flags) if long]

    t1 = _median_trigger(
        "T1_tool_context",
        "tool-context family",
        "median first-request tool-definition share, across sessions",
        [s["first_request_tool_definition_share"] for s in sessions],
        TOOL_DEFINITION_SHARE,
    )
    t2 = _median_trigger(
        "T2_safe_removal",
        "transformation family: safe removal first",
        "median last-request redundant-payload share, across long sessions",
        [s["last_request_redundant_payload_share"] for s in long_sessions],
        DUPLICATE_SHARE,
    )
    t3 = _window_trigger(sessions)
    t4 = _prefix_trigger(long_sessions)
    return [t1, t2, t3, t4]


# The three ways window pressure is measured. Never merged into one number. The measured one
# is what the provider reported for the prompt; the other two are estimates from the captured
# text. If the harness's own usage record is available it is preferred and the estimates are
# kept only for comparison.
WINDOW_BASES = (
    ("measured", "window_fraction_max_measured"),
    ("bytes_estimate", "window_fraction_max_bytes_estimate"),
    ("word_estimate", "window_fraction_max_word_estimate"),
)


def _window_record(sessions: list[dict[str, Any]], key: str, metric: str) -> Record:
    """At least two sessions reach 60% of the window, or any compaction occurs, on one basis.

    The decisive value is the second-highest session, since two must reach the line.
    """
    fractions = _numbers([s[key] for s in sessions])
    unobserved = len(sessions) - len(fractions)
    compaction = sum(1 for s in sessions if s["compaction_records"] > 0)
    if len(fractions) < MIN_SESSIONS_TO_EVALUATE and not compaction:
        return _finish(
            "T3_externalise_recall",
            "externalise-and-recall family",
            metric,
            UNOBSERVED,
            WINDOW_FRACTION,
            NOT_EVALUABLE,
            len(fractions),
            unobserved,
            UNOBSERVED,
        )
    ranked = sorted(fractions, reverse=True)
    second = ranked[1] if len(ranked) >= WINDOW_SESSIONS_REQUIRED else 0.0
    status = TRIGGERED if (second >= WINDOW_FRACTION or compaction) else NOT_TRIGGERED
    flips = 0
    for i in range(len(ranked)):
        rest = ranked[:i] + ranked[i + 1 :]
        alt_second = rest[1] if len(rest) >= WINDOW_SESSIONS_REQUIRED else 0.0
        alt = TRIGGERED if (alt_second >= WINDOW_FRACTION or compaction) else NOT_TRIGGERED
        flips += int(alt != status)
    return _finish(
        "T3_externalise_recall",
        "externalise-and-recall family",
        metric,
        round(second, 6),
        WINDOW_FRACTION,
        status,
        len(fractions),
        unobserved,
        flips,
    )


def _window_trigger(sessions: list[dict[str, Any]]) -> Record:
    """T3 on each basis, reported as one record on the primary basis with the others beside it.

    The primary basis is the measured one when at least three sessions have it, otherwise the
    bytes estimate. A trigger is labelled borderline when any basis sits within a quarter of the
    line, and the record names which basis put it there. Disagreement between bases is recorded,
    never averaged away.
    """
    metric = "second-highest session peak window fraction, or any compaction"
    records = {
        name: _window_record(sessions, key, f"{metric} ({name})") for name, key in WINDOW_BASES
    }
    measured_ok = records["measured"].status != NOT_EVALUABLE
    primary_name = "measured" if measured_ok else "bytes_estimate"
    primary = records[primary_name]
    others = {
        name: {
            "observed_value": rec.observed_value,
            "status": rec.status,
            "band": rec.band,
            "sessions_used": rec.sessions_used,
        }
        for name, rec in records.items()
        if name != primary_name
    }
    near = [n for n, rec in records.items() if rec.band == "borderline"]
    band = "borderline" if near and primary.status != NOT_EVALUABLE else primary.band
    return Record(
        primary.trigger,
        primary.routes_to,
        primary.metric,
        primary.observed_value,
        primary.routing_threshold,
        primary.status,
        primary.distance,
        primary.relative_distance,
        band,
        primary.sessions_used,
        primary.sessions_unobserved,
        primary.leave_one_out_flips,
        basis=primary_name,
        other_bases=others,
        borderline_bases=near,
    )


def _prefix_trigger(long_sessions: list[dict[str, Any]]) -> Record:
    """Median stable-prefix fraction at least 50% in at least half of long sessions."""
    medians = [s["prefix_fraction_median"] for s in long_sessions]
    nums = _numbers(medians)
    unobserved = len(medians) - len(nums)
    args = (
        "T4_cache_probe",
        "paid cache probe",
        "share of long sessions whose median stable-prefix fraction is at least 0.5",
    )
    if len(nums) < MIN_SESSIONS_TO_EVALUATE:
        return _finish(
            *args,
            UNOBSERVED,
            STABLE_PREFIX_SESSION_PROPORTION,
            NOT_EVALUABLE,
            len(nums),
            unobserved,
            UNOBSERVED,
        )
    proportion = round(sum(1 for v in nums if v >= STABLE_PREFIX_FRACTION) / len(nums), 6)
    status = TRIGGERED if proportion >= STABLE_PREFIX_SESSION_PROPORTION else NOT_TRIGGERED
    flips = 0
    for i in range(len(nums)):
        rest = nums[:i] + nums[i + 1 :]
        alt_p = sum(1 for v in rest if v >= STABLE_PREFIX_FRACTION) / len(rest)
        alt = TRIGGERED if alt_p >= STABLE_PREFIX_SESSION_PROPORTION else NOT_TRIGGERED
        flips += int(alt != status)
    return _finish(
        *args, proportion, STABLE_PREFIX_SESSION_PROPORTION, status, len(nums), unobserved, flips
    )


def prefix_line_sensitivity(long_sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """T4 also depends on the per-session line of 0.5. Show it moved by a quarter either way."""
    nums = _numbers([s["prefix_fraction_median"] for s in long_sessions])
    out: dict[str, Any] = {}
    for label, line in (
        ("line_lower", STABLE_PREFIX_FRACTION * (1 - BORDERLINE_RELATIVE)),
        ("line_as_registered", STABLE_PREFIX_FRACTION),
        ("line_higher", STABLE_PREFIX_FRACTION * (1 + BORDERLINE_RELATIVE)),
    ):
        out[label] = round(sum(1 for v in nums if v >= line) / len(nums), 6) if nums else UNOBSERVED
    return out
