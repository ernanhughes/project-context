"""Reconciliation: intended injection versus observed invocation.

Compares the injection receipt plus the rendered reference against the
record the existing observer captured. Every check is structural and
byte-exact where it matters:

- record_valid: the observed record passes bridge validation;
- markers_present: a runtime block marker survived to observation;
- block_exact: an occurrence equals the intended text byte for byte;
- block_once: exactly one exact occurrence (duplication count kept);
- order_preserved: the exact block is the last system block (the
  append location) and internal section order matches the reference;
- integrity_match: observer-side integrity equals the receipt's
  post_digest — byte-equality of the whole request, catching any
  added, dropped, or altered material anywhere.

Non-injected receipts reconcile differently: noop_empty requires the
markers ABSENT and integrity equal to pre (nothing added, nothing
changed); noop_idempotent requires the block present once with
integrity equal to post; failed receipts are not_applicable (the
failure receipt itself is the record).
"""

from __future__ import annotations

from typing import Any

from project_context.opencode.bridge import integrity_of, validate_record
from project_context.runtime.model import (
    BLOCK_OPEN,
    InjectionReceipt,
    ReconciliationResult,
    RenderedBlock,
)


def _system_texts(observed: dict[str, Any]) -> list[str]:
    system = observed.get("system")
    if not isinstance(system, list):
        return []
    return [
        block["text"]
        for block in system
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]


def _section_bodies(text: str) -> list[str]:
    """Item body sequence inside a rendered block, in order. Headers
    (marker lines and [KIND] lines) are skipped; bodies determine order."""
    lines = text.split("\n")
    inner = lines[1:-1] if len(lines) >= 2 else []
    chunks = [chunk for chunk in "\n".join(inner).split("\n\n") if chunk.strip()]
    bodies = []
    for chunk in chunks:
        parts = chunk.split("\n", 1)
        bodies.append(parts[1] if len(parts) == 2 else parts[0])
    return bodies


def reconcile(
    receipt: InjectionReceipt, rendered: RenderedBlock, observed: dict[str, Any]
) -> ReconciliationResult:
    """Reconcile one injection against one observed record. Pure."""
    texts = _system_texts(observed)
    markers = sum(1 for text in texts if BLOCK_OPEN in text)
    occurrences = sum(1 for text in texts if text == rendered.text)
    record_ok = not validate_record(observed)
    integrity_ok = bool(texts) and integrity_of(observed) == (
        receipt.post_digest if receipt.status != "noop_empty" else receipt.pre_digest
    )

    if receipt.status == "failed":
        return ReconciliationResult(
            runtime_request_id=receipt.runtime_request_id,
            status="not_applicable",
            checks={"reason": "no injection was attempted"},
            duplication_count=occurrences,
            detail="failure receipt stands alone; nothing to reconcile",
        )
    if receipt.status == "noop_empty":
        passed = record_ok and markers == 0 and integrity_ok
        return ReconciliationResult(
            runtime_request_id=receipt.runtime_request_id,
            status="pass" if passed else "fail",
            checks={
                "record_valid": record_ok,
                "markers_absent": markers == 0,
                "integrity_match": integrity_ok,
            },
            duplication_count=occurrences,
            detail="empty render must leave the request untouched",
        )
    last_is_block = bool(texts) and texts[-1] == rendered.text
    order_ok = last_is_block and _section_bodies(texts[-1]) == _section_bodies(rendered.text)
    checks = {
        "record_valid": record_ok,
        "markers_present": markers >= 1,
        "block_exact": occurrences >= 1,
        "block_once": occurrences == 1,
        "order_preserved": order_ok,
        "integrity_match": integrity_ok,
    }
    passed = all(checks.values())
    return ReconciliationResult(
        runtime_request_id=receipt.runtime_request_id,
        status="pass" if passed else "fail",
        checks=checks,
        duplication_count=max(0, occurrences - 1),
        detail="intended block reconciled against observed invocation"
        if passed
        else "observed invocation diverges from intended injection",
    )
