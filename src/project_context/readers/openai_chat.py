"""OpenAI-compatible chat completions reader over stdlib HTTP.

One narrow adapter: single request, temperature/seed/max_tokens,
JSON-object response format, usage telemetry where exposed. The HTTP
transport is injectable so tests exercise request-building and response
parsing without network. Secrets travel in headers only and are never
logged, stored, or included in any artifact.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from project_context.readers.domain import (
    ReaderRequest,
    ReaderResponse,
    ReaderTransportError,
)
from project_context.telemetry import TokenCount, TokenSource

Transport = Callable[[str, str, dict[str, str], bytes], tuple[int, bytes]]


def urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes, timeout: int = 120
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


@dataclass(frozen=True)
class OpenAIChatConfig:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: int = 120

    def redacted(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "api_key_present": self.api_key is not None,
            "timeout_seconds": self.timeout_seconds,
        }


class OpenAIChatAdapter:
    """Single-shot chat completions reader. No sessions, no tools, no
    retrieval: one POST per invoke, connection closed afterwards.

    base_url is the OpenAI-compatible API root, e.g.
    http://localhost:11434/v1 — `/chat/completions` is appended."""

    def __init__(
        self,
        config: OpenAIChatConfig,
        transport: Transport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or (
            lambda method, url, headers, body: urllib_transport(
                method, url, headers, body, timeout=config.timeout_seconds
            )
        )

    @property
    def name(self) -> str:
        return "openai-chat"

    def describe(self) -> dict[str, Any]:
        info = self._config.redacted()
        info["adapter"] = self.name
        info["live"] = True
        return info

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = "Bearer " + self._config.api_key
        return headers

    def invoke(self, request: ReaderRequest) -> ReaderResponse:
        body = json.dumps(
            {
                "model": self._config.model,
                "messages": [
                    {"role": "system", "content": request.system_text},
                    {"role": "user", "content": request.task_text + request.context_text},
                ],
                "temperature": request.temperature,
                "seed": request.seed,
                "max_tokens": request.max_tokens,
                "response_format": {"type": "json_object"},
            },
            sort_keys=True,
        ).encode("utf-8")
        started = time.perf_counter()
        try:
            status, payload = self._transport(
                "POST",
                self._config.base_url.rstrip("/") + "/chat/completions",
                self._headers(),
                body,
            )
        except (OSError, TimeoutError, ValueError) as exc:
            raise ReaderTransportError(f"transport failed: {type(exc).__name__}") from exc
        latency_ms = (time.perf_counter() - started) * 1000.0
        if status != 200:
            raise ReaderTransportError(f"HTTP status {status}")
        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ReaderTransportError("unreadable response body") from exc
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ReaderTransportError("missing choices/message/content") from exc
        text = content if isinstance(content, str) else _join_blocks(content)
        usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}

        def count(*keys: str) -> TokenCount:
            for key in keys:
                value = usage.get(key)
                if isinstance(value, bool):
                    continue
                if isinstance(value, int) and value >= 0:
                    return TokenCount(value=value, source=TokenSource.PROVIDER)
            return TokenCount.unavailable()

        return ReaderResponse(
            raw_text=text,
            provider="openai-compatible",
            model=str(data.get("model", self._config.model)),
            model_version=None,
            latency_ms=latency_ms,
            input_tokens=count("prompt_tokens"),
            output_tokens=count("completion_tokens"),
            reasoning_tokens=count("reasoning_tokens", "completion_tokens_details"),
        )


def _join_blocks(blocks: Any) -> str:
    parts: list[str] = []
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "".join(parts)
