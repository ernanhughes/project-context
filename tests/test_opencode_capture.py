"""Stage 1 OpenCode capture tests: ingestion, boundaries, prevalence gates."""

import json
from pathlib import Path

from project_context.opencode.bridge import (
    load_capture_file,
    validate_record,
)
from project_context.opencode.ingest import SequenceTracker, ingest_record
from project_context.opencode.prevalence import (
    assert_exportable,
    export_report,
    repetition_report,
    structural_shared_prefix,
)

GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "opencode-capture-v1"
    / "primary-one-request.json"
)


def _golden_records():
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert doc["evidence_class"] == "synthetic"
    return doc["records"]


def test_golden_records_validate():
    for record in _golden_records():
        assert validate_record(record) == []


def test_unknown_schema_rejected():
    assert validate_record({"schema": "project_context.opencode_capture.v9"}) == [
        "unsupported schema: 'project_context.opencode_capture.v9'"
    ]


def test_one_event_one_bundle_one_invocation():
    tracker = SequenceTracker()
    records = _golden_records()
    assert len(records) == 4
    for record in records:
        bundle, invocation = ingest_record(record, tracker)
        assert bundle.id == f"opencode-{record['capture_id']}"
        assert invocation.bundle_id == bundle.id
        assert invocation.id == f"inv-{record['capture_id']}"
        assert bundle.evidence_class == "opencode_capture"
        assert bundle.provenance is not None
        assert bundle.provenance.capture_id == record["capture_id"]
        assert bundle.provenance.capture_stage == "opencode.v1.pre_dispatch_partial"


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


def test_unknown_part_survives_ingestion():
    tracker = SequenceTracker()
    records = {r["capture_id"]: r for r in _golden_records()}
    bundle, _ = ingest_record(records["cap-gold-002"], tracker)
    kinds = [item.kind for item in bundle.items]
    assert "conversation_user" in kinds
    assert "tool_result" in kinds
    assert "other_message_part" in kinds
    opaque = [item for item in bundle.items if item.kind == "other_message_part"][0]
    assert "weird-future-part" in opaque.content
    assert [item.position for item in bundle.items] == [0, 1, 2]
    assert opaque.ref == "part-3"


def test_tool_result_call_linkage():
    tracker = SequenceTracker()
    records = {r["capture_id"]: r for r in _golden_records()}
    bundle, _ = ingest_record(records["cap-gold-004"], tracker)
    assert len(bundle.items) == 1
    item = bundle.items[0]
    assert item.kind == "tool_result"
    assert item.ref == "call-9"
    assert "3 passed" in item.content


def test_structural_shared_prefix_same_scope():
    tracker = SequenceTracker()
    records = {r["capture_id"]: r for r in _golden_records()}
    first, _ = ingest_record(records["cap-gold-001"], tracker)
    third, _ = ingest_record(records["cap-gold-003"], tracker)
    result = structural_shared_prefix(first, third)
    assert result["comparable"] is True
    assert result["shared_item_count"] == 0
    assert result["first_divergence_index"] == 0


def test_structural_shared_prefix_refuses_cross_scope():
    tracker = SequenceTracker()
    records = {r["capture_id"]: r for r in _golden_records()}
    first, _ = ingest_record(records["cap-gold-001"], tracker)
    second, _ = ingest_record(records["cap-gold-002"], tracker)
    result = structural_shared_prefix(first, second)
    assert result["comparable"] is False
    assert "reason" in result


def test_structural_shared_prefix_counts_overlap():
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
            created_at="2026-09-23T00:00:00Z",
            evidence_class="opencode_capture",
            provenance=CaptureProvenance(source_type="opencode_capture", session_ref=session),
        )

    earlier = bundle_with(["alpha", "beta", "gamma"], "ses-x")
    later = bundle_with(["alpha", "beta", "CHANGED"], "ses-x")
    result = structural_shared_prefix(earlier, later)
    assert result["comparable"] is True
    assert result["shared_item_count"] == 2
    assert result["first_divergence_index"] == 2
    assert result["shared_bytes"] == len("alphabetagamma".encode("utf-8")) - len(
        "gamma".encode("utf-8")
    )


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
        "Fix the test.",
        "file contents here",
        "weird-future-part",
        "call-9",
        "Please review",
    ]:
        assert forbidden not in blob, forbidden
    # Local analysis keys growth by session id (private spool only).
    assert "growth_by_session" in analysis
    exported = export_report(analysis)
    exported_blob = json.dumps(exported)
    assert "ses-gold-1" not in exported_blob
    assert "Fix the test." not in exported_blob
    assert assert_exportable(exported) == []


def test_export_rejects_identifiers_and_hashes():
    bad = {
        "bundles": 2,
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


def test_provider_fields_absent_from_v1_records():
    for record in _golden_records():
        assert "usage" not in record
        assert "cache_hit" not in json.dumps(record)
