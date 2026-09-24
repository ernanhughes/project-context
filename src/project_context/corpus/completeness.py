"""What the F1 capture can and cannot see, and when a session counts as observed.

Two separate ideas live here, and they are never merged:

* the **observability matrix**: for every quantity the study reports, whether the
  capture OBSERVES it, DERIVES it from observed material, only offers a PROXY,
  relies on the author's DECLARATION, or cannot see it at all (UNOBSERVED);
* **session completeness**: whether the records for one session are a whole
  observation, judged from the records alone.

UNOBSERVED is not zero and it is not absent. A share computed over sessions where a
quantity was unobserved has a smaller denominator, and reports say so.
"""

from __future__ import annotations

from dataclasses import dataclass

from project_context.opencode.bridge import integrity_of, validate_record

OBSERVED = "OBSERVED"  # read directly from the captured record
DERIVED = "DERIVED"  # computed deterministically from observed material
PROXY = "PROXY"  # a stand-in for the thing wanted; stated as a stand-in wherever used
DECLARED = "DECLARED"  # supplied by the author in the sidecar, never inferred from text
UNOBSERVED = "UNOBSERVED"  # the capture cannot see it; never zero, never absent

STATUSES = (OBSERVED, DERIVED, PROXY, DECLARED, UNOBSERVED)

# (status, basis). Every quantity F1 reports appears here exactly once.
OBSERVABILITY: dict[str, tuple[str, str]] = {
    "rendered_input_bytes": (
        OBSERVED,
        "bytes of system, message and tool-definition text at the harness's model-context "
        "boundary; not the provider's final rendered prompt",
    ),
    "rendered_input_tokens": (
        DERIVED,
        "an estimate (word count times 1.3), labelled approximate everywhere; the provider's "
        "tokeniser is not applied",
    ),
    "category_composition": (DERIVED, "grouping of observed parts by their recorded kind"),
    "tool_definitions": (OBSERVED, "one item per exposed tool: description plus input schema"),
    "tool_definition_stability": (DERIVED, "byte identity of each definition across requests"),
    "tool_result_bytes_and_growth": (OBSERVED, "completed tool-result parts as re-sent"),
    "tool_name_per_result": (OBSERVED, "recorded on the tool part"),
    "tool_call_arguments": (UNOBSERVED, "only the result and its title are captured"),
    "tool_call_identity": (
        PROXY,
        "tool name plus result title; a title may be path-like, so it is used locally and "
        "never leaves the machine",
    ),
    "carry_over": (DERIVED, "a part re-sent unchanged from an earlier request in the session"),
    "redundant_payload": (
        DERIVED,
        "the same tool-output body more than once inside one request, header removed",
    ),
    "stable_prefix": (
        PROXY,
        "longest run of identical leading parts between consecutive requests, under an "
        "ASSUMED render order (tool definitions, system, messages); the provider's actual "
        "order is not observed",
    ),
    "render_order": (UNOBSERVED, "how the provider lays the parts out before the model sees them"),
    "standing_instruction_split": (
        UNOBSERVED,
        "system entries are not attributed to harness, project or user; only their total is seen",
    ),
    "history_window_distance": (
        OBSERVED,
        "rendered size against model_limits.context when the record carries it",
    ),
    "compaction_record": (OBSERVED, "a record whose request_kind is compaction"),
    "history_rewrite": (
        DERIVED,
        "an earlier part changed or disappeared between consecutive requests",
    ),
    "project_instruction_origin": (DECLARED, "operator sidecar; origin is never inferred"),
    "same_call_different_bytes": (
        PROXY,
        "same tool and title returning different bytes; without arguments this can also be "
        "two different calls that share a title",
    ),
    "repository_state_or_version": (UNOBSERVED, "the working tree is not part of the capture"),
    "session_outcome": (DECLARED, "sidecar, closed vocabulary; a fact about the work"),
    "provider_cache_behaviour": (UNOBSERVED, "not exposed at the harness boundary"),
    "provider_added_material": (UNOBSERVED, "added after the observation point"),
    "provider_usage_and_cost": (UNOBSERVED, "not part of the record"),
    "latency": (UNOBSERVED, "not part of the record"),
    "hidden_reasoning": (UNOBSERVED, "only reasoning parts the harness re-sends are visible"),
}

assert all(status in STATUSES for status, _ in OBSERVABILITY.values())


def unobserved_quantities() -> tuple[str, ...]:
    return tuple(sorted(q for q, (s, _) in OBSERVABILITY.items() if s == UNOBSERVED))


def proxies() -> tuple[str, ...]:
    return tuple(sorted(q for q, (s, _) in OBSERVABILITY.items() if s == PROXY))


# Closed vocabulary: each maps to the exclusion reason "capture incomplete".
INCOMPLETE_REASONS = (
    "no_records",
    "skipped_lines",
    "invalid_record",
    "integrity_mismatch",
    "mixed_or_missing_session",
    "sequence_gap",
    "sequence_duplicate_or_restart",
    "first_record_not_sequence_one",
    "no_primary_request",
)


@dataclass(frozen=True)
class Completeness:
    """One session's completeness, from its records alone."""

    complete: bool
    reasons: tuple[str, ...]
    records: int
    primary_requests: int
    other_requests: int  # compaction, generate, title: counted, never merged into primary
    tool_definitions_seen: bool  # a session with no exposed tools cannot inform Q4

    def qualifies_for_f1(self) -> bool:
        """A session enters analysis only when whole. There is no partial credit and no
        repair: an incomplete session is excluded and its reason recorded."""
        return self.complete


def assess_session(records: list[dict], skipped_lines: int = 0) -> Completeness:
    """Judge whether `records` are a whole observation of one session.

    The adapter keeps one counter per session across every request kind, so a whole
    session has sequence numbers 1..N, each once. A repeated 1 means the harness process
    restarted mid-session; a gap means a record was lost. Neither is repaired.
    """
    reasons: list[str] = []
    if not records:
        return Completeness(False, ("no_records",), 0, 0, 0, False)
    if skipped_lines:
        reasons.append("skipped_lines")
    if any(validate_record(r) for r in records):
        reasons.append("invalid_record")
    else:
        if any(r.get("integrity", {}).get("sha256") != integrity_of(r) for r in records):
            reasons.append("integrity_mismatch")
        sessions = {r.get("session_id") for r in records}
        if len(sessions) != 1 or None in sessions:
            reasons.append("mixed_or_missing_session")
        sequences = sorted(int(r["invocation_sequence"]) for r in records)
        if len(set(sequences)) != len(sequences):
            reasons.append("sequence_duplicate_or_restart")
        elif sequences[0] != 1:
            reasons.append("first_record_not_sequence_one")
        elif sequences != list(range(1, len(sequences) + 1)):
            reasons.append("sequence_gap")
    primary = sum(1 for r in records if r.get("request_kind") == "context")
    if primary == 0:
        reasons.append("no_primary_request")
    tools = any(bool(r.get("tools")) for r in records if r.get("request_kind") == "context")
    return Completeness(
        not reasons,
        tuple(reasons),
        len(records),
        primary,
        len(records) - primary,
        tools,
    )
