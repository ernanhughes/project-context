"""Stratum assignment for F1 sessions.

Strata exist for **coverage**, so the author can see which kinds of natural work the
corpus has and has not met. They are not an ontology and not a hypothesis. Each session
gets one **primary** stratum and any number of **secondary tags**.

Rules that keep the assignment honest:

* The primary stratum is a function of the session's own structure and a fixed precedence.
  It never looks at how many sessions each stratum already has. A session is never
  relabelled to fill a gap.
* A session that fits no stratum is labelled ``S0_unclassified`` and stays in the corpus.
  Absence is recorded, not repaired.
* A stratum nobody met is reported as *naturally absent*, with the number of sessions that
  were observed while it was absent.
* Where the capture cannot see the thing a definition needs, the criterion is a PROXY and
  the label says so in `basis`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_context.corpus.completeness import PROXY

STRATA = {
    "S1": "short question",
    "S2": "single-file repair",
    "S3": "multi-file repair",
    "S4": "test/debug loop",
    "S5": "tool-heavy investigation",
    "S6": "long-running",
    "S7": "project instructions",
    "S8": "stale or re-read material",
}
UNCLASSIFIED = "S0_unclassified"

# Fixed precedence for the primary label, most demanding first. S7 and S8 are tags only.
PRIMARY_PRECEDENCE = ("S6", "S5", "S4", "S3", "S2", "S1")
TAG_ONLY = ("S7", "S8")

# Definitions, from the preregistration.
S1_MAX_REQUESTS = 3
S2_MAX_REQUESTS = 15
S3_MIN_FILES = 3
S4_MIN_TEST_CALLS = 3
S5_TOOL_SHARE = 0.5
S6_MIN_REQUESTS = 40


@dataclass(frozen=True)
class Assignment:
    primary: str
    tags: tuple[str, ...]
    satisfied: tuple[str, ...]  # every stratum whose definition the session meets
    basis: dict[str, str]  # stratum -> "observed" | "proxy" | "declared"


def satisfied_strata(
    session: dict[str, Any], declared: dict[str, Any] | None = None
) -> dict[str, str]:
    """Which definitions this session meets, and on what basis. `session` is the L1 summary."""
    declared = declared or {}
    n = session["primary_requests"]
    edits = session["distinct_edit_targets"]
    edit_calls = session["edit_result_count"]
    met: dict[str, str] = {}
    if n <= S1_MAX_REQUESTS and edit_calls == 0:
        met["S1"] = "observed"
    if edits == 1 and n <= S2_MAX_REQUESTS:
        met["S2"] = PROXY.lower()  # "files edited" is inferred from distinct edit-result titles
    if edits >= S3_MIN_FILES:
        met["S3"] = PROXY.lower()
    if session["test_command_result_count"] >= S4_MIN_TEST_CALLS:
        met["S4"] = PROXY.lower()  # test runs are recognised from the command title
    share = session["last_request_tool_result_share"]
    if isinstance(share, float) and share > S5_TOOL_SHARE:
        met["S5"] = "observed"
    if n >= S6_MIN_REQUESTS or session["compaction_records"] > 0:
        met["S6"] = "observed"
    if declared.get("project_instructions") is True:
        met["S7"] = "declared"
    if session["identities_with_differing_bytes"] > 0:
        met["S8"] = PROXY.lower()
    return met


def assign(session: dict[str, Any], declared: dict[str, Any] | None = None) -> Assignment:
    met = satisfied_strata(session, declared)
    primary = next((s for s in PRIMARY_PRECEDENCE if s in met), UNCLASSIFIED)
    tags = tuple(s for s in sorted(met) if s != primary)
    return Assignment(primary, tags, tuple(sorted(met)), met)


def coverage(assignments: list[Assignment]) -> dict[str, Any]:
    """Per stratum: primary count and tag count, plus which strata were naturally absent.

    Reads assignments only. Nothing here can change an assignment.
    """
    rows = {}
    for stratum in [*STRATA, UNCLASSIFIED]:
        primary = sum(1 for a in assignments if a.primary == stratum)
        tagged = sum(1 for a in assignments if stratum in a.tags)
        rows[stratum] = {"primary": primary, "tag": tagged, "any": primary + tagged}
    # With no sessions nothing has been observed, so nothing can yet be called absent.
    absent = [s for s in STRATA if rows[s]["any"] == 0] if assignments else []
    return {
        "sessions": len(assignments),
        "assessable": bool(assignments),
        "by_stratum": rows,
        "naturally_absent": absent,
        "sessions_observed_while_absent": len(assignments),
        "max_primary_in_one_stratum": max((r["primary"] for r in rows.values()), default=0),
    }


def is_long(assignment: Assignment) -> bool:
    """A long session, for the routing triggers, is one that meets the S6 definition, whether
    S6 is its primary label or a tag."""
    return "S6" in assignment.satisfied
