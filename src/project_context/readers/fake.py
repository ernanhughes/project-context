"""Scripted reader for offline development and tests. Maps case-ID
substrings to canned behaviours. Never performs network IO; a source
scan test pins that."""

from __future__ import annotations

from dataclasses import dataclass, field

from project_context.readers.domain import (
    ReaderAdapter,
    ReaderRequest,
    ReaderResponse,
    ReaderTransportError,
)
from project_context.telemetry import TokenCount


@dataclass
class FakeReader:
    """Scripted responses keyed by case-ID substring match.

    rules: list of (substring, outcome) where outcome is one of:
      {"ok": "<raw text>"} — valid response with fixed telemetry
      {"malformed": "<raw text>"} — unparseable response
      {"error": "<message>"} — raises FakeProviderError
    Unmatched cases return default_ok.
    """

    name: str = "fake"
    rules: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    default_ok: str = (
        '{"action": "ABSTAIN", "target": null, "value": null, "reason_code": "unknown"}'
    )
    calls: list[str] = field(default_factory=list)

    def describe(self) -> dict[str, object]:
        return {"adapter": self.name, "model": "fake-scripted-v1", "live": False}

    def invoke(self, request: ReaderRequest) -> ReaderResponse:
        self.calls.append(request.case_id)
        for substring, outcome in self.rules:
            if substring in request.case_id:
                if "error" in outcome:
                    raise FakeProviderError(outcome["error"])
                return ReaderResponse(
                    raw_text=outcome.get("ok", outcome.get("malformed", "")),
                    provider="fake",
                    model="fake-scripted-v1",
                    model_version=None,
                    latency_ms=1.0,
                    input_tokens=TokenCount(value=100, source="approximation"),
                    output_tokens=TokenCount(value=10, source="approximation"),
                )
        return ReaderResponse(
            raw_text=self.default_ok,
            provider="fake",
            model="fake-scripted-v1",
            model_version=None,
            latency_ms=1.0,
            input_tokens=TokenCount(value=100, source="approximation"),
            output_tokens=TokenCount(value=10, source="approximation"),
        )


class FakeProviderError(ReaderTransportError):
    """Controlled provider failure for retry-policy tests."""


def _adapter_protocol_satisfied() -> bool:
    adapter: ReaderAdapter = FakeReader()
    return adapter.name == "fake"
