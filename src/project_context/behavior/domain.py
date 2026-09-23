"""One minimal behavioural linkage record. Links a frozen bundle (or a
derived interventional bundle) to one parsed model action and its
invocation. All grading lives in EvaluationObservation records; this
record carries identity and linkage only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BEHAVIOR_RECORD_SCHEMA = "project_context.behavior_record.v1"


@dataclass(frozen=True)
class BehaviorRecord:
    id: str
    experiment_case_id: str
    fixture_id: str
    condition_id: str
    repeat_index: int
    source_bundle_id: str
    source_bundle_digest: str
    parent_bundle_id: str | None
    intervention_id: str | None
    removed_ids: tuple[str, ...]
    added_ids: tuple[str, ...]
    invocation_id: str
    parse_status: str
    parsed_action: dict[str, Any] | None
    raw_response_digest: str
    prompt_version: str
    parser_version: str
    grader_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BEHAVIOR_RECORD_SCHEMA,
            "id": self.id,
            "experiment_case_id": self.experiment_case_id,
            "fixture_id": self.fixture_id,
            "condition_id": self.condition_id,
            "repeat_index": self.repeat_index,
            "source_bundle_id": self.source_bundle_id,
            "source_bundle_digest": self.source_bundle_digest,
            "parent_bundle_id": self.parent_bundle_id,
            "intervention_id": self.intervention_id,
            "removed_ids": list(self.removed_ids),
            "added_ids": list(self.added_ids),
            "invocation_id": self.invocation_id,
            "parse_status": self.parse_status,
            "parsed_action": self.parsed_action,
            "raw_response_digest": self.raw_response_digest,
            "prompt_version": self.prompt_version,
            "parser_version": self.parser_version,
            "grader_version": self.grader_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BehaviorRecord":
        version = data.get("schema_version", BEHAVIOR_RECORD_SCHEMA)
        if version != BEHAVIOR_RECORD_SCHEMA:
            raise ValueError(f"unsupported BehaviorRecord schema: {version!r}")
        return cls(
            id=data["id"],
            experiment_case_id=data["experiment_case_id"],
            fixture_id=data["fixture_id"],
            condition_id=data["condition_id"],
            repeat_index=int(data.get("repeat_index", 0)),
            source_bundle_id=data["source_bundle_id"],
            source_bundle_digest=data["source_bundle_digest"],
            parent_bundle_id=data.get("parent_bundle_id"),
            intervention_id=data.get("intervention_id"),
            removed_ids=tuple(data.get("removed_ids", [])),
            added_ids=tuple(data.get("added_ids", [])),
            invocation_id=data["invocation_id"],
            parse_status=data["parse_status"],
            parsed_action=data.get("parsed_action"),
            raw_response_digest=data["raw_response_digest"],
            prompt_version=data["prompt_version"],
            parser_version=data["parser_version"],
            grader_version=data["grader_version"],
        )
