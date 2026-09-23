"""Reader request/response records. Transport-agnostic; adapters map
these onto provider calls. Telemetry uses TokenCount provenance exactly
like Stage 0: provider-reported where exposed, unavailable otherwise."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from project_context.telemetry import TokenCount

READER_REQUEST_SCHEMA = "project_context.reader_request.v1"
READER_RESPONSE_SCHEMA = "project_context.reader_response.v1"


@dataclass(frozen=True)
class ReaderRequest:
    """One isolated inference. No conversation, no tools, no memory."""

    case_id: str
    system_text: str
    task_text: str
    context_text: str
    schema_text: str
    temperature: float
    seed: int
    max_tokens: int
    actions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": READER_REQUEST_SCHEMA,
            "case_id": self.case_id,
            "system_text": self.system_text,
            "task_text": self.task_text,
            "context_text": self.context_text,
            "schema_text": self.schema_text,
            "temperature": self.temperature,
            "seed": self.seed,
            "max_tokens": self.max_tokens,
            "actions": list(self.actions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReaderRequest":
        version = data.get("schema_version", READER_REQUEST_SCHEMA)
        if version != READER_REQUEST_SCHEMA:
            raise ValueError(f"unsupported ReaderRequest schema: {version!r}")
        return cls(
            case_id=data["case_id"],
            system_text=data["system_text"],
            task_text=data["task_text"],
            context_text=data["context_text"],
            schema_text=data["schema_text"],
            temperature=float(data["temperature"]),
            seed=int(data["seed"]),
            max_tokens=int(data["max_tokens"]),
            actions=tuple(data.get("actions", ())),
        )


@dataclass(frozen=True)
class ReaderResponse:
    """Raw provider outcome. Malformed model output stays raw here; the
    parser decides parse_status downstream. Transport errors raise in the
    adapter and never become responses."""

    raw_text: str
    provider: str
    model: str
    model_version: str | None
    latency_ms: float | None
    input_tokens: TokenCount
    output_tokens: TokenCount
    reasoning_tokens: TokenCount | None = None
    cached_read_tokens: TokenCount | None = None
    cached_write_tokens: TokenCount | None = None

    def to_dict(self) -> dict[str, Any]:
        def tok(value: TokenCount | None) -> dict[str, Any] | None:
            return value.to_dict() if value is not None else None

        return {
            "schema_version": READER_RESPONSE_SCHEMA,
            "raw_text": self.raw_text,
            "provider": self.provider,
            "model": self.model,
            "model_version": self.model_version,
            "latency_ms": self.latency_ms,
            "input_tokens": tok(self.input_tokens),
            "output_tokens": tok(self.output_tokens),
            "reasoning_tokens": tok(self.reasoning_tokens),
            "cached_read_tokens": tok(self.cached_read_tokens),
            "cached_write_tokens": tok(self.cached_write_tokens),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReaderResponse":
        version = data.get("schema_version", READER_RESPONSE_SCHEMA)
        if version != READER_RESPONSE_SCHEMA:
            raise ValueError(f"unsupported ReaderResponse schema: {version!r}")

        def tok(raw: dict[str, Any] | None) -> TokenCount | None:
            return TokenCount.from_dict(raw) if raw is not None else None

        return cls(
            raw_text=data["raw_text"],
            provider=data["provider"],
            model=data["model"],
            model_version=data.get("model_version"),
            latency_ms=data.get("latency_ms"),
            input_tokens=TokenCount.from_dict(data["input_tokens"]),
            output_tokens=TokenCount.from_dict(data["output_tokens"]),
            reasoning_tokens=tok(data.get("reasoning_tokens")),
            cached_read_tokens=tok(data.get("cached_read_tokens")),
            cached_write_tokens=tok(data.get("cached_write_tokens")),
        )


class ReaderTransportError(RuntimeError):
    """Transport/provider failure. Runners retry these; they never retry
    valid model behaviour."""


class ReaderAdapter(Protocol):
    """Narrow live-reader contract. Implementations: fake (tests),
    OpenAI-compatible HTTP (Stage 4 primary wave)."""

    @property
    def name(self) -> str:
        """Stable adapter identity, e.g. 'fake' or 'ollama-local'."""
        ...

    def describe(self) -> dict[str, Any]:
        """Provider/model identity for run provenance. No secrets, ever."""
        ...

    def invoke(self, request: ReaderRequest) -> ReaderResponse:
        """One isolated inference. Transport/provider errors raise."""
        ...
