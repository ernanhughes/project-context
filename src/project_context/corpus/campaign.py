"""Ecological corpus campaign: what was collected, what counts, why not.

A campaign tracks collection progress without touching private content.
Session records carry counts and statuses only; raw captures stay in the
local spool. Synthetic evidence is refused at the gate, never counted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CAMPAIGN_SCHEMA = "project_context.corpus_campaign.v1"

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"

EXCLUSION_REASONS = frozenset(
    {
        "invalid-schema",
        "corrupt-jsonl",
        "interrupted-capture",
        "unsupported-adapter",
        "missing-provenance",
        "synthetic-evidence",
        "duplicate-import",
    }
)


@dataclass(frozen=True)
class Exclusion:
    """One refused unit of input. Deterministic ordering by (scope, reason,
    detail) keeps the ledger stable across repeated runs."""

    scope: str
    reason: str
    detail: str

    def __post_init__(self) -> None:
        if self.reason not in EXCLUSION_REASONS:
            raise ValueError(f"unknown exclusion reason: {self.reason!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"scope": self.scope, "reason": self.reason, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Exclusion":
        return cls(scope=data["scope"], reason=data["reason"], detail=data["detail"])


@dataclass(frozen=True)
class SessionRecord:
    """Local per-session metadata. Counts and statuses only; no content,
    no paths, no original session identifiers beyond the opaque local id."""

    local_session_id: str
    campaign_id: str
    source_label: str
    capture_schema: str
    capture_stage: str
    opencode_version: str | None
    adapter_version: str | None
    started_at: str | None
    ended_at: str | None
    invocation_count: int
    captured_record_count: int
    tool_result_count: int
    complete_capture: bool
    completeness_notes: tuple[str, ...] = ()
    compaction_observed: bool = False
    parse_warnings: int = 0
    hook_kinds: tuple[str, ...] = ()
    privacy_status: str = "raw-local"
    publication_status: str = "not-approved"

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_session_id": self.local_session_id,
            "campaign_id": self.campaign_id,
            "source_label": self.source_label,
            "capture_schema": self.capture_schema,
            "capture_stage": self.capture_stage,
            "opencode_version": self.opencode_version,
            "adapter_version": self.adapter_version,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "invocation_count": self.invocation_count,
            "captured_record_count": self.captured_record_count,
            "tool_result_count": self.tool_result_count,
            "complete_capture": self.complete_capture,
            "completeness_notes": list(self.completeness_notes),
            "compaction_observed": self.compaction_observed,
            "parse_warnings": self.parse_warnings,
            "hook_kinds": list(self.hook_kinds),
            "privacy_status": self.privacy_status,
            "publication_status": self.publication_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionRecord":
        return cls(
            local_session_id=data["local_session_id"],
            campaign_id=data["campaign_id"],
            source_label=data["source_label"],
            capture_schema=data["capture_schema"],
            capture_stage=data["capture_stage"],
            opencode_version=data.get("opencode_version"),
            adapter_version=data.get("adapter_version"),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            invocation_count=data.get("invocation_count", 0),
            captured_record_count=data.get("captured_record_count", 0),
            tool_result_count=data.get("tool_result_count", 0),
            complete_capture=bool(data.get("complete_capture", False)),
            completeness_notes=tuple(data.get("completeness_notes", [])),
            compaction_observed=bool(data.get("compaction_observed", False)),
            parse_warnings=data.get("parse_warnings", 0),
            hook_kinds=tuple(data.get("hook_kinds", ())),
            privacy_status=data.get("privacy_status", "raw-local"),
            publication_status=data.get("publication_status", "not-approved"),
        )


@dataclass(frozen=True)
class CampaignManifest:
    """The collection campaign itself. Committable: identity, versions,
    counts, and statuses only. Never task text, paths, or session ids."""

    campaign_id: str
    target_sessions: int
    capture_schema: str
    capture_stage: str
    opencode_version: str | None
    adapter_version: str | None
    started_at: str
    status: str = STATUS_OPEN
    sampling_notes: str = ""
    sessions: tuple[SessionRecord, ...] = ()
    exclusions: tuple[Exclusion, ...] = ()

    def genuine_session_count(self) -> int:
        return len(self.sessions)

    def with_session(self, record: SessionRecord) -> "CampaignManifest":
        if any(s.local_session_id == record.local_session_id for s in self.sessions):
            return self
        return CampaignManifest(
            campaign_id=self.campaign_id,
            target_sessions=self.target_sessions,
            capture_schema=self.capture_schema,
            capture_stage=self.capture_stage,
            opencode_version=self.opencode_version,
            adapter_version=self.adapter_version,
            started_at=self.started_at,
            status=self.status,
            sampling_notes=self.sampling_notes,
            sessions=self.sessions + (record,),
            exclusions=self.exclusions,
        )

    def with_exclusion(self, exclusion: Exclusion) -> "CampaignManifest":
        if exclusion in self.exclusions:
            return self
        ordered = tuple(
            sorted(
                self.exclusions + (exclusion,),
                key=lambda e: (e.scope, e.reason, e.detail),
            )
        )
        return CampaignManifest(
            campaign_id=self.campaign_id,
            target_sessions=self.target_sessions,
            capture_schema=self.capture_schema,
            capture_stage=self.capture_stage,
            opencode_version=self.opencode_version,
            adapter_version=self.adapter_version,
            started_at=self.started_at,
            status=self.status,
            sampling_notes=self.sampling_notes,
            sessions=self.sessions,
            exclusions=ordered,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CAMPAIGN_SCHEMA,
            "campaign_id": self.campaign_id,
            "target_sessions": self.target_sessions,
            "capture_schema": self.capture_schema,
            "capture_stage": self.capture_stage,
            "opencode_version": self.opencode_version,
            "adapter_version": self.adapter_version,
            "started_at": self.started_at,
            "status": self.status,
            "sampling_notes": self.sampling_notes,
            "sessions": [s.to_dict() for s in self.sessions],
            "exclusions": [e.to_dict() for e in self.exclusions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignManifest":
        if data.get("schema", CAMPAIGN_SCHEMA) != CAMPAIGN_SCHEMA:
            raise ValueError(f"unsupported campaign schema: {data.get('schema')!r}")
        return cls(
            campaign_id=data["campaign_id"],
            target_sessions=data["target_sessions"],
            capture_schema=data["capture_schema"],
            capture_stage=data["capture_stage"],
            opencode_version=data.get("opencode_version"),
            adapter_version=data.get("adapter_version"),
            started_at=data["started_at"],
            status=data.get("status", STATUS_OPEN),
            sampling_notes=data.get("sampling_notes", ""),
            sessions=tuple(SessionRecord.from_dict(s) for s in data.get("sessions", [])),
            exclusions=tuple(Exclusion.from_dict(e) for e in data.get("exclusions", [])),
        )
