"""Debugger domain: categories, thresholds, observations.

Small, boring, stdlib-only. Immutable dataclasses and pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEBUGGER_VERSION = "0.1.0"
DOCTOR_POLICY_VERSION = "debugger-doctor-policy-v1"

OBSERVED_BOUNDARY = "opencode.v2.model_context"
OBSERVED_BOUNDARY_NOTE = (
    "OpenCode V2 semantic model-request context observed at the session "
    "context hook immediately before the agent model request proceeds. "
    "NOT the byte-for-byte provider HTTP request."
)

UNOBSERVED_CATEGORIES = (
    "Provider-added material",
    "Final provider wire representation",
    "Provider cache decision",
)

EPISTEMIC_KNOWN = ("content was present in observed OpenCode context",)
EPISTEMIC_UNKNOWN = (
    "whether the model attended to it",
    "whether the model used it",
    "whether it helped",
    "whether it harmed",
    "whether removing it would be safe",
)

#: Debugger display categories. Mapping is structural (ingester kind),
#: never inferred from prose content.
CATEGORIES = (
    "system",
    "user",
    "assistant",
    "tool_definition",
    "tool_call",
    "tool_result",
    "other",
)

KIND_TO_CATEGORY = {
    "system_instruction": "system",
    "conversation_user": "user",
    "conversation_assistant": "assistant",
    "reasoning_part": "assistant",
    "text_part": "other",
    "tool_definition": "tool_definition",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "other_message_part": "other",
}


def category_of(kind: str) -> str:
    """Structural kind -> debugger category. Unknown kinds are other."""
    return KIND_TO_CATEGORY.get(kind, "other")


#: Descriptive thresholds: they decide when the doctor surfaces an
#: observation. They prove nothing about intervention. Relative
#: structural shares preferred over absolute token limits.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "large_item_share": 0.10,
    "repetition_share": 0.05,
    "early_divergence": 0.25,
    "large_tool_result_share": 0.15,
    "large_tool_surface_share": 0.15,
    "high_history_share": 0.60,
    "session_growth_multiple": 3.0,
    "old_history_turns": 5.0,
    "low_prefix_survival": 0.50,
}


@dataclass(frozen=True)
class Observation:
    """One deterministic debugger observation. Magnitude only — never a
    claim about usefulness, harm, or safe removability."""

    code: str
    prominence: str  # INFO | NOTICE | HIGH
    measurement: str
    evidence: str
    chapters: tuple[str, ...] = ()
    investigation: str = ""
    intervention_earned: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "prominence": self.prominence,
            "measurement": self.measurement,
            "evidence": self.evidence,
            "chapters": list(self.chapters),
            "possible_investigation": self.investigation,
            "intervention_earned": self.intervention_earned,
            "policy_version": DOCTOR_POLICY_VERSION,
        }


@dataclass(frozen=True)
class CompositionSlice:
    category: str
    items: int = 0
    bytes: int = 0
    chars: int = 0
    approx_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "items": self.items,
            "bytes": self.bytes,
            "chars": self.chars,
            "approx_tokens": self.approx_tokens,
            "token_provenance": "approximation",
        }


@dataclass(frozen=True)
class InvocationView:
    """Derived read-only view over one observed model request. References
    bundle/invocation records; owns no raw context."""

    session_ordinal: int
    sequence: int
    capture_id: str
    bundle_id: str
    model: str
    provider: str
    agent: str | None
    request_kind: str
    created_at: str
    composition: tuple[CompositionSlice, ...] = ()
    total_bytes: int = 0
    total_chars: int = 0
    total_approx_tokens: int = 0
    item_count: int = 0
    model_limits: dict[str, Any] | None = None
    boundary: str = OBSERVED_BOUNDARY
    unobserved: tuple[str, ...] = UNOBSERVED_CATEGORIES

    def to_dict(self, *, include_identifiers: bool = False) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "debugger_version": DEBUGGER_VERSION,
            "session_ordinal": self.session_ordinal,
            "sequence": self.sequence,
            "model": self.model,
            "provider": self.provider,
            "agent": self.agent,
            "request_kind": self.request_kind,
            "created_at": self.created_at,
            "composition": [s.to_dict() for s in self.composition],
            "total_bytes": self.total_bytes,
            "total_chars": self.total_chars,
            "total_approx_tokens": self.total_approx_tokens,
            "token_provenance": "approximation",
            "item_count": self.item_count,
            "model_limits": self.model_limits if self.model_limits is not None else "UNAVAILABLE",
            "boundary": self.boundary,
            "boundary_note": OBSERVED_BOUNDARY_NOTE,
            "unobserved": list(self.unobserved),
        }
        if include_identifiers:
            doc["capture_id"] = self.capture_id
            doc["bundle_id"] = self.bundle_id
        return doc


@dataclass(frozen=True)
class SessionView:
    session_ordinal: int
    invocations: tuple[InvocationView, ...] = ()
    growth_multiple: float | None = None

    def to_dict(self, *, include_identifiers: bool = False) -> dict[str, Any]:
        invocations = [v.to_dict(include_identifiers=include_identifiers) for v in self.invocations]
        return {
            "debugger_version": DEBUGGER_VERSION,
            "session_ordinal": self.session_ordinal,
            "invocations": invocations,
            "growth_multiple": self.growth_multiple,
            "boundary": OBSERVED_BOUNDARY,
            "unobserved": list(UNOBSERVED_CATEGORIES),
        }


@dataclass(frozen=True)
class DoctorReport:
    session_ordinal: int
    sequence: int | None  # None => session scope
    observations: tuple[Observation, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "debugger_version": DEBUGGER_VERSION,
            "policy_version": DOCTOR_POLICY_VERSION,
            "session_ordinal": self.session_ordinal,
            "sequence": self.sequence,
            "observations": [o.to_dict() for o in self.observations],
            "boundary": OBSERVED_BOUNDARY,
            "not_assessed": [
                "relevance",
                "usefulness",
                "behavioural harm",
                "safe removability",
            ],
        }
