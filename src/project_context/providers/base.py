"""Minimal provider-observation normaliser. Stage 0 ships no real provider
adapters (no API calls, no money). This base defines the translation
contract later adapters must honour: preserve raw payloads, keep
unsupported metrics unavailable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_context.telemetry import TokenCount, TokenSource


@dataclass(frozen=True)
class ProviderObservation:
    """Normalised telemetry for one model call. Raw provider payload is
    retained alongside (when safe) so normalisation is auditable."""

    provider: str
    model: str
    input_tokens: TokenCount
    output_tokens: TokenCount
    reasoning_tokens: TokenCount | None = None
    cached_read_tokens: TokenCount | None = None
    cached_write_tokens: TokenCount | None = None
    latency_ms: float | None = None
    raw_payload: tuple[tuple[str, str], ...] = ()

    @staticmethod
    def _count(payload: dict[str, Any], *keys: str) -> TokenCount:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, int):
                return TokenCount(value=value, source=TokenSource.PROVIDER)
        return TokenCount.unavailable()

    @classmethod
    def from_mapping(
        cls,
        provider: str,
        model: str,
        payload: dict[str, Any],
        *,
        latency_ms: float | None = None,
    ) -> "ProviderObservation":
        """Best-effort translation. Unknown fields are ignored; missing
        fields become unavailable. Nothing is estimated here."""
        return cls(
            provider=provider,
            model=model,
            input_tokens=cls._count(payload, "input_tokens", "prompt_tokens"),
            output_tokens=cls._count(payload, "output_tokens", "completion_tokens"),
            reasoning_tokens=cls._count(payload, "reasoning_tokens"),
            cached_read_tokens=cls._count(
                payload,
                "cached_tokens",
                "cache_read_input_tokens",
                "prompt_cache_hit_tokens",
            ),
            cached_write_tokens=cls._count(payload, "cache_write_tokens"),
            latency_ms=latency_ms,
            raw_payload=tuple((k, str(v)) for k, v in payload.items()),
        )
