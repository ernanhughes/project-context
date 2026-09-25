"""Bridge-record validation and JSONL loading (V2 only).

Active schema: ``project_context.opencode_capture.v2`` observed at the
OpenCode V2 ``session.hook("context")`` boundary
(``opencode.v2.model_context``): one record per observed model request,
carrying the assembled semantic system/messages/tools/options blocks.

V1 records (``project_context.opencode_capture.v1``,
``opencode.v1.pre_dispatch_partial``) are historical and are REJECTED by
this reader — never coerced. Unknown schemas are rejected loudly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BRIDGE_SCHEMA_V2 = "project_context.opencode_capture.v2"
# Historical only: active readers accept V2 and nothing else.
BRIDGE_SCHEMA_V1_HISTORICAL = "project_context.opencode_capture.v1"
SUPPORTED_SCHEMAS = frozenset({BRIDGE_SCHEMA_V2})

CAPTURE_STAGE_V2 = "opencode.v2.model_context"

REQUIRED_KEYS = (
    "schema",
    "capture_id",
    "captured_at",
    "capture_stage",
    "request_kind",
    "session_id",
    "invocation_sequence",
    "agent",
    "model",
    "system",
    "messages",
    "tools",
    "options",
    "integrity",
)

KNOWN_REQUEST_KINDS = frozenset({"context", "compaction", "generate", "title"})


class UnknownSchemaError(ValueError):
    """Raised when a record declares a schema this reader does not know."""


class MalformedRecordError(ValueError):
    """Raised when a record claims a known schema but breaks its shape."""


def validate_record(record: Any) -> list[str]:
    """Return error strings; empty means valid."""
    if not isinstance(record, dict):
        return ["record is not an object"]
    errors: list[str] = []
    schema = record.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        if schema == BRIDGE_SCHEMA_V1_HISTORICAL:
            return ["unsupported schema: V1 capture retired; re-capture under V2"]
        return [f"unsupported schema: {schema!r}"]
    for key in REQUIRED_KEYS:
        if key not in record:
            errors.append(f"missing key: {key}")
    if "model" in record and not isinstance(record["model"], dict):
        errors.append("model is not an object")
    if "system" in record and not isinstance(record["system"], list):
        errors.append("system is not a list")
    if "messages" in record and not isinstance(record["messages"], list):
        errors.append("messages is not a list")
    if "tools" in record and not isinstance(record["tools"], dict):
        errors.append("tools is not an object")
    if "options" in record and not isinstance(record["options"], dict):
        errors.append("options is not an object")
    kind = record.get("request_kind")
    if kind is not None and kind not in KNOWN_REQUEST_KINDS:
        errors.append(f"unknown request_kind: {kind!r}")
    stage = record.get("capture_stage")
    if stage is not None and stage != CAPTURE_STAGE_V2:
        errors.append(f"unexpected capture_stage: {stage!r}")
    return errors


def load_capture_file(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Load one JSONL capture file. Returns (records, skipped_lines).

    A malformed final (partial-write) line is skipped and counted, never
    silently repaired; the raw file is never modified. Malformed lines
    anywhere else are also skipped-and-counted, each reported by the
    caller. Use validate_record per record afterwards.
    """
    records: list[dict[str, Any]] = []
    skipped = 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    return records, skipped


def load_capture_dir(directory: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Load every *.jsonl under a spool directory tree."""
    records: list[dict[str, Any]] = []
    skipped_total = 0
    files = 0
    for path in sorted(directory.rglob("*.jsonl")):
        file_records, skipped = load_capture_file(path)
        records.extend(file_records)
        skipped_total += skipped
        files += 1
    return records, {"files": files, "skipped_lines": skipped_total}


def canonicalize(value: Any) -> Any:
    """Canonical form for integrity hashing: object keys sorted
    recursively, arrays keep order. Byte-identical with the
    TypeScript adapter's canonicalize for all content, including
    non-ASCII: both sides hash raw UTF-8 bytes (Python
    ensure_ascii=False to match JSON.stringify)."""
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    return value


def integrity_of(record: dict[str, Any]) -> str:
    """Expected sha256 over the observed blocks {system, messages,
    tools, options} with compact separators and raw UTF-8 encoding
    (matching TypeScript JSON.stringify, which never ASCII-escapes).
    Used by tests to pin the golden fixture."""
    import hashlib

    observed = {
        "system": record.get("system"),
        "messages": record.get("messages"),
        "tools": record.get("tools"),
        "options": record.get("options"),
    }
    return hashlib.sha256(
        json.dumps(
            canonicalize(observed),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


# Backwards-compatible alias for callers that name the historical V1 symbol.
BRIDGE_SCHEMA_V1 = BRIDGE_SCHEMA_V1_HISTORICAL
