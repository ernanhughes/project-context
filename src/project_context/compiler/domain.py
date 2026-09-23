"""Compiler domain records. All frozen dataclasses with stable schema IDs
and JSON round-trips, following the Stage 0 record conventions.

A ContextCandidate is one legal representation option: it wraps an
immutable content identity plus compiler-visible metadata. Hidden
evaluator labels and oracle minima NEVER appear here; only the
hidden-truth loader in the evaluation package may read them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

CONTEXT_CANDIDATE_SCHEMA = "project_context.context_candidate.v1"
CONTEXT_REQUEST_SCHEMA = "project_context.context_request.v1"
DECISION_TRACE_SCHEMA = "project_context.decision_trace.v1"
COMPILE_FAILURE_SCHEMA = "project_context.compile_failure.v1"
COMPILATION_RESULT_SCHEMA = "project_context.compilation_result.v1"


class RequirementClass(str, Enum):
    MANDATORY = "MANDATORY"
    REQUIRED = "REQUIRED"
    PREFERRED = "PREFERRED"
    DISCRETIONARY = "DISCRETIONARY"


class TraceDecision(str, Enum):
    ADMITTED = "ADMITTED"
    REJECTED_HARD = "REJECTED_HARD"
    REJECTED_BUDGET = "REJECTED_BUDGET"
    REJECTED_REDUNDANT = "REJECTED_REDUNDANT"
    REJECTED_ALTERNATIVE = "REJECTED_ALTERNATIVE"
    REJECTED_DEPENDENCY = "REJECTED_DEPENDENCY"
    REJECTED_GROUP = "REJECTED_GROUP"


class FailureReason(str, Enum):
    INSUFFICIENT_BUDGET = "INSUFFICIENT_BUDGET"
    UNSATISFIED_DEPENDENCY = "UNSATISFIED_DEPENDENCY"
    NO_LEGAL_REPRESENTATION = "NO_LEGAL_REPRESENTATION"
    UNRESOLVED_REQUIRED_GROUP = "UNRESOLVED_REQUIRED_GROUP"
    REQUIRED_SOURCE_UNAVAILABLE = "REQUIRED_SOURCE_UNAVAILABLE"
    REQUIRED_INELIGIBLE = "REQUIRED_INELIGIBLE"


@dataclass(frozen=True)
class ContextCandidate:
    """One representation option over an immutable content identity.

    Compiler-visible metadata only. `form_rank`/`min_rank` encode the
    representation floor: legal iff form_rank >= min_rank. Higher rank
    means more complete (REFERENCE=0, ANCHOR=1, COMPACT=2, FULL=3 by
    fixture convention). `depends_on` names candidate IDs that must be
    admitted alongside. `group_id` with `group_required` marks all-of
    groups (qualification pairs, conflict triples).
    """

    candidate_id: str
    content_identity: str
    representation_id: str
    form_rank: int
    min_rank: int
    source_kind: str
    source_ref: str
    kind: str
    content: str
    token_count: int
    token_source: str
    requirement: RequirementClass
    order_role: str
    scope_eligible: bool
    scope_reason: str
    freshness_eligible: bool
    freshness_reason: str
    authority_eligible: bool
    authority_reason: str
    depends_on: tuple[str, ...] = ()
    group_id: str | None = None
    group_required: bool = False
    coverage_keys: tuple[str, ...] = ()
    relevance: float = 0.0
    is_default_form: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONTEXT_CANDIDATE_SCHEMA,
            "candidate_id": self.candidate_id,
            "content_identity": self.content_identity,
            "representation_id": self.representation_id,
            "form_rank": self.form_rank,
            "min_rank": self.min_rank,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "kind": self.kind,
            "content": self.content,
            "token_count": self.token_count,
            "token_source": self.token_source,
            "requirement": self.requirement.value,
            "order_role": self.order_role,
            "scope_eligible": self.scope_eligible,
            "scope_reason": self.scope_reason,
            "freshness_eligible": self.freshness_eligible,
            "freshness_reason": self.freshness_reason,
            "authority_eligible": self.authority_eligible,
            "authority_reason": self.authority_reason,
            "depends_on": list(self.depends_on),
            "group_id": self.group_id,
            "group_required": self.group_required,
            "coverage_keys": list(self.coverage_keys),
            "relevance": self.relevance,
            "is_default_form": self.is_default_form,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextCandidate":
        version = data.get("schema_version", CONTEXT_CANDIDATE_SCHEMA)
        if version != CONTEXT_CANDIDATE_SCHEMA:
            raise ValueError(f"unsupported ContextCandidate schema: {version!r}")
        return cls(
            candidate_id=data["candidate_id"],
            content_identity=data["content_identity"],
            representation_id=data["representation_id"],
            form_rank=data["form_rank"],
            min_rank=data["min_rank"],
            source_kind=data["source_kind"],
            source_ref=data["source_ref"],
            kind=data["kind"],
            content=data["content"],
            token_count=data["token_count"],
            token_source=data.get("token_source", "approximation"),
            requirement=RequirementClass(data["requirement"]),
            order_role=data["order_role"],
            scope_eligible=data["scope_eligible"],
            scope_reason=data.get("scope_reason", ""),
            freshness_eligible=data["freshness_eligible"],
            freshness_reason=data.get("freshness_reason", ""),
            authority_eligible=data["authority_eligible"],
            authority_reason=data.get("authority_reason", ""),
            depends_on=tuple(data.get("depends_on", [])),
            group_id=data.get("group_id"),
            group_required=bool(data.get("group_required", False)),
            coverage_keys=tuple(data.get("coverage_keys", [])),
            relevance=float(data.get("relevance", 0.0)),
            is_default_form=bool(data.get("is_default_form", False)),
        )


@dataclass(frozen=True)
class ContextRequest:
    """Compilation inputs describing the computation. No business logic,
    no oracle labels. `required_ids` names candidate IDs the task
    explicitly requires; absence is failure, never substitution."""

    request_id: str
    task_id: str
    usable_token_budget: int
    created_at: str
    active_scope: str
    required_ids: tuple[str, ...] = ()
    policy_version: str = "compiler-policy-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONTEXT_REQUEST_SCHEMA,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "usable_token_budget": self.usable_token_budget,
            "created_at": self.created_at,
            "active_scope": self.active_scope,
            "required_ids": list(self.required_ids),
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextRequest":
        version = data.get("schema_version", CONTEXT_REQUEST_SCHEMA)
        if version != CONTEXT_REQUEST_SCHEMA:
            raise ValueError(f"unsupported ContextRequest schema: {version!r}")
        budget = data["usable_token_budget"]
        if not isinstance(budget, int) or budget < 0:
            raise ValueError(f"invalid usable_token_budget: {budget!r}")
        return cls(
            request_id=data["request_id"],
            task_id=data["task_id"],
            usable_token_budget=budget,
            created_at=data["created_at"],
            active_scope=data.get("active_scope", ""),
            required_ids=tuple(data.get("required_ids", [])),
            policy_version=data.get("policy_version", "compiler-policy-v1"),
        )


@dataclass(frozen=True)
class TraceEntry:
    """Terminal decision for one candidate record. Every record the
    compiler considers gets exactly one entry; early-gate evidence is
    preserved in reason/reason_detail, never dropped."""

    candidate_id: str
    content_identity: str
    representation_id: str
    decision: TraceDecision
    reason_code: str
    reason_detail: str
    priority_band: str
    relevance: float
    marginal_cost: int
    dependency_closure: tuple[str, ...]
    budget_before: int
    budget_after: int
    position: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "content_identity": self.content_identity,
            "representation_id": self.representation_id,
            "decision": self.decision.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "priority_band": self.priority_band,
            "relevance": self.relevance,
            "marginal_cost": self.marginal_cost,
            "dependency_closure": list(self.dependency_closure),
            "budget_before": self.budget_before,
            "budget_after": self.budget_after,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceEntry":
        return cls(
            candidate_id=data["candidate_id"],
            content_identity=data["content_identity"],
            representation_id=data["representation_id"],
            decision=TraceDecision(data["decision"]),
            reason_code=data["reason_code"],
            reason_detail=data.get("reason_detail", ""),
            priority_band=data.get("priority_band", ""),
            relevance=float(data.get("relevance", 0.0)),
            marginal_cost=int(data.get("marginal_cost", 0)),
            dependency_closure=tuple(data.get("dependency_closure", [])),
            budget_before=int(data.get("budget_before", 0)),
            budget_after=int(data.get("budget_after", 0)),
            position=data.get("position"),
        )


@dataclass(frozen=True)
class DecisionTrace:
    """Complete ordered audit of one compilation. Entries sorted by
    candidate_id for deterministic output; decision order is recoverable
    from budget/position fields."""

    request_id: str
    policy_version: str
    entries: tuple[TraceEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DECISION_TRACE_SCHEMA,
            "request_id": self.request_id,
            "policy_version": self.policy_version,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionTrace":
        version = data.get("schema_version", DECISION_TRACE_SCHEMA)
        if version != DECISION_TRACE_SCHEMA:
            raise ValueError(f"unsupported DecisionTrace schema: {version!r}")
        return cls(
            request_id=data["request_id"],
            policy_version=data.get("policy_version", ""),
            entries=tuple(TraceEntry.from_dict(raw) for raw in data.get("entries", [])),
        )

    def decisions_for(self, candidate_id: str) -> tuple[TraceEntry, ...]:
        return tuple(e for e in self.entries if e.candidate_id == candidate_id)


@dataclass(frozen=True)
class CompileFailure:
    """Explicit infeasibility. Never a bundle, never a guess. Reason codes
    are machine-readable; diagnostics carry blocking IDs in deterministic
    order."""

    request_id: str
    policy_version: str
    reason: FailureReason
    blocking_ids: tuple[str, ...]
    budget_used: int
    budget_total: int
    diagnostic: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": COMPILE_FAILURE_SCHEMA,
            "request_id": self.request_id,
            "policy_version": self.policy_version,
            "reason": self.reason.value,
            "blocking_ids": list(self.blocking_ids),
            "budget_used": self.budget_used,
            "budget_total": self.budget_total,
            "diagnostic": self.diagnostic,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompileFailure":
        version = data.get("schema_version", COMPILE_FAILURE_SCHEMA)
        if version != COMPILE_FAILURE_SCHEMA:
            raise ValueError(f"unsupported CompileFailure schema: {version!r}")
        return cls(
            request_id=data["request_id"],
            policy_version=data.get("policy_version", ""),
            reason=FailureReason(data["reason"]),
            blocking_ids=tuple(data.get("blocking_ids", [])),
            budget_used=int(data.get("budget_used", 0)),
            budget_total=int(data.get("budget_total", 0)),
            diagnostic=data.get("diagnostic", ""),
        )


@dataclass(frozen=True)
class CompilationResult:
    """Exactly one of bundle_id/trace (success) or failure/trace. The
    bundle itself travels as a ContextBundle record; only its identity is
    stored here to keep result serialisation small and acyclic."""

    request_id: str
    policy_version: str
    success: bool
    bundle_id: str | None
    bundle_tokens: int | None
    bundle_hash: str | None
    trace: DecisionTrace
    failure: CompileFailure | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": COMPILATION_RESULT_SCHEMA,
            "request_id": self.request_id,
            "policy_version": self.policy_version,
            "success": self.success,
            "bundle_id": self.bundle_id,
            "bundle_tokens": self.bundle_tokens,
            "bundle_hash": self.bundle_hash,
            "trace": self.trace.to_dict(),
            "failure": self.failure.to_dict() if self.failure else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompilationResult":
        version = data.get("schema_version", COMPILATION_RESULT_SCHEMA)
        if version != COMPILATION_RESULT_SCHEMA:
            raise ValueError(f"unsupported CompilationResult schema: {version!r}")
        failure = data.get("failure")
        return cls(
            request_id=data["request_id"],
            policy_version=data.get("policy_version", ""),
            success=bool(data["success"]),
            bundle_id=data.get("bundle_id"),
            bundle_tokens=data.get("bundle_tokens"),
            bundle_hash=data.get("bundle_hash"),
            trace=DecisionTrace.from_dict(data["trace"]),
            failure=CompileFailure.from_dict(failure) if failure else None,
        )
