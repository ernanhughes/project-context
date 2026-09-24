"""Runtime records: render policy, rendered block, receipts, reconciliation.

All records are frozen dataclasses with schema versions and JSON
round-trips. Receipts carry digests, counts, and identities — never raw
model-facing content (privacy: live statements may be private; receipts
are the shareable artifact, rendered blocks are local-only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RENDER_POLICY_SCHEMA = "project_context.runtime_render_policy.v1"
RENDERED_BLOCK_SCHEMA = "project_context.rendered_block.v1"
INJECTION_RECEIPT_SCHEMA = "project_context.injection_receipt.v1"
RECONCILIATION_SCHEMA = "project_context.reconciliation_result.v1"

BLOCK_OPEN = "[CONTEXT RUNTIME]"
BLOCK_CLOSE = "[/CONTEXT RUNTIME]"
INJECTION_LOCATION = "system-append"

RENDER_POLICY_ID = "runtime-render-v1"


class RuntimeError(Exception):
    """Typed runtime failure with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class RenderPolicy:
    """How a selected bundle becomes model-facing text. One canonical
    policy in Stage 6D; placement experiments belong later."""

    policy_id: str = RENDER_POLICY_ID
    policy_version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RENDER_POLICY_SCHEMA,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RenderPolicy":
        version = data.get("schema_version", RENDER_POLICY_SCHEMA)
        if version != RENDER_POLICY_SCHEMA:
            raise ValueError(f"unsupported RenderPolicy schema: {version!r}")
        return cls(
            policy_id=data.get("policy_id", RENDER_POLICY_ID),
            policy_version=data.get("policy_version", "1"),
        )


@dataclass(frozen=True)
class RenderedBlock:
    """Deterministic model-facing text for one selected bundle, plus its
    identity. Empty selections render to empty text with item_count 0;
    the injector refuses those (no mutation for nothing)."""

    bundle_id: str
    policy_id: str
    text: str
    item_count: int
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RENDERED_BLOCK_SCHEMA,
            "bundle_id": self.bundle_id,
            "policy_id": self.policy_id,
            "text": self.text,
            "item_count": self.item_count,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RenderedBlock":
        version = data.get("schema_version", RENDERED_BLOCK_SCHEMA)
        if version != RENDERED_BLOCK_SCHEMA:
            raise ValueError(f"unsupported RenderedBlock schema: {version!r}")
        return cls(
            bundle_id=data["bundle_id"],
            policy_id=data.get("policy_id", RENDER_POLICY_ID),
            text=data["text"],
            item_count=int(data["item_count"]),
            digest=data["digest"],
        )


@dataclass(frozen=True)
class InjectionReceipt:
    """What the runtime intended and what it did. `pre_digest` and
    `post_digest` use the same identity basis as the observer-side
    integrity hash, so reconciliation can prove byte-equality."""

    runtime_request_id: str
    bundle_id: str
    rendered_digest: str
    candidate_ids: tuple[str, ...]
    render_policy_id: str
    injection_location: str
    pre_digest: str
    post_digest: str
    injected_bytes: int
    status: str
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": INJECTION_RECEIPT_SCHEMA,
            "runtime_request_id": self.runtime_request_id,
            "bundle_id": self.bundle_id,
            "rendered_digest": self.rendered_digest,
            "candidate_ids": list(self.candidate_ids),
            "render_policy_id": self.render_policy_id,
            "injection_location": self.injection_location,
            "pre_digest": self.pre_digest,
            "post_digest": self.post_digest,
            "injected_bytes": self.injected_bytes,
            "status": self.status,
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InjectionReceipt":
        version = data.get("schema_version", INJECTION_RECEIPT_SCHEMA)
        if version != INJECTION_RECEIPT_SCHEMA:
            raise ValueError(f"unsupported InjectionReceipt schema: {version!r}")
        return cls(
            runtime_request_id=data["runtime_request_id"],
            bundle_id=data["bundle_id"],
            rendered_digest=data["rendered_digest"],
            candidate_ids=tuple(data.get("candidate_ids", [])),
            render_policy_id=data.get("render_policy_id", RENDER_POLICY_ID),
            injection_location=data.get("injection_location", INJECTION_LOCATION),
            pre_digest=data["pre_digest"],
            post_digest=data["post_digest"],
            injected_bytes=int(data["injected_bytes"]),
            status=data["status"],
            failure_reason=data.get("failure_reason"),
        )


@dataclass(frozen=True)
class ReconciliationResult:
    """Intended injection versus observed invocation. PASS requires every
    check; anything else is FAIL with per-check evidence. Checks skipped
    for non-injected receipts report `not_applicable` as their status."""

    runtime_request_id: str
    status: str
    checks: dict[str, Any]
    duplication_count: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RECONCILIATION_SCHEMA,
            "runtime_request_id": self.runtime_request_id,
            "status": self.status,
            "checks": dict(self.checks),
            "duplication_count": self.duplication_count,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReconciliationResult":
        version = data.get("schema_version", RECONCILIATION_SCHEMA)
        if version != RECONCILIATION_SCHEMA:
            raise ValueError(f"unsupported ReconciliationResult schema: {version!r}")
        return cls(
            runtime_request_id=data["runtime_request_id"],
            status=data["status"],
            checks=dict(data.get("checks", {})),
            duplication_count=int(data.get("duplication_count", 0)),
            detail=data.get("detail", ""),
        )
