"""Provenance for live-captured bundles. Stage 0 bundles leave this empty;
Stage 1 OpenCode ingestion attaches it. All fields optional so older
records keep parsing. Presence of provenance never implies provider-wire
fidelity: see capture_stage wording."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CaptureProvenance:
    source_type: str
    capture_schema: str | None = None
    capture_id: str | None = None
    capture_stage: str | None = None
    session_ref: str | None = None
    sequence_index: int | None = None
    adapter_version: str | None = None
    opencode_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "capture_schema": self.capture_schema,
            "capture_id": self.capture_id,
            "capture_stage": self.capture_stage,
            "session_ref": self.session_ref,
            "sequence_index": self.sequence_index,
            "adapter_version": self.adapter_version,
            "opencode_version": self.opencode_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CaptureProvenance | None":
        if data is None:
            return None
        return cls(
            source_type=data.get("source_type", "unknown"),
            capture_schema=data.get("capture_schema"),
            capture_id=data.get("capture_id"),
            capture_stage=data.get("capture_stage"),
            session_ref=data.get("session_ref"),
            sequence_index=data.get("sequence_index"),
            adapter_version=data.get("adapter_version"),
            opencode_version=data.get("opencode_version"),
        )
