"""Evidence about an invocation, bundle, or probe. Append-only: observations
accumulate in an EvaluationLog; nothing already recorded is ever mutated."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


SCHEMA_VERSION = "project_context.evaluation_observation.v1"


@dataclass(frozen=True)
class EvaluationObservation:
    id: str
    target_type: str
    target_id: str
    metric: str
    value: str
    verdict: Verdict
    evidence: str
    evaluator: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "metric": self.metric,
            "value": self.value,
            "verdict": self.verdict.value,
            "evidence": self.evidence,
            "evaluator": self.evaluator,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluationObservation":
        version = data.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported EvaluationObservation schema: {version!r}")
        return cls(
            id=data["id"],
            target_type=data["target_type"],
            target_id=data["target_id"],
            metric=data["metric"],
            value=data["value"],
            verdict=Verdict(data["verdict"]),
            evidence=data["evidence"],
            evaluator=data["evaluator"],
            created_at=data["created_at"],
        )


@dataclass(frozen=True)
class EvaluationLog:
    """Append-only sequence. append() returns a NEW log; the old one is
    unchanged. This is what makes silent mutation of evidence impossible
    by construction rather than by convention."""

    observations: tuple[EvaluationObservation, ...] = ()

    def append(self, observation: EvaluationObservation) -> "EvaluationLog":
        return EvaluationLog(observations=self.observations + (observation,))

    def to_dict(self) -> dict[str, Any]:
        return {"observations": [obs.to_dict() for obs in self.observations]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluationLog":
        return cls(
            observations=tuple(
                EvaluationObservation.from_dict(raw) for raw in data.get("observations", [])
            )
        )
