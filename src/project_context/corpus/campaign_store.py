"""Corpus campaign store: progress tracking without private content.

Committed campaign files carry identity, versions, counts, and statuses
only. The mapping from opaque local session ids back to original session
references lives in .local/corpus/index.json (git-ignored) and never
enters the committed file.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_context.corpus.campaign import (
    CampaignManifest,
    Exclusion,
    SessionRecord,
)
from project_context.opencode.bridge import load_capture_file, validate_record
from project_context.opencode.ingest import SequenceTracker, ingest_record

LOCAL_INDEX = Path(".local") / "corpus" / "index.json"


def campaign_path(root: Path, campaign_id: str) -> Path:
    return root / "corpus" / "campaigns" / f"{campaign_id}.json"


def load_campaign(path: Path) -> CampaignManifest:
    return CampaignManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_campaign(path: Path, campaign: CampaignManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(campaign.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_local_index(root: Path) -> dict[str, Any]:
    path = root / LOCAL_INDEX
    if not path.is_file():
        return {"mappings": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_local_index(root: Path, index: dict[str, Any]) -> None:
    path = root / LOCAL_INDEX
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass
class AddResult:
    campaign: CampaignManifest
    sessions_added: int
    sessions_seen: int
    skipped_lines: int
    invalid_records: int


def _local_id_for(
    index: dict[str, Any], campaign_id: str, session_ref: str
) -> tuple[str, dict[str, Any]]:
    mappings = index.setdefault("mappings", {})
    campaign_map = mappings.setdefault(campaign_id, {})
    if session_ref in campaign_map:
        return campaign_map[session_ref], index
    local_id = f"ls-{uuid.uuid4().hex[:12]}"
    campaign_map[session_ref] = local_id
    return local_id, index


def add_spool(
    campaign: CampaignManifest,
    spool_dir: Path,
    source_label: str,
    root: Path,
) -> tuple[CampaignManifest, AddResult, dict[str, Any]]:
    """Ingest one local spool directory into a campaign. Returns the
    updated campaign, an AddResult, and the updated local index (caller
    persists both). Synthetic evidence classes are refused, never counted.
    Raw files are only read, never modified."""
    if not spool_dir.is_dir():
        raise ValueError(f"spool directory not found: {spool_dir}")
    index = load_local_index(root)
    tracker = SequenceTracker()
    updated = campaign
    sessions_seen: set[str] = set()
    skipped_total = 0
    invalid_total = 0
    per_session: dict[str, dict[str, Any]] = {}
    file_skips: dict[str, int] = {}
    session_invalid: dict[str, int] = {}

    for path in sorted(spool_dir.rglob("*.jsonl")):
        records, skipped = load_capture_file(path)
        skipped_total += skipped
        file_key = str(path)
        file_skips[file_key] = skipped
        for record in records:
            if not isinstance(record, dict):
                invalid_total += 1
                updated = updated.with_exclusion(
                    Exclusion(
                        scope=str(path.name),
                        reason="corrupt-jsonl",
                        detail="non-object line",
                    )
                )
                continue
            if record.get("evidence_class", "opencode_capture") != "opencode_capture":
                invalid_total += 1
                updated = updated.with_exclusion(
                    Exclusion(
                        scope=str(record.get("capture_id", path.name)),
                        reason="synthetic-evidence",
                        detail="non-genuine evidence class refused from campaign",
                    )
                )
                continue
            errors = validate_record(record)
            if errors:
                invalid_total += 1
                suspect = record.get("session_id")
                if isinstance(suspect, str):
                    session_invalid[suspect] = session_invalid.get(suspect, 0) + 1
                updated = updated.with_exclusion(
                    Exclusion(
                        scope=str(record.get("capture_id", path.name)),
                        reason="invalid-schema",
                        detail=errors[0][:160],
                    )
                )
                continue
            bundle, _invocation = ingest_record(record, tracker)
            session = bundle.provenance.session_ref if bundle.provenance else None
            key = session if session else f"unlinked:{bundle.id}"
            sessions_seen.add(key)
            entry = per_session.setdefault(
                key,
                {
                    "records": [],
                    "bundles": [],
                    "first": None,
                    "last": None,
                    "skipped": 0,
                    "adapter": set(),
                    "opencode": set(),
                    "schemas": set(),
                    "stages": set(),
                },
            )
            entry["records"].append(record)
            entry["bundles"].append(bundle)
            entry.setdefault("files", set()).add(file_key)
            kind = record.get("request_kind")
            if isinstance(kind, str):
                entry.setdefault("hooks", set()).add(kind)
            if bundle.provenance is not None:
                if bundle.provenance.adapter_version:
                    entry["adapter"].add(bundle.provenance.adapter_version)
                if bundle.provenance.opencode_version:
                    entry["opencode"].add(bundle.provenance.opencode_version)
                entry["schemas"].add(bundle.provenance.capture_schema or "?")
                entry["stages"].add(bundle.provenance.capture_stage or "?")
            captured = record.get("captured_at")
            if isinstance(captured, str):
                if entry["first"] is None or captured < entry["first"]:
                    entry["first"] = captured
                if entry["last"] is None or captured > entry["last"]:
                    entry["last"] = captured

    sessions_added = 0
    for key in sorted(sessions_seen):
        if key.startswith("unlinked:"):
            updated = updated.with_exclusion(
                Exclusion(
                    scope=key,
                    reason="missing-provenance",
                    detail="no session scope; not countable as a campaign session",
                )
            )
            continue
        local_id, index = _local_id_for(index, campaign.campaign_id, key)
        entry = per_session[key]
        tool_results = sum(
            1 for bundle in entry["bundles"] for item in bundle.items if item.kind == "tool_result"
        )
        local_files = sorted(entry.get("files", set()))
        dirty_files = [f for f in local_files if file_skips.get(f, 0) > 0]
        bad_records = session_invalid.get(key, 0)
        complete = not dirty_files and bad_records == 0
        kinds = set(entry.get("hooks", set()))
        notes = []
        if dirty_files:
            notes.append(f"skipped lines in contributing files: {len(dirty_files)} file(s)")
        if bad_records:
            notes.append(f"invalid records attributed to session: {bad_records}")
        notes.append(
            "compaction requests are captured as kind=compaction, "
            "filtered from primary timelines by default"
        )
        record_obj = SessionRecord(
            local_session_id=local_id,
            campaign_id=campaign.campaign_id,
            source_label=source_label,
            capture_schema=campaign.capture_schema,
            capture_stage=campaign.capture_stage,
            opencode_version=sorted(entry["opencode"])[0] if entry["opencode"] else None,
            adapter_version=sorted(entry["adapter"])[0] if entry["adapter"] else None,
            started_at=entry["first"],
            ended_at=entry["last"],
            invocation_count=len(entry["bundles"]),
            captured_record_count=len(entry["records"]),
            tool_result_count=tool_results,
            complete_capture=complete,
            completeness_notes=tuple(notes),
            compaction_observed="compaction" in kinds,
            parse_warnings=sum(file_skips.get(f, 0) for f in local_files),
            hook_kinds=tuple(sorted(kinds)),
            privacy_status="raw-local",
            publication_status="not-approved",
        )
        before = updated.genuine_session_count()
        updated = updated.with_session(record_obj)
        if updated.genuine_session_count() > before:
            sessions_added += 1

    result = AddResult(
        campaign=updated,
        sessions_added=sessions_added,
        sessions_seen=len([k for k in sessions_seen if not k.startswith("unlinked:")]),
        skipped_lines=skipped_total,
        invalid_records=invalid_total,
    )
    return updated, result, index
