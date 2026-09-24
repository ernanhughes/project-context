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


def is_moving_alias(model: str) -> bool:
    """True when a model name is a moving alias: no tag, or the `latest`
    tag. Such a name can resolve to different weights on different days,
    so a run made under it is not reproducible from the name alone."""
    _, sep, tag = model.partition(":")
    return not sep or tag == "latest"


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
        self._identity: dict[str, str | None] | None = None
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
        info["model_alias_moving"] = is_moving_alias(self._config.model)
        if self._identity is not None:
            info.update(self._identity)
        return info

    def resolve_identity(self) -> dict[str, str | None]:
        """Best-effort stable identity of the served model.

        Asks the local Ollama native API (`/api/tags`, the endpoint root
        without the OpenAI-compatible `/v1` suffix) for the digest of the
        exact configured model name. Nothing is inferred: when the
        endpoint does not answer or does not list the model, the digest
        stays None with source "unavailable". A digest identifies the
        weights actually served; the model name alone does not.
        """
        digest: str | None = None
        source = "unavailable"
        root = self._config.base_url.rstrip("/")
        if root.endswith("/v1"):
            root = root[: -len("/v1")]
        try:
            status, payload = self._transport("GET", root + "/api/tags", self._headers(), b"")
            if status == 200:
                listed = json.loads(payload.decode("utf-8")).get("models", [])
                for entry in listed if isinstance(listed, list) else []:
                    if not isinstance(entry, dict):
                        continue
                    if self._config.model in (entry.get("name"), entry.get("model")):
                        raw = entry.get("digest")
                        if isinstance(raw, str) and raw:
                            digest = raw
                            source = "ollama-api-tags"
                        break
        except (OSError, TimeoutError, ValueError, AttributeError):
            pass
        self._identity = {"model_digest": digest, "model_identity_source": source}
        return dict(self._identity)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = "Bearer " + self._config.api_key
        return headers

    def invoke(self, request: ReaderRequest) -> ReaderResponse:
        if request.actions:
            response_format: dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "action",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": list(request.actions)},
                            "target": {"type": ["string", "null"]},
                            "value": {"type": ["string", "null"]},
                            "reason_code": {"type": ["string", "null"]},
                        },
                        "required": ["action", "target", "value", "reason_code"],
                        "additionalProperties": False,
                    },
                },
            }
        else:
            response_format = {"type": "json_object"}
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
                "response_format": response_format,
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
            model_version=self._model_version(),
            latency_ms=latency_ms,
            input_tokens=count("prompt_tokens"),
            output_tokens=count("completion_tokens"),
            reasoning_tokens=count("reasoning_tokens", "completion_tokens_details"),
        )

    def _model_version(self) -> str | None:
        if self._identity and self._identity.get("model_digest"):
            return "digest:" + str(self._identity["model_digest"])
        return None


def _join_blocks(blocks: Any) -> str:
    parts: list[str] = []
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "".join(parts)
