"""Explicit injection into a synthetic OpenCode-shaped request.

The request dict mirrors the V2 bridge record shape (system/messages/
tools/options). Injection appends one marked text block to the END of
the system array: the least invasive stable location, leaving every
existing block untouched and ordered.

Fail-closed contract:

- `mode` must be the literal runtime mode; anything else raises
  `opt_in_required`. A default/fresh setup can never mutate.
- malformed requests raise `unsupported_request_shape` (programmer
  error, never a receipt).
- a differing pre-existing runtime block yields a failure receipt with
  NO mutation (`injection_conflict`).
- an identical pre-existing block yields an idempotent no-op receipt.
- an empty rendered block yields an empty no-op receipt.
- partial writes never occur: the new system array is built first and
  swapped once.
"""

from __future__ import annotations

import copy
from typing import Any

from project_context.opencode.bridge import integrity_of
from project_context.runtime.model import (
    BLOCK_OPEN,
    INJECTION_LOCATION,
    InjectionReceipt,
    RenderedBlock,
    RuntimeError,
)

RUNTIME_MODE = "runtime"
OBSERVER_MODE = "observe"


def _system_texts(request: dict[str, Any]) -> list[str]:
    return [
        block["text"]
        for block in request["system"]
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]


def inject(
    request: dict[str, Any],
    rendered: RenderedBlock,
    *,
    request_id: str,
    mode: str,
    candidate_ids: tuple[str, ...] = (),
) -> tuple[dict[str, Any], InjectionReceipt]:
    """Inject the rendered block, or refuse with an explicit receipt."""
    if mode != RUNTIME_MODE:
        raise RuntimeError(
            "opt_in_required",
            f"injection requires mode={RUNTIME_MODE!r}; got {mode!r}",
        )
    if (
        not isinstance(request, dict)
        or not isinstance(request.get("system"), list)
        or not isinstance(request.get("messages"), list)
        or not isinstance(request.get("tools"), dict)
        or not isinstance(request.get("options"), dict)
    ):
        raise RuntimeError("unsupported_request_shape", "request is not a V2-shaped record")
    pre_digest = integrity_of(request)
    base_receipt = {
        "runtime_request_id": request_id,
        "bundle_id": rendered.bundle_id,
        "rendered_digest": rendered.digest,
        "candidate_ids": tuple(candidate_ids),
        "render_policy_id": rendered.policy_id,
        "injection_location": INJECTION_LOCATION,
        "pre_digest": pre_digest,
    }
    if not rendered.text or rendered.item_count == 0:
        copied = copy.deepcopy(request)
        return copied, InjectionReceipt(
            **base_receipt,
            post_digest=pre_digest,
            injected_bytes=0,
            status="noop_empty",
            failure_reason=None,
        )
    existing = [text for text in _system_texts(request) if BLOCK_OPEN in text]
    if existing:
        if any(text == rendered.text for text in existing):
            copied = copy.deepcopy(request)
            return copied, InjectionReceipt(
                **base_receipt,
                post_digest=pre_digest,
                injected_bytes=0,
                status="noop_idempotent",
                failure_reason=None,
            )
        copied = copy.deepcopy(request)
        return copied, InjectionReceipt(
            **base_receipt,
            post_digest=pre_digest,
            injected_bytes=0,
            status="failed",
            failure_reason="injection_conflict",
        )
    mutated = copy.deepcopy(request)
    mutated["system"] = [*mutated["system"], {"type": "text", "text": rendered.text}]
    post_digest = integrity_of(mutated)
    return mutated, InjectionReceipt(
        **base_receipt,
        post_digest=post_digest,
        injected_bytes=len(rendered.text.encode("utf-8")),
        status="injected",
        failure_reason=None,
    )
