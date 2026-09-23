"""Corpus manifests: describe traces without exposing content."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "project_context.corpus_manifest.v1"

SANITISATION_RAW_LOCAL = "raw-local"
SANITISATION_SANITISED = "sanitised"
SANITISATION_APPROVED_PUBLIC = "approved-public"

SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{8,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]+"),
)


class UnsanitisedCorpusError(ValueError):
    """Raised when raw or unapproved material is offered for publication."""


@dataclass(frozen=True)
class CorpusManifest:
    corpus_id: str
    trace_id: str
    source_type: str
    captured_at: str
    turn_count: int
    tool_call_count: int
    rendered_token_min: int
    rendered_token_max: int
    sanitisation_status: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "corpus_id": self.corpus_id,
            "trace_id": self.trace_id,
            "source_type": self.source_type,
            "captured_at": self.captured_at,
            "turn_count": self.turn_count,
            "tool_call_count": self.tool_call_count,
            "rendered_token_min": self.rendered_token_min,
            "rendered_token_max": self.rendered_token_max,
            "sanitisation_status": self.sanitisation_status,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CorpusManifest":
        version = data.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported CorpusManifest schema: {version!r}")
        return cls(
            corpus_id=data["corpus_id"],
            trace_id=data["trace_id"],
            source_type=data["source_type"],
            captured_at=data["captured_at"],
            turn_count=data["turn_count"],
            tool_call_count=data["tool_call_count"],
            rendered_token_min=data["rendered_token_min"],
            rendered_token_max=data["rendered_token_max"],
            sanitisation_status=data["sanitisation_status"],
            content_hash=data["content_hash"],
        )


def assert_publishable(manifest: CorpusManifest) -> None:
    """Gate for anything committed or exported. Only approved-public
    manifests pass; everything else raises, including merely sanitised
    material awaiting human approval."""
    if manifest.sanitisation_status != SANITISATION_APPROVED_PUBLIC:
        raise UnsanitisedCorpusError(
            f"trace {manifest.trace_id} has status "
            f"{manifest.sanitisation_status!r}; only "
            f"{SANITISATION_APPROVED_PUBLIC!r} material may be published"
        )


def scan_text_for_secrets(text: str) -> list[str]:
    """Modest pattern scan used by artifact validation. Returns the names
    of matched patterns, never the matched secrets themselves."""
    hits: list[str] = []
    for index, pattern in enumerate(SECRET_PATTERNS):
        if pattern.search(text):
            hits.append(f"secret-pattern-{index}")
    return hits
