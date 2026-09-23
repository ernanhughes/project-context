"""Bridge-record validation and JSONL loading.

The bridge schema is owned jointly with the TypeScript adapter; the
golden fixture at fixtures/opencode-capture-v1/ is the compatibility
contract. Unknown schemas are rejected loudly, never coerced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BRIDGE_SCHEMA_V1 = "project_context.opencode_capture.v1"
SUPPORTED_SCHEMAS = frozenset({BRIDGE_SCHEMA_V1})

REQUIRED_KEYS = (
    "schema",
    "capture_id",
    "captured_at",
    "capture_stage",
    "hook_kind",
    "sequence_scope",
    "payload",
    "integrity",
)

KNOWN_HOOK_KINDS = frozenset(
    {
        "system.transform",
        "messages.transform",
        "chat.message",
        "tool.execute.after",
    }
)


class UnknownSchemaError(ValueError):
    """Raised when a record declares a schema this reader does not know."""


class MalformedRecordError(ValueError):
    """Raised when a record claims a known schema but breaks its shape."""


def validate_record(record: Any) -> list[str]:
    """Return error strings; empty means valid."""
    if not isinstance(record, dict):
        return ["record is not an object"]
    errors = []
    schema = record.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        return [f"unsupported schema: {schema!r}"]
    for key in REQUIRED_KEYS:
        if key not in record:
            errors.append(f"missing key: {key}")
    if "payload" in record and not isinstance(record["payload"], dict):
        errors.append("payload is not an object")
    hook = record.get("hook_kind")
    if hook is not None and hook not in KNOWN_HOOK_KINDS:
        errors.append(f"unknown hook_kind: {hook!r}")
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
