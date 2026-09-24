"""Ingest V2 bridge records into ContextBundle + ModelInvocation.

Mapping rules (V2 boundary ``opencode.v2.model_context``):

- One bridge record becomes exactly one ContextBundle. Bundles carry
  CaptureProvenance (source_type opencode_capture) with session scope and
  the adapter-assigned ``invocation_sequence``; bundle ids are
  ``opencode-<capture_id>``.
- System parts become kind=system_instruction items, in order. Each entry
  is ``{"type": ..., "text": ...}`` (or a plain string for tolerance);
  content is the text; item ``ref`` carries the part type where known.
- Messages become one item per message part: text parts carry their text
  with kind by role (conversation_user / conversation_assistant);
  tool-call parts (pending/authored calls) become kind=tool_call;
  completed tool parts become kind=tool_result (output text only — input
  args are NOT copied into derived items; the raw capture retains full
  fidelity); reasoning parts become kind=reasoning_part; unknown shapes
  become kind=other_message_part with their JSON as content, so nothing
  is silently dropped. Item ``ref`` carries call/message/part ids.
- Tool definitions (``tools`` map of name -> {description, input}) become
  one kind=tool_definition item each, sorted by tool name for
  determinism; content is canonical JSON of the definition; item ``ref``
  is the tool name. Executable functions are never recorded — only the
  model-visible description plus JSON schema.
- ModelInvocation links the bundle; provider/model come from the record;
  everything usage-related stays None (unavailable). ``options`` are
  observed request overrides only, never the complete effective provider
  configuration; they are therefore NOT copied into invocation telemetry.
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


def _system_text(entry: Any) -> tuple[str, str | None]:
    if isinstance(entry, str):
        return entry, None
    if isinstance(entry, dict):
        text = entry.get("text")
        part_type = entry.get("type")
        ref = part_type if isinstance(part_type, str) else None
        if isinstance(text, str):
            return text, ref
        return json.dumps(entry, sort_keys=True), ref
    return json.dumps(entry, sort_keys=True), None


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
    if part_type in ("tool_call", "tool-call", "function_call"):
        return "tool_call"
    if part_type in ("tool_result", "tool-result", "function_result"):
        return "tool_result"
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
        # Tolerate direct tool-call shapes without nested state.
        name = part.get("tool") or part.get("name")
        call = part.get("callID") or part.get("call_id") or part.get("id")
        args = part.get("input") or part.get("args")
        head = f"[tool:{name} call:{call}]"
        if isinstance(args, str) and args:
            return f"{head}\n{args}"
        if kind == "tool_result":
            output = part.get("output")
            if isinstance(output, str):
                return f"{head}\n{output}" if output else head
    if kind == "reasoning_part":
        text = part.get("text")
        if isinstance(text, str):
            return text
    return json.dumps(part, sort_keys=True)


def _part_ref(part: dict[str, Any]) -> str | None:
    for key in ("callID", "call_id", "id"):
        value = part.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _message_role(message: Any) -> str | None:
    if isinstance(message, dict):
        info = message.get("info")
        if isinstance(info, dict) and isinstance(info.get("role"), str):
            return info["role"]
        if isinstance(message.get("role"), str):
            return message["role"]
    return None


def _message_parts(message: dict[str, Any]) -> list[Any]:
    parts = message.get("parts")
    if isinstance(parts, list):
        return parts
    # Tolerate flat message shapes: {"role": ..., "content": "..."}.
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return content
    return []


def record_to_items(record: dict[str, Any], observed_at: str) -> list[ContextItem]:
    """Map one validated V2 bridge record to ordered ContextItems.

    Order: system entries, then message parts in order, then tool
    definitions sorted by tool name (deterministic). Unknown shapes are
    preserved opaquely, never dropped.
    """
    system = record.get("system", [])
    messages = record.get("messages", [])
    tools = record.get("tools", {})
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

    entries = system if isinstance(system, list) else [system]
    for entry in entries:
        text, ref = _system_text(entry)
        add("opencode-system", "system_instruction", text, ref)

    message_list = messages if isinstance(messages, list) else []
    for message in message_list:
        if not isinstance(message, dict):
            add("opencode-messages", "other_message_part", message, None)
            continue
        role = _message_role(message)
        parts = _message_parts(message)
        if not parts:
            add("opencode-messages", "other_message_part", message, None)
            continue
        for part in parts:
            if not isinstance(part, dict):
                add("opencode-messages", "other_message_part", part, None)
                continue
            kind = _part_kind(role, part)
            add("opencode-messages", kind, _part_content(part, kind), _part_ref(part))

    if isinstance(tools, dict):
        for name in sorted(tools):
            definition = tools[name]
            if isinstance(definition, dict):
                content = json.dumps(
                    {"tool": name, **{k: definition[k] for k in sorted(definition)}},
                    sort_keys=True,
                )
            else:
                content = json.dumps({"tool": name, "definition": definition}, sort_keys=True)
            ref = name if isinstance(name, str) else None
            add("opencode-tools", "tool_definition", content, ref)
    return items


class SequenceTracker:
    """Per-scope monotonic counters (ingestion-local fallback).

    V2 records carry their own adapter-assigned ``invocation_sequence``;
    the tracker only orders observations when a record omits it (e.g.
    hand-built fixtures). It never reorders model dispatches.
    """

    def __init__(self) -> None:
        self._next: dict[str, int] = defaultdict(int)

    def assign(self, scope: str) -> int:
        self._next[scope] += 1
        return self._next[scope]


def _model_ids(record: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    model = record.get("model")
    if not isinstance(model, dict):
        return None, None, None
    provider = model.get("provider_id", model.get("providerID"))
    ident = model.get("id", model.get("modelID"))
    variant = model.get("variant")
    return (
        provider if isinstance(provider, str) else None,
        ident if isinstance(ident, str) else None,
        variant if isinstance(variant, str) else None,
    )


def ingest_record(
    record: dict[str, Any], tracker: SequenceTracker | None = None
) -> tuple[ContextBundle, ModelInvocation]:
    """One validated V2 bridge record becomes one bundle plus one linked
    invocation. ``invocation_sequence`` comes from the record when
    present; otherwise a tracker (or a fresh one) assigns per-scope order.
    """
    capture_id = str(record.get("capture_id", "unknown"))
    captured_at = str(record.get("captured_at", ""))
    session = record.get("session_id")
    session_ref = session if isinstance(session, str) else None
    scope = session_ref or "unlinked"
    raw_sequence = record.get("invocation_sequence")
    if isinstance(raw_sequence, int):
        index = raw_sequence
    elif tracker is not None:
        index = tracker.assign(scope)
    else:
        index = SequenceTracker().assign(scope)
    provider_id, model_id, _variant = _model_ids(record)
    request_kind = record.get("request_kind")
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
        plugin_api_version=record.get("plugin_api_version")
        if isinstance(record.get("plugin_api_version"), str)
        else None,
        request_kind=request_kind if isinstance(request_kind, str) else None,
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
