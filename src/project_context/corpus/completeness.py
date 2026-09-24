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
from typing import Any

from project_context.opencode.bridge import integrity_of, validate_record

OBSERVED = "OBSERVED"  # read directly from the captured record
DERIVED = "DERIVED"  # computed deterministically from observed material
JOINED = "JOINED"  # read from the harness's own local record and joined to the session afterwards
PROXY = "PROXY"  # a stand-in for the thing wanted; stated as a stand-in wherever used
DECLARED = "DECLARED"  # supplied by the author in the sidecar, never inferred from text
UNOBSERVED = "UNOBSERVED"  # the capture cannot see it; never zero, never absent

STATUSES = (OBSERVED, DERIVED, JOINED, PROXY, DECLARED, UNOBSERVED)

# (status, basis). Every quantity F1 reports appears here exactly once.
# Revised after the calibration run (specs/f1-calibration.md): tool-call arguments, model
# limits and provider usage turned out to be observable; the message shape and one adapter
# call turned out to differ from what had been assumed.
OBSERVABILITY: dict[str, tuple[str, str]] = {
    "rendered_input_bytes": (
        OBSERVED,
        "bytes of system, message and tool-definition text at the model-context "
        "boundary; not the provider's final rendered prompt",
    ),
    "rendered_input_token_estimates": (
        DERIVED,
        "two independent estimates, bytes divided by four and words times 1.3; neither is a "
        "tokeniser count and they are never merged",
    ),
    "category_composition": (DERIVED, "grouping of observed parts by their recorded type and role"),
    "tool_definitions": (OBSERVED, "one item per exposed tool: description plus input schema"),
    "tool_definition_stability": (DERIVED, "byte identity of each definition across requests"),
    "tool_result_bytes_and_growth": (OBSERVED, "tool-result parts as re-sent"),
    "tool_name_per_result": (OBSERVED, "recorded on the tool-result part"),
    "tool_call_arguments": (
        OBSERVED,
        "the input of each tool-call part; used locally, never exported",
    ),
    "tool_call_identity": (
        DERIVED,
        "tool name plus canonical arguments; two calls with equal identity ask the same thing",
    ),
    "carry_over": (DERIVED, "a part re-sent unchanged from an earlier request in the session"),
    "redundant_payload": (
        DERIVED,
        "the same tool-output body (at least 32 bytes) more than once inside one request",
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
    "model_limit": (
        OBSERVED,
        "context, input and output limits from the harness's model registry when it knows the "
        "model; absent for a model configured without one",
    ),
    "window_pressure_measured": (
        JOINED,
        "provider-reported prompt tokens (fresh input plus cache reads and writes) divided by "
        "the input limit if there is one, else the context limit",
    ),
    "window_pressure_estimates": (
        DERIVED,
        "the same fraction from each of the two token estimates, kept beside the measured one",
    ),
    "provider_reported_tokens": (
        JOINED,
        "per request, from the harness database; joined by order and only when counts agree",
    ),
    "provider_reported_cache_tokens": (
        JOINED,
        "cache read and write tokens as the provider reported them; says what was reused, not why",
    ),
    "provider_cost": (JOINED, "per request, as recorded by the harness"),
    "latency": (JOINED, "harness-recorded start to completion of the request"),
    "compaction_record": (OBSERVED, "a record whose request_kind is compaction"),
    "history_rewrite": (
        DERIVED,
        "an earlier message part changed or disappeared between consecutive requests",
    ),
    "project_instruction_origin": (DECLARED, "operator sidecar; origin is never inferred"),
    "same_call_different_bytes": (
        DERIVED,
        "one call identity whose results differ in bytes. A re-run whose state changed is "
        "included, so this shows that an older result survives beside a newer one, not that "
        "the older one is wrong",
    ),
    "repository_state_or_version": (UNOBSERVED, "the working tree is not part of the capture"),
    "session_outcome": (DECLARED, "sidecar, closed vocabulary; a fact about the work"),
    "provider_cache_decisions": (UNOBSERVED, "why the provider did or did not reuse a prefix"),
    "provider_added_material": (UNOBSERVED, "added after the observation point"),
    "reasoning_sent_to_provider": (
        UNOBSERVED,
        "reasoning parts are in the message list; whether the provider receives them is not seen",
    ),
    "subagent_relations": (
        UNOBSERVED,
        "a subagent tool exists and the harness database links child sessions to parents, but "
        "that link is not read here",
    ),
}

assert all(status in STATUSES for status, _ in OBSERVABILITY.values())


def unobserved_quantities() -> tuple[str, ...]:
    return tuple(sorted(q for q, (s, _) in OBSERVABILITY.items() if s == UNOBSERVED))


def proxies() -> tuple[str, ...]:
    return tuple(sorted(q for q, (s, _) in OBSERVABILITY.items() if s == PROXY))


# The adapter writes one of these into the spool when it cannot vouch for its own ordering
# (its persisted sequence state was damaged and the spool could not confirm it). It is not a
# capture record and is never analysed; it only marks the session incomplete.
CONTROL_SCHEMA = "project_context.opencode_capture.control.v1"
ORDERING_LOST_EVENT = "sequence_state_lost"

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
    "ordering_state_lost",
    "unrecognised_message_shape",
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


def message_shape_ok(message: Any) -> bool:
    """A message in the shape the analysis understands: a role and a list of typed parts.

    This is the shape OpenCode 2.0.16 really produces. Any other shape is refused rather than
    analysed as if it were understood.
    """
    return (
        isinstance(message, dict)
        and isinstance(message.get("role"), str)
        and isinstance(message.get("content"), list)
        and all(isinstance(p, dict) and isinstance(p.get("type"), str) for p in message["content"])
    )


def split_control(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate capture records from the adapter's control records."""
    control = [r for r in records if r.get("schema") == CONTROL_SCHEMA]
    data = [r for r in records if r.get("schema") != CONTROL_SCHEMA]
    return data, control


def select_session(records: list[dict], session_id: str) -> list[dict]:
    """Every record, capture or control, that belongs to one session, in file order."""
    return [r for r in records if r.get("session_id") == session_id]


def assess_session(records: list[dict], skipped_lines: int = 0) -> Completeness:
    """Judge whether `records` are a whole observation of one session.

    The adapter keeps one counter per session across every request kind, so a whole
    session has sequence numbers 1..N, each once. A repeated 1 means the harness process
    restarted mid-session; a gap means a record was lost. Neither is repaired.

    The adapter now persists its counter, so an ordinary restart no longer resets it. If it
    could not recover its ordering it says so with a control record, and the session is
    incomplete even when the numbers happen to look contiguous.
    """
    records, control = split_control(records)
    reasons: list[str] = []
    if any(c.get("event") == ORDERING_LOST_EVENT for c in control):
        reasons.append("ordering_state_lost")
    if not records:
        return Completeness(False, (*reasons, "no_records"), 0, 0, 0, False)
    if skipped_lines:
        reasons.append("skipped_lines")
    if any(validate_record(r) for r in records):
        reasons.append("invalid_record")
    else:
        if any(r.get("integrity", {}).get("sha256") != integrity_of(r) for r in records):
            reasons.append("integrity_mismatch")
        if not all(message_shape_ok(m) for r in records for m in r["messages"]):
            reasons.append("unrecognised_message_shape")
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
