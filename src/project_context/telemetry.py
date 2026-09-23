"""Token and cost accounting. Three separations are structural here:

1. Provider-reported vs locally estimated tokens are never merged. Every
   count carries provenance (TokenCount.source).
2. Usage observation vs pricing schedule vs calculated cost are three
   distinct records. Prices live in versioned PriceSchedule objects, never
   inline in code paths.
3. Stage 0 spends no real money: the only schedule shipped is an explicitly
   synthetic one with round, implausible numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class TokenSource:
    PROVIDER = "provider"
    LOCAL_TOKENIZER = "local-tokenizer"
    APPROXIMATION = "approximation"
    UNAVAILABLE = "unavailable"

    ALL = (PROVIDER, LOCAL_TOKENIZER, APPROXIMATION, UNAVAILABLE)


@dataclass(frozen=True)
class TokenCount:
    """A token count that cannot be separated from how it was obtained.
    value None means unobserved (with source UNAVAILABLE), never zero."""

    value: int | None
    source: str

    def __post_init__(self) -> None:
        if self.source not in TokenSource.ALL:
            raise ValueError(f"unknown token source: {self.source!r}")
        if self.value is None and self.source != TokenSource.UNAVAILABLE:
            raise ValueError("None value requires source 'unavailable'")
        if self.value is not None and self.value < 0:
            raise ValueError("token counts cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenCount":
        return cls(value=data.get("value"), source=data.get("source", "unavailable"))

    @staticmethod
    def unavailable() -> "TokenCount":
        return TokenCount(value=None, source=TokenSource.UNAVAILABLE)


SYNTHETIC_PRICE_SCHEDULE_V1 = "synthetic-price-schedule-v1"


@dataclass(frozen=True)
class PriceSchedule:
    """Versioned price list. Historical invocations are recomputed against
    the schedule version recorded on the invocation, never today's prices."""

    schedule_id: str
    per_million_input: float
    per_million_output: float
    per_million_cached_read: float
    per_million_cached_write: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "per_million_input": self.per_million_input,
            "per_million_output": self.per_million_output,
            "per_million_cached_read": self.per_million_cached_read,
            "per_million_cached_write": self.per_million_cached_write,
        }


def synthetic_price_schedule() -> PriceSchedule:
    """Deliberately round, implausible numbers. SYNTHETIC ONLY: any cost
    computed under this schedule is not a book cost claim."""
    return PriceSchedule(
        schedule_id=SYNTHETIC_PRICE_SCHEDULE_V1,
        per_million_input=10.0,
        per_million_output=30.0,
        per_million_cached_read=1.0,
        per_million_cached_write=12.5,
    )


def _rate(count: TokenCount | None) -> int:
    if count is None or count.value is None:
        return 0
    return count.value


def calculate_cost(
    *,
    input_tokens: TokenCount,
    output_tokens: TokenCount,
    schedule: PriceSchedule,
    cached_read_tokens: TokenCount | None = None,
    cached_write_tokens: TokenCount | None = None,
) -> dict[str, Any]:
    """Pure function: usage observation + schedule -> cost breakdown.
    Unobserved components contribute zero and are flagged as such."""
    ordinary = _rate(input_tokens) - _rate(cached_read_tokens) - _rate(cached_write_tokens)
    ordinary = max(0, ordinary)
    cost = (
        ordinary * schedule.per_million_input
        + _rate(output_tokens) * schedule.per_million_output
        + _rate(cached_read_tokens) * schedule.per_million_cached_read
        + _rate(cached_write_tokens) * schedule.per_million_cached_write
    ) / 1_000_000
    return {
        "schedule_id": schedule.schedule_id,
        "ordinary_input_tokens": ordinary,
        "cost_usd": cost,
        "unobserved_components": [
            name
            for name, count in (
                ("cached_read_tokens", cached_read_tokens),
                ("cached_write_tokens", cached_write_tokens),
            )
            if count is None or count.value is None
        ],
    }
