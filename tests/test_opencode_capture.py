"""Stage 5 OpenCode V2 capture tests: bridge, ingestion, boundaries.

Active contract only: ``project_context.opencode_capture.v2`` at
``opencode.v2.model_context`` (OpenCode 2.0.16, V2 plugin API,
``@opencode/plugin`` 2.0.16, adapter 0.3.0). V1 records are retired and
must be rejected, never coerced.
"""

import json
from pathlib import Path

from project_context.opencode.bridge import (
    BRIDGE_SCHEMA_V2,
    CAPTURE_STAGE_V2,
    integrity_of,
    load_capture_file,
    validate_record,
)
from project_context.opencode.ingest import SequenceTracker, ingest_record
from project_context.opencode.prevalence import (
    assert_exportable,
    composition_report,
    export_report,
    repetition_report,
    structural_shared_prefix,
    tool_definition_stats,
)

GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "opencode-capture-v2"
    / "session-three-requests.json"
)

OPENCODE_VERSION = "2.0.16"
PLUGIN_API_VERSION = "@opencode/plugin 2.0.16"
ADAPTER_VERSION = "0.3.0"


def _golden_doc():
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert doc["evidence_class"] == "synthetic"
    return doc


def _golden_records():
    return _golden_doc()["records"]


def test_pinned_versions():
    for record in _golden_records():
        assert record["schema"] == BRIDGE_SCHEMA_V2
        assert record["capture_stage"] == CAPTURE_STAGE_V2
        assert record["opencode_version"] == OPENCODE_VERSION
        assert record["plugin_api_version"] == PLUGIN_API_VERSION
        assert record["adapter_version"] == ADAPTER_VERSION


def test_golden_records_validate():
    for record in _golden_records():
        assert validate_record(record) == []


def test_integrity_digest_matches_canonical_blocks():
    for record in _golden_records():
        assert record["integrity"]["sha256"] == integrity_of(record)


def test_integrity_hashes_raw_utf8_not_ascii_escapes():
    import hashlib

    from project_context.opencode.bridge import canonicalize

    record = {
        "system": [{"type": "text", "text": "em—dash and ✓ mark"}],
        "messages": [],
        "tools": {},
        "options": {"temperature": 0.2},
    }
    observed = {
        "system": record["system"],
        "messages": record["messages"],
        "tools": record["tools"],
        "options": record["options"],
    }
    raw = hashlib.sha256(
        json.dumps(
            canonicalize(observed),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    escaped = hashlib.sha256(
        json.dumps(canonicalize(observed), sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    assert raw != escaped  # the cases actually differ
    assert integrity_of(record) == raw
    assert integrity_of(record) != escaped


def test_unknown_schema_rejected():
    assert validate_record({"schema": "project_context.opencode_capture.v9"}) == [
        "unsupported schema: 'project_context.opencode_capture.v9'"
    ]


def test_v1_records_retired_not_coerced():
    v1 = {
        "schema": "project_context.opencode_capture.v1",
        "capture_id": "cap-old",
        "captured_at": "2026-09-23T00:00:01Z",
        "capture_stage": "opencode.v1.pre_dispatch_partial",
        "hook_kind": "system.transform",
        "sequence_scope": "ses-old",
        "payload": {"system": ["x"]},
        "integrity": {"sha256": "0" * 64},
    }
    errors = validate_record(v1)
    assert errors == ["unsupported schema: V1 capture retired; re-capture under V2"]


def test_missing_fields_rejected():
    errors = validate_record({"schema": BRIDGE_SCHEMA_V2})
    for key in (
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
    ):
        assert f"missing key: {key}" in errors


def test_unknown_request_kind_rejected():
    record = dict(_golden_records()[0])
    record["request_kind"] = "teleport"
    assert validate_record(record) == ["unknown request_kind: 'teleport'"]


def test_one_context_record_one_bundle_one_invocation():
    tracker = SequenceTracker()
    records = _golden_records()
    assert len(records) == 3
    for record in records:
        bundle, invocation = ingest_record(record, tracker)
        assert bundle.id == f"opencode-{record['capture_id']}"
        assert invocation.bundle_id == bundle.id
        assert invocation.id == f"inv-{record['capture_id']}"
        assert bundle.evidence_class == "opencode_capture"
        assert bundle.provenance is not None
        assert bundle.provenance.capture_id == record["capture_id"]
        assert bundle.provenance.capture_stage == "opencode.v2.model_context"
        assert bundle.provenance.request_kind == "context"
        assert bundle.provenance.sequence_index == record["invocation_sequence"]
        assert bundle.provenance.opencode_version == OPENCODE_VERSION
        assert bundle.provenance.plugin_api_version == PLUGIN_API_VERSION


def test_unavailable_usage_metrics_are_none():
    tracker = SequenceTracker()
    for record in _golden_records():
        _bundle, invocation = ingest_record(record, tracker)
        assert invocation.input_tokens.value is None
        assert invocation.output_tokens.value is None
        assert invocation.reasoning_tokens is None
        assert invocation.cached_read_tokens is None
        assert invocation.cached_write_tokens is None
        assert invocation.latency_ms is None
        assert invocation.cost_usd is None
        assert invocation.observation_only is True


def test_system_messages_tools_options_captured_together():
    tracker = SequenceTracker()
    bundle, _ = ingest_record(_golden_records()[1], tracker)
    kinds = [item.kind for item in bundle.items]
    assert kinds[:2] == ["system_instruction", "system_instruction"]
    assert "conversation_user" in kinds
    assert "conversation_assistant" in kinds
    assert "tool_result" in kinds
    assert "tool_definition" in kinds
    # Deterministic tool-definition order: sorted by tool name.
    tool_refs = [item.ref for item in bundle.items if item.kind == "tool_definition"]
    assert tool_refs == sorted(tool_refs) == ["bash", "read"]


def test_tool_definitions_carry_no_executables():
    tracker = SequenceTracker()
    for record in _golden_records():
        bundle, _ = ingest_record(record, tracker)
        for item in bundle.items:
            if item.kind == "tool_definition":
                assert "execute" not in item.content
                assert "description" in item.content


def test_tool_result_call_linkage():
    tracker = SequenceTracker()
    bundle, _ = ingest_record(_golden_records()[1], tracker)
    results = [item for item in bundle.items if item.kind == "tool_result"]
    assert {item.ref for item in results} == {"call-1", "call-2"}
    assert any("STATIC-REPEATED-OUTPUT" in item.content for item in results)


def test_model_agent_captured_options_not_telemetry():
    tracker = SequenceTracker()
    _bundle, invocation = ingest_record(_golden_records()[1], tracker)
    assert invocation.provider == "test-provider"
    assert invocation.model == "test-model"
    # Request overrides stay overrides: nothing about them may become
    # effective provider configuration or usage telemetry.
    assert invocation.input_tokens.value is None
    assert invocation.cost_schedule_id is None


def test_exact_order_preserved():
    tracker = SequenceTracker()
    bundle, _ = ingest_record(_golden_records()[2], tracker)
    assert [item.position for item in bundle.items] == list(range(len(bundle.items)))


def test_tool_definition_stats_observed():
    tracker = SequenceTracker()
    bundles = [ingest_record(r, tracker)[0] for r in _golden_records()]
    stats = tool_definition_stats(bundles)
    assert stats["items"] == 6
    assert stats["bytes"] > 0
    assert stats["distinct_definitions"] == 3
    report = composition_report(bundles)
    assert report["tool_definitions"] == "observed"


def test_structural_shared_prefix_stable_then_churn():
    tracker = SequenceTracker()
    bundles = [ingest_record(r, tracker)[0] for r in _golden_records()]
    first = structural_shared_prefix(bundles[0], bundles[1])
    assert first["comparable"] is True
    assert first["shared_item_count"] == 3
    assert first["first_divergence_index"] == 3
    second = structural_shared_prefix(bundles[1], bundles[2])
    assert second["comparable"] is True
    assert second["shared_item_count"] == 2
    assert second["first_divergence_index"] == 2


def test_structural_shared_prefix_refuses_cross_scope():
    from project_context.domain.bundles import build_bundle
    from project_context.domain.items import make_item
    from project_context.domain.provenance import CaptureProvenance

    def bundle_with(texts, session):
        items = [
            make_item(id=f"i-{n}", source="s", kind="k", content=text)
            for n, text in enumerate(texts)
        ]
        return build_bundle(
            items,
            bundle_id=f"b-{session}-{len(texts)}",
            created_at="2026-09-24T00:00:00Z",
            evidence_class="opencode_capture",
            provenance=CaptureProvenance(source_type="opencode_capture", session_ref=session),
        )

    earlier = bundle_with(["alpha", "beta", "gamma"], "ses-x")
    later = bundle_with(["alpha", "beta", "CHANGED"], "ses-x")
    result = structural_shared_prefix(earlier, later)
    assert result["comparable"] is True
    assert result["shared_item_count"] == 2
    assert result["first_divergence_index"] == 2
    other = bundle_with(["alpha"], "ses-y")
    refused = structural_shared_prefix(earlier, other)
    assert refused["comparable"] is False


def test_repetition_detector_counts_duplicates():
    from project_context.domain.bundles import build_bundle
    from project_context.domain.items import make_item

    items = [
        make_item(id="a", source="s", kind="k", content="same text"),
        make_item(id="b", source="s", kind="k", content="different"),
        make_item(id="c", source="s", kind="k", content="same text"),
    ]
    bundle = build_bundle(items, bundle_id="b", created_at="t")
    report = repetition_report([bundle])
    assert report["within_bundle_duplicate_items"] == 1
    assert report["within_bundle_duplicate_bytes"] == len("same text".encode("utf-8"))
    assert report["distinct_contents"] == 2
    assert report["recurring_contents"] == 1


def test_prevalence_output_contains_no_raw_content():
    tracker = SequenceTracker()
    bundles = [ingest_record(r, tracker)[0] for r in _golden_records()]
    from project_context.opencode.prevalence import analyse_bundles

    analysis = analyse_bundles(bundles)
    blob = json.dumps(analysis)
    for forbidden in [
        "Fix the login bug",
        "STATIC-REPEATED-OUTPUT",
        "call-1",
        "Follow project rules",
    ]:
        assert forbidden not in blob, forbidden
    assert "growth_by_session" in analysis
    exported = export_report(analysis)
    exported_blob = json.dumps(exported)
    assert "ses-v2-gold-1" not in exported_blob
    assert "Fix the login bug" not in exported_blob
    assert assert_exportable(exported) == []


def test_export_rejects_identifiers_and_hashes():
    bad = {
        "bundles": 3,
        "sessions_observed": 1,
        "growth_by_session": {"ses-secret-1": {"sizes": [10]}},
        "content_sample": "hello",
        "digest": "abc",
        "fingerprint_index": {"x": 1},
    }
    errors = assert_exportable(bad)
    assert errors, "export gate must refuse identifier/content/hash fields"


def test_malformed_final_jsonl_line_skipped(tmp_path):
    path = tmp_path / "captures.jsonl"
    good = json.dumps(_golden_records()[0])
    path.write_text(good + "\n" + '{"schema": "project_context.opencode_cap', encoding="utf-8")
    records, skipped = load_capture_file(path)
    assert len(records) == 1
    assert skipped == 1


def test_spool_loading_never_modifies_raw(tmp_path):
    path = tmp_path / "captures.jsonl"
    body = "".join(json.dumps(r, sort_keys=True) + "\n" for r in _golden_records())
    path.write_text(body, encoding="utf-8")
    before = path.read_bytes()
    records, skipped = load_capture_file(path)
    assert skipped == 0
    assert len(records) == 3
    assert path.read_bytes() == before


def test_provider_fields_absent_from_records():
    for record in _golden_records():
        assert "usage" not in record
        assert "cache_hit" not in json.dumps(record)
