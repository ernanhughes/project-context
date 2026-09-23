"""Ingest bridge records into ContextBundle + ModelInvocation.

Mapping rules (V1 boundary, documented limits inline):

- One bridge record becomes exactly one ContextBundle. Bundles carry
  CaptureProvenance (source_type opencode_capture) with session scope and
  per-scope sequence index; bundle ids are `opencode-<capture_id>`.
- System strings become kind=system_instruction items, in order.
- Message parts become one item per part: text parts carry their text;
  completed tool parts carry title plus output (input args are NOT copied
  into derived items; the raw capture retains full fidelity); unknown part
  shapes become kind=other_message_part with their JSON as content, so
  nothing is silently dropped. Item `ref` carries call/message/part ids.
- Tool-after records become a single tool_result item.
- ModelInvocation links the bundle; provider/model come from the record
  where present, everything usage-related stays None (unavailable).
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from project_context.domain.bundles import ContextBundle, build_bundle
from project_context.domain.invocations import ModelInvocation
from project_context.domain.items import ContextItem, make_item
from project_context.domain.provenance import CaptureProvenance
from project_context.telemetry import TokenCount

SOURCE_TYPE = "opencode_capture"


def _text_item(
    *,
    item_id: str,
    source: str,
    kind: str,
    content: str,
    authority: str | None,
    scope: str,
    observed_at: str,
    ref: str | None,
    semantic_id: str | None = None,
) -> ContextItem:
    base = make_item(
        id=item_id,
        source=source,
        kind=kind,
        content=content,
        authority=authority,
        scope=scope,
        semantic_id=semantic_id,
    )
    return ContextItem(
        id=base.id,
        source=base.source,
        kind=base.kind,
        content=base.content,
        position=0,
        token_count=base.token_count,
        token_provenance=base.token_provenance,
        authority=base.authority,
        scope=base.scope,
        observed_at=observed_at,
        semantic_id=base.semantic_id,
        ref=ref,
    )


def _part_kind(role: str | None, part: dict[str, Any]) -> str:
    part_type = part.get("type")
    if part_type == "text":
        if role == "user":
            return "conversation_user"
        if role == "assistant":
            return "conversation_assistant"
        return "text_part"
    if part_type == "tool":
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        if isinstance(state, dict) and state.get("status") == "completed":
            return "tool_result"
        return "tool_call"
    if part_type == "reasoning":
        return "reasoning_part"
    return "other_message_part"


def _part_content(part: dict[str, Any], kind: str) -> str:
    if kind in ("conversation_user", "conversation_assistant", "text_part"):
        text = part.get("text")
        if isinstance(text, str):
            return text
    if kind in ("tool_result", "tool_call"):
        state = part.get("state")
        if isinstance(state, dict):
            output = state.get("output")
            title = state.get("title", "")
            if isinstance(output, str):
                head = f"[tool:{part.get('tool')} call:{part.get('callID')} title:{title}]"
                return f"{head}\n{output}" if output else head
    if kind == "reasoning_part":
        text = part.get("text")
        if isinstance(text, str):
            return text
    return json.dumps(part, sort_keys=True)


def _part_ref(part: dict[str, Any]) -> str | None:
    for key in ("callID", "id"):
        value = part.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _message_role(message: Any) -> str | None:
    if isinstance(message, dict) and isinstance(message.get("role"), str):
        return message["role"]
    return None


def record_to_items(record: dict[str, Any], observed_at: str) -> list[ContextItem]:
    """Map one validated bridge record to ordered ContextItems (positions
    assigned later by the bundle builder). Unknown shapes are preserved
    opaquely, never dropped."""
    payload = record.get("payload", {})
    hook = record.get("hook_kind")
    items: list[ContextItem] = []
    counter = [0]

    def add(source: str, kind: str, content: Any, ref: str | None) -> None:
        text = content if isinstance(content, str) else json.dumps(content, sort_keys=True)
        counter[0] += 1
        items.append(
            _text_item(
                item_id=f"{record.get('capture_id')}-p{counter[0]:03d}",
                source=source,
                kind=kind,
                content=text,
                authority=None,
                scope="session" if record.get("session_id") else "unknown",
                observed_at=observed_at,
                ref=ref,
            )
        )

    if hook == "system.transform":
        system = payload.get("system", [])
        entries = system if isinstance(system, list) else [system]
        for entry in entries:
            add("opencode-system", "system_instruction", entry, None)
    elif hook in ("messages.transform", "chat.message"):
        messages: Any = []
        if hook == "messages.transform":
            messages = payload.get("messages", [])
        else:
            admission = payload.get("admission", {})
            if isinstance(admission, dict):
                messages = [{"info": admission.get("message"), "parts": admission.get("parts", [])}]
        if not isinstance(messages, list):
            messages = []
        for message in messages:
            if not isinstance(message, dict):
                add("opencode-messages", "other_message_part", message, None)
                continue
            role = _message_role(message.get("info"))
            parts = message.get("parts", [])
            if not isinstance(parts, list) or not parts:
                add("opencode-messages", "other_message_part", message, None)
                continue
            for part in parts:
                if not isinstance(part, dict):
                    add("opencode-messages", "other_message_part", part, None)
                    continue
                kind = _part_kind(role, part)
                add("opencode-messages", kind, _part_content(part, kind), _part_ref(part))
    elif hook == "tool.execute.after":
        result = payload.get("tool_result", {})
        if not isinstance(result, dict):
            result = {}
        title = result.get("title", "")
        output = result.get("output", "")
        text = f"[tool:{result.get('tool')} call:{result.get('callID')} title:{title}]"
        if isinstance(output, str) and output:
            text += f"\n{output}"
        call_ref = result.get("callID")
        add(
            "opencode-tool",
            "tool_result",
            text,
            call_ref if isinstance(call_ref, str) else None,
        )
    else:
        add("opencode-unknown", "other_message_part", payload, None)
    return items


class SequenceTracker:
    """Per-scope monotonic counters. Scope is the record's sequence_scope
    (a session id or 'unlinked'). Counters are ingestion-local; they order
    observations, not model dispatches."""

    def __init__(self) -> None:
        self._next: dict[str, int] = defaultdict(int)

    def assign(self, scope: str) -> int:
        self._next[scope] += 1
        return self._next[scope]


def _model_ids(record: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    model = record.get("model")
    if not isinstance(model, dict):
        return None, None, None
    provider = model.get("provider_id")
    ident = model.get("id")
    variant = model.get("variant")
    return (
        provider if isinstance(provider, str) else None,
        ident if isinstance(ident, str) else None,
        variant if isinstance(variant, str) else None,
    )


def ingest_record(
    record: dict[str, Any], tracker: SequenceTracker
) -> tuple[ContextBundle, ModelInvocation]:
    """One validated bridge record becomes one bundle plus one linked
    invocation. Raises on unknown hook kinds only if the record failed
    bridge validation first (callers validate before ingesting)."""
    capture_id = str(record.get("capture_id", "unknown"))
    captured_at = str(record.get("captured_at", ""))
    session = record.get("session_id")
    session_ref = session if isinstance(session, str) else None
    scope = str(record.get("sequence_scope", "unlinked"))
    index = tracker.assign(scope)
    provider_id, model_id, _variant = _model_ids(record)

    provenance = CaptureProvenance(
        source_type=SOURCE_TYPE,
        capture_schema=str(record.get("schema", "")),
        capture_id=capture_id,
        capture_stage=str(record.get("capture_stage", "")),
        session_ref=session_ref,
        sequence_index=index,
        adapter_version=record.get("adapter_version")
        if isinstance(record.get("adapter_version"), str)
        else None,
        opencode_version=record.get("opencode_version")
        if isinstance(record.get("opencode_version"), str)
        else None,
    )
    bundle = build_bundle(
        record_to_items(record, captured_at),
        bundle_id=f"opencode-{capture_id}",
        created_at=captured_at,
        evidence_class="opencode_capture",
        provenance=provenance,
    )
    invocation = ModelInvocation(
        id=f"inv-{capture_id}",
        bundle_id=bundle.id,
        provider=provider_id or "unknown",
        model=model_id or "unknown",
        started_at=captured_at,
        completed_at=captured_at,
        input_tokens=TokenCount(value=None, source="unavailable"),
        output_tokens=TokenCount(value=None, source="unavailable"),
        reasoning_tokens=None,
        cached_read_tokens=None,
        cached_write_tokens=None,
        latency_ms=None,
        cost_usd=None,
        cost_schedule_id=None,
        observation_only=True,
    )
    return bundle, invocation
