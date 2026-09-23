"""Actual execution of one bundle: provider, model, telemetry, cost.

Telemetry discipline (book Chapter 9): provider-reported and locally
estimated tokens are never merged. Every count carries provenance via
telemetry.TokenCount. Unavailable metrics stay None; None is not zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_context.telemetry import TokenCount

SCHEMA_VERSION = "project_context.model_invocation.v1"


@dataclass(frozen=True)
class ModelInvocation:
    id: str
    bundle_id: str
    provider: str
    model: str
    started_at: str
    completed_at: str
    input_tokens: TokenCount
    output_tokens: TokenCount
    model_version: str | None = None
    reasoning_tokens: TokenCount | None = None
    cached_read_tokens: TokenCount | None = None
    cached_write_tokens: TokenCount | None = None
    latency_ms: float | None = None
    cost_usd: float | None = None
    cost_schedule_id: str | None = None
    observation_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        def tok(value: TokenCount | None) -> dict[str, Any] | None:
            return value.to_dict() if value is not None else None

        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "bundle_id": self.bundle_id,
            "provider": self.provider,
            "model": self.model,
            "model_version": self.model_version,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "input_tokens": tok(self.input_tokens),
            "output_tokens": tok(self.output_tokens),
            "reasoning_tokens": tok(self.reasoning_tokens),
            "cached_read_tokens": tok(self.cached_read_tokens),
            "cached_write_tokens": tok(self.cached_write_tokens),
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "cost_schedule_id": self.cost_schedule_id,
            "observation_only": self.observation_only,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelInvocation":
        version = data.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported ModelInvocation schema: {version!r}")

        def tok(raw: dict[str, Any] | None) -> TokenCount | None:
            return TokenCount.from_dict(raw) if raw is not None else None

        return cls(
            id=data["id"],
            bundle_id=data["bundle_id"],
            provider=data["provider"],
            model=data["model"],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            input_tokens=TokenCount.from_dict(data["input_tokens"]),
            output_tokens=TokenCount.from_dict(data["output_tokens"]),
            model_version=data.get("model_version"),
            reasoning_tokens=tok(data.get("reasoning_tokens")),
            cached_read_tokens=tok(data.get("cached_read_tokens")),
            cached_write_tokens=tok(data.get("cached_write_tokens")),
            latency_ms=data.get("latency_ms"),
            cost_usd=data.get("cost_usd"),
            cost_schedule_id=data.get("cost_schedule_id"),
            observation_only=data.get("observation_only", True),
        )
