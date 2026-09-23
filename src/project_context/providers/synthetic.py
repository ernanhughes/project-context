"""Deterministic synthetic provider for tests and scaffolding. Produces
ModelInvocation records WITHOUT calling any model: telemetry is derived
from the bundle by fixed rules, and every record is marked synthetic."""

from __future__ import annotations

import hashlib

from project_context.domain.bundles import ContextBundle
from project_context.domain.invocations import ModelInvocation
from project_context.telemetry import (
    TokenCount,
    TokenSource,
    calculate_cost,
    synthetic_price_schedule,
)

PROVIDER_NAME = "synthetic"
MODEL_NAME = "synthetic-deterministic-v1"


def observe_bundle(
    bundle: ContextBundle, *, invocation_id: str, started_at: str, completed_at: str
) -> ModelInvocation:
    """Build a synthetic invocation: input tokens come from the bundle's
    rendered total (approximation provenance preserved), output is a
    content-hash-derived small integer (NOT model output)."""
    digest = hashlib.sha256(bundle.content_hash().encode("utf-8")).hexdigest()
    pseudo_output = int(digest[:4], 16) % 64 + 8
    schedule = synthetic_price_schedule()
    input_tokens = TokenCount(value=bundle.rendered_token_total(), source=TokenSource.APPROXIMATION)
    output_tokens = TokenCount(value=pseudo_output, source=TokenSource.APPROXIMATION)
    cost = calculate_cost(input_tokens=input_tokens, output_tokens=output_tokens, schedule=schedule)
    return ModelInvocation(
        id=invocation_id,
        bundle_id=bundle.id,
        provider=PROVIDER_NAME,
        model=MODEL_NAME,
        started_at=started_at,
        completed_at=completed_at,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=TokenCount.unavailable(),
        cached_read_tokens=TokenCount.unavailable(),
        cached_write_tokens=TokenCount.unavailable(),
        latency_ms=None,
        cost_usd=cost["cost_usd"],
        cost_schedule_id=schedule.schedule_id,
        observation_only=True,
    )
