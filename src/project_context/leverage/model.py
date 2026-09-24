"""Frozen records for the oracle-leverage-v1 measurement layer.

All records are frozen dataclasses with schema versions and JSON
round-trips. Raw attempt evidence is immutable and separate from
derived grading, so a later deterministic regrade never rewrites
model observations. Economics fields use None for unavailable, never
zero. No record carries hidden truth into model-visible state; truth
references live evaluator-side only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GRADER_VERSION = "leverage-grader-v1"
RUNNER_VERSION = "leverage-runner-v1"
RESULT_SCHEMA = "project_context.leverage_result.v1"
ATTEMPT_SCHEMA = "project_context.leverage_attempt.v1"
GRADED_RUN_SCHEMA = "project_context.leverage_graded_run.v1"

PARSE_SCHEMA = "project_context.leverage_parse.v1"
BEHAVIOUR_SCHEMA = "project_context.leverage_behaviour.v1"
ADHERENCE_SCHEMA = "project_context.leverage_adherence.v1"
UTILISATION_SCHEMA = "project_context.leverage_utilisation.v1"
ECONOMICS_SCHEMA = "project_context.leverage_economics.v1"


@dataclass(frozen=True)
class ParseResult:
    """Can the produced state be interpreted for grading? Wrong-but-readable
    parses; only uninterpretable state fails."""

    ok: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": PARSE_SCHEMA, "ok": self.ok, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParseResult":
        return cls(ok=bool(data["ok"]), reason=str(data["reason"]))


@dataclass(frozen=True)
class BehaviourResult:
    """Binary task success plus the independent harmful flag. Harmful is
    fixture-defined behaviour, never code-quality judgement."""

    task_score: float
    harmful_action: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BEHAVIOUR_SCHEMA,
            "task_score": self.task_score,
            "harmful_action": self.harmful_action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BehaviourResult":
        return cls(
            task_score=float(data["task_score"]), harmful_action=bool(data["harmful_action"])
        )


@dataclass(frozen=True)
class ConstraintAdherence:
    """One frozen constraint and whether the produced action adhered to it,
    with a reference to the deterministic evidence. Never inferred from
    task_score."""

    constraint_id: str
    adhered: bool
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ADHERENCE_SCHEMA,
            "constraint_id": self.constraint_id,
            "adhered": self.adhered,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConstraintAdherence":
        return cls(
            constraint_id=str(data["constraint_id"]),
            adhered=bool(data["adhered"]),
            evidence=str(data["evidence"]),
        )


@dataclass(frozen=True)
class UtilisationResult:
    """Observable use of the supplied constraint: the decisive value is
    present in the produced action and the decisive item was admitted
    (transport-observed). Never inferred from condition identity or
    task success; never a claim about hidden reasoning."""

    evidence_use: bool
    admitted: bool
    decisive_present: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": UTILISATION_SCHEMA,
            "evidence_use": self.evidence_use,
            "admitted": self.admitted,
            "decisive_present": self.decisive_present,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UtilisationResult":
        return cls(
            evidence_use=bool(data["evidence_use"]),
            admitted=bool(data["admitted"]),
            decisive_present=bool(data["decisive_present"]),
        )


@dataclass(frozen=True)
class EconomicsResult:
    """Captured economics. Unavailable stays None, never zero."""

    latency_s: float | None
    call_count: int | None
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    reported_cost: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ECONOMICS_SCHEMA,
            "latency_s": self.latency_s,
            "call_count": self.call_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cached_tokens": self.cached_tokens,
            "reported_cost": self.reported_cost,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EconomicsResult":
        return cls(
            latency_s=data["latency_s"],
            call_count=data["call_count"],
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            reasoning_tokens=data.get("reasoning_tokens"),
            cached_tokens=data.get("cached_tokens"),
            reported_cost=data.get("reported_cost"),
        )


@dataclass(frozen=True)
class AttemptEvidence:
    """Immutable raw evidence for one attempt. Written once, never edited.
    No hidden truth inside."""

    experiment_id: str
    run_id: str
    attempt: int
    fixture_id: str
    schedule_position: int
    session_id: str | None
    started_at: str
    ended_at: str
    model: str
    model_digest: str | None
    starting_repo_digest: str
    task_digest: str
    payload_digest: str
    rendered_digest: str | None
    transport: dict[str, Any] = field(default_factory=dict)
    response_summary: dict[str, Any] = field(default_factory=dict)
    final_repo_digest: str | None = None
    economics: dict[str, Any] = field(default_factory=dict)
    infra_status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ATTEMPT_SCHEMA,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "attempt": self.attempt,
            "fixture_id": self.fixture_id,
            "schedule_position": self.schedule_position,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "model": self.model,
            "model_digest": self.model_digest,
            "starting_repo_digest": self.starting_repo_digest,
            "task_digest": self.task_digest,
            "payload_digest": self.payload_digest,
            "rendered_digest": self.rendered_digest,
            "transport": dict(self.transport),
            "response_summary": dict(self.response_summary),
            "final_repo_digest": self.final_repo_digest,
            "economics": dict(self.economics),
            "infra_status": self.infra_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AttemptEvidence":
        return cls(
            experiment_id=data["experiment_id"],
            run_id=data["run_id"],
            attempt=int(data["attempt"]),
            fixture_id=data["fixture_id"],
            schedule_position=int(data["schedule_position"]),
            session_id=data.get("session_id"),
            started_at=data["started_at"],
            ended_at=data["ended_at"],
            model=data["model"],
            model_digest=data.get("model_digest"),
            starting_repo_digest=data["starting_repo_digest"],
            task_digest=data["task_digest"],
            payload_digest=data["payload_digest"],
            rendered_digest=data.get("rendered_digest"),
            transport=dict(data.get("transport", {})),
            response_summary=dict(data.get("response_summary", {})),
            final_repo_digest=data.get("final_repo_digest"),
            economics=dict(data.get("economics", {})),
            infra_status=data.get("infra_status", "ok"),
        )


@dataclass(frozen=True)
class GradedRun:
    """Derived grading for one run, separate from raw attempts. Graded by
    run output only; the grader never sees the condition."""

    run_id: str
    fixture_id: str
    grader_version: str
    parse: ParseResult
    behaviour: BehaviourResult
    adherence: tuple[ConstraintAdherence, ...]
    utilisation: UtilisationResult
    valid: bool
    exclusion_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GRADED_RUN_SCHEMA,
            "run_id": self.run_id,
            "fixture_id": self.fixture_id,
            "grader_version": self.grader_version,
            "parse": self.parse.to_dict(),
            "behaviour": self.behaviour.to_dict(),
            "adherence": [a.to_dict() for a in self.adherence],
            "utilisation": self.utilisation.to_dict(),
            "valid": self.valid,
            "exclusion_reason": self.exclusion_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GradedRun":
        return cls(
            run_id=data["run_id"],
            fixture_id=data["fixture_id"],
            grader_version=data.get("grader_version", GRADER_VERSION),
            parse=ParseResult.from_dict(data["parse"]),
            behaviour=BehaviourResult.from_dict(data["behaviour"]),
            adherence=tuple(ConstraintAdherence.from_dict(a) for a in data["adherence"]),
            utilisation=UtilisationResult.from_dict(data["utilisation"]),
            valid=bool(data["valid"]),
            exclusion_reason=data.get("exclusion_reason"),
        )
