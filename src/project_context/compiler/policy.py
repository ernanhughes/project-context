"""Explicit versioned compiler policy. One immutable record with separated
concerns; behaviour lives in engine.py, numbers live here. Serialisable so
frozen runs can pin exactly which policy decided."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COMPILER_POLICY_SCHEMA = "project_context.compiler_policy.v1"
DEFAULT_POLICY_VERSION = "compiler-policy-v1"


@dataclass(frozen=True)
class CompilerPolicy:
    """Staged deterministic admission policy.

    `min_discretionary_relevance`: a PREFERRED/DISCRETIONARY candidate
    earns admission only if it fits and either meets this relevance or
    covers a previously uncovered coverage key.
    `mandatory_form`: cheapest legal form first ("cheapest") — the only
    supported mode in Stage 3.
    `order_roles`: deterministic render role order; unknown roles sort
    last, ties break by candidate_id.
    `repair`: render-overrun repair mode ("drop-last-discretionary").
    """

    policy_version: str
    min_discretionary_relevance: float
    mandatory_form: str
    order_roles: tuple[str, ...]
    repair: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": COMPILER_POLICY_SCHEMA,
            "policy_version": self.policy_version,
            "min_discretionary_relevance": self.min_discretionary_relevance,
            "mandatory_form": self.mandatory_form,
            "order_roles": list(self.order_roles),
            "repair": self.repair,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompilerPolicy":
        version = data.get("schema_version", COMPILER_POLICY_SCHEMA)
        if version != COMPILER_POLICY_SCHEMA:
            raise ValueError(f"unsupported CompilerPolicy schema: {version!r}")
        return cls(
            policy_version=data.get("policy_version", DEFAULT_POLICY_VERSION),
            min_discretionary_relevance=float(data.get("min_discretionary_relevance", 0.3)),
            mandatory_form=data.get("mandatory_form", "cheapest"),
            order_roles=tuple(
                data.get(
                    "order_roles",
                    ("instruction", "task", "state", "evidence", "support", "tool"),
                )
            ),
            repair=data.get("repair", "drop-last-discretionary"),
        )


def default_policy() -> CompilerPolicy:
    return CompilerPolicy(
        policy_version=DEFAULT_POLICY_VERSION,
        min_discretionary_relevance=0.3,
        mandatory_form="cheapest",
        order_roles=("instruction", "task", "state", "evidence", "support", "tool"),
        repair="drop-last-discretionary",
    )
