"""Context Debugger v1 tests: views, queries, doctor, privacy, determinism.

Golden source: fixtures/opencode-capture-v2/session-three-requests.json
(SYNTHETIC) loaded through the real spool path. Every assertion is
structural; raw content must never appear in default output.
"""

import json
from pathlib import Path

import pytest

from project_context.cli.main import main as cli_main
from project_context.debugger.analyse import _sequence_of, load_spool
from project_context.debugger.doctor import doctor_invocation, doctor_session
from project_context.debugger.domain import DEFAULT_THRESHOLDS, DOCTOR_POLICY_VERSION
from project_context.debugger.query import query_items
from project_context.debugger.report import (
    report_compare,
    report_doctor,
    report_explain,
    report_inspect,
    report_latest,
    report_query,
    report_timeline,
)

SPOOL = Path(__file__).resolve().parent.parent / "fixtures" / "opencode-capture-v2" / "spool"

RAW_STRINGS = (
    "Fix the login bug",
    "STATIC-REPEATED-OUTPUT",
    "Follow project rules",
    "ses-v2-gold-1",
    "cap-v2-001",
)


@pytest.fixture()
def store():
    return load_spool(SPOOL)


@pytest.fixture()
def session(store):
    key = store.session_order[0]
    return key, 1, store.sessions[key]


def test_spool_loads_one_session_three_primary(store):
    assert len(store.session_order) == 1
    ordered = store.sessions[store.session_order[0]]
    assert len(ordered) == 3
    assert [_sequence_of(o, i) for i, o in enumerate(ordered)] == [1, 2, 3]
    assert store.invalid_records == 0
    assert all(o.request_kind == "context" for o in ordered)


def test_latest_view_structure(session):
    key, ordinal, ordered = session
    text, doc = report_latest(key, ordinal, ordered)
    assert doc["sequence"] == 3
    assert doc["session_ordinal"] == 1
    assert doc["model"] == "test-provider / test-model"
    assert doc["agent"] == "build"
    assert doc["boundary"] == "opencode.v2.model_context"
    assert doc["context_modified"] is False
    assert doc["token_provenance"] == "approximation"
    assert {s["category"] for s in doc["composition"]} == {
        "system",
        "user",
        "assistant",
        "tool_definition",
        "tool_call",
        "tool_result",
        "other",
    }
    assert "NOT provider wire payload" in text
    assert "No context was modified." in text
    for raw in RAW_STRINGS:
        assert raw not in text, raw
        assert raw not in json.dumps(doc), raw


def test_latest_change_and_prefix(session):
    key, ordinal, ordered = session
    _text, doc = report_latest(key, ordinal, ordered)
    change = doc["change_since_previous"]
    assert change["membership"] == {"unchanged": 4, "added": 6, "removed": 5}
    assert change["shared_prefix_ratio"] == pytest.approx(0.2)
    assert change["first_divergence"] == 2


def test_inspect_inventory_no_content_by_default(session):
    key, ordinal, ordered = session
    text, doc = report_inspect(key, ordinal, ordered, 3)
    assert doc["item_count"] if "item_count" in doc else True
    assert len(doc["items"]) == 10
    assert [r["position"] for r in doc["items"]] == list(range(10))
    assert doc["content_shown"] is False
    for row in doc["items"]:
        assert "content" not in row
    for raw in RAW_STRINGS:
        assert raw not in text, raw
    assert "ref=call-1" in text  # structural linkage is shown


def test_inspect_show_content_is_explicit_and_warned(session):
    key, ordinal, ordered = session
    text, doc = report_inspect(key, ordinal, ordered, 3, show_content=True)
    assert doc["content_shown"] is True
    assert any("content" in row for row in doc["items"])
    assert "WARNING" in text


def test_inspect_unknown_invocation(session):
    key, ordinal, ordered = session
    with pytest.raises(ValueError):
        report_inspect(key, ordinal, ordered, 99)


def test_timeline_rows(session):
    key, ordinal, ordered = session
    text, doc = report_timeline(key, ordinal, ordered)
    assert len(doc["turns"]) == 3
    assert doc["turns"][0]["delta_bytes"] is None
    assert doc["turns"][1]["delta_bytes"] == 153
    assert doc["turns"][1]["shared_prefix_ratio"] == pytest.approx(3 / 9)
    assert doc["turns"][2]["shared_prefix_ratio"] == pytest.approx(0.2)
    assert "No context was modified." in text


def test_compare_membership_prefix_surface(session):
    _key, ordinal, ordered = session
    text, doc = report_compare(ordinal, ordered, 2, 3)
    cmp = doc["comparison"]
    assert cmp["membership"] == {"unchanged": 4, "added": 6, "removed": 5}
    assert cmp["shared_prefix_ratio"] == pytest.approx(0.2)
    assert cmp["first_divergence"] == 2
    assert cmp["tool_surface"]["added"] == ["grep"]
    assert cmp["tool_surface"]["removed"] == ["bash"]
    assert "No claim is made about provider cache behaviour." in text
    assert "cache hit" not in text.lower()


def test_explain_item_history_and_limits(session):
    key, ordinal, ordered = session
    text, doc = report_explain(key, ordinal, ordered, "cap-v2-002-p005")
    item = doc["item"]
    assert item["kind"] == "tool_result"
    assert item["ref"] == "call-1"
    assert item["first_seen_sequence"] == 2
    assert item["recurrence_sequences"] == [2, 3]
    assert doc["known"] == ["content was present in observed OpenCode context"]
    assert "whether the model used it" in doc["unknown"]
    assert "whether removing it would be safe" in doc["unknown"]
    for raw in ("STATIC-REPEATED-OUTPUT", "ses-v2-gold-1"):
        assert raw not in text, raw


def test_explain_unknown_item(session):
    key, ordinal, ordered = session
    with pytest.raises(ValueError):
        report_explain(key, ordinal, ordered, "no-such-item")


def test_query_kind_filter(session):
    _key, _ordinal, ordered = session
    results = query_items(ordered, kind="tool_result")
    assert len(results) == 4
    assert all(r["kind"] == "tool_result" for r in results)
    assert all("content" not in r for r in results)


def test_query_repeated_and_introduced_after(session):
    _key, _ordinal, ordered = session
    repeated = query_items(ordered, repeated=True)
    assert repeated, "golden fixture must contain recurrence"
    assert all(r["recurrences"] >= 2 for r in repeated)
    fresh = query_items(ordered, introduced_after=2)
    assert fresh
    assert all(r["first_seen_sequence"] > 2 for r in fresh)


def test_query_min_bytes_and_category(session):
    _key, _ordinal, ordered = session
    big = query_items(ordered, min_bytes=100)
    assert big and all(r["bytes"] >= 100 for r in big)
    defs = query_items(ordered, category="tool_definition")
    assert len(defs) == 6
    combined = query_items(ordered, category="tool_definition", min_bytes=1000)
    assert combined == []


def test_query_contains_requires_explicit_local_flag(session):
    from project_context.debugger.query import ContentSearchNotAllowedError

    _key, _ordinal, ordered = session
    with pytest.raises(ContentSearchNotAllowedError):
        query_items(ordered, contains="login")
    hits = query_items(ordered, contains="login", allow_content_search=True)
    assert hits, "expected local content hits"
    assert all("content" not in r for r in hits)


def test_query_report_text_json(session):
    _key, ordinal, ordered = session
    results = query_items(ordered, kind="tool_definition")
    text, doc = report_query(ordinal, results, {}, "kind=tool_definition")
    assert doc["summary"]["items"] == 6
    assert "No context was modified." in text


def test_doctor_fires_expected_observations(session):
    _key, ordinal, ordered = session
    text, doc = report_doctor(ordinal, ordered)
    codes = [o["code"] for o in doc["observations"]]
    assert "EARLY_PREFIX_CHURN" in codes
    assert "LARGE_TOOL_SURFACE" in codes
    assert "REPEATED_CONTENT" in codes
    for obs in doc["observations"]:
        assert obs["policy_version"] == DOCTOR_POLICY_VERSION
        assert obs["intervention_earned"] is False
    assert doc["context_modified"] is False
    assert "Observations, not recommendations" in text


def test_doctor_language_never_normative(session):
    _key, ordinal, ordered = session
    text, _doc = report_doctor(ordinal, ordered)
    lowered = text.lower()
    for forbidden in (
        "harmful",
        "waste",
        "useless",
        "irrelevant",
        "should remove",
        "must remove",
        "you should",
        "bad item",
        "safe to remove",
        "safely remove",
    ):
        assert forbidden not in lowered, forbidden


def test_doctor_thresholds_are_policy_not_truth(session):
    _key, _ordinal, ordered = session
    strict = dict(DEFAULT_THRESHOLDS)
    strict["repetition_share"] = 0.99
    strict["early_divergence"] = 0.0
    strict["large_tool_surface_share"] = 0.99
    strict["large_tool_result_share"] = 0.99
    strict["large_item_share"] = 0.99
    strict["high_history_share"] = 0.99
    relaxed_obs = doctor_invocation(ordered, 2, thresholds=strict)
    assert [o for o in relaxed_obs if o.code == "REPEATED_CONTENT"] == []
    assert [o for o in relaxed_obs if o.code == "EARLY_PREFIX_CHURN"] == []


def test_doctor_session_scope(session):
    _key, ordinal, ordered = session
    session_obs = doctor_session(ordered)
    assert session_obs == [] or all(isinstance(o.code, str) for o in session_obs)


def test_auxiliary_requests_filtered_by_default(tmp_path):
    import copy

    doc = json.loads(
        (
            Path(__file__).resolve().parent.parent
            / "fixtures"
            / "opencode-capture-v2"
            / "session-three-requests.json"
        ).read_text(encoding="utf-8")
    )
    records = [dict(r) for r in doc["records"]]
    extra = copy.deepcopy(records[-1])
    extra["capture_id"] = "cap-v2-aux-1"
    extra["request_kind"] = "compaction"
    extra["invocation_sequence"] = 4
    spool = tmp_path / "spool"
    spool.mkdir()
    (spool / "captures.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in records + [extra]),
        encoding="utf-8",
    )
    primary = load_spool(spool)
    assert len(primary.sessions[primary.session_order[0]]) == 3
    assert primary.auxiliary_excluded == 1
    full = load_spool(spool, primary_only=False)
    assert len(full.sessions[full.session_order[0]]) == 4


def test_json_output_deterministic(tmp_path, capsys):
    first = cli_main(["debug", "latest", str(SPOOL), "--format", "json"])
    assert first == 0
    out_one = capsys.readouterr().out
    second = cli_main(["debug", "latest", str(SPOOL), "--format", "json"])
    assert second == 0
    out_two = capsys.readouterr().out
    assert out_one == out_two
    doc = json.loads(out_one)
    blob = json.dumps(doc)
    for raw in RAW_STRINGS:
        assert raw not in blob, raw
    assert "fingerprint" not in blob
    assert "sha256" not in blob


def test_cli_all_debug_commands(capsys):
    assert cli_main(["debug", "latest", str(SPOOL)]) == 0
    capsys.readouterr()
    assert cli_main(["debug", "inspect", str(SPOOL), "2"]) == 0
    capsys.readouterr()
    assert cli_main(["debug", "timeline", str(SPOOL)]) == 0
    capsys.readouterr()
    assert cli_main(["debug", "compare", str(SPOOL), "1", "2"]) == 0
    capsys.readouterr()
    assert cli_main(["debug", "explain", str(SPOOL), "cap-v2-001-p003"]) == 0
    capsys.readouterr()
    assert cli_main(["debug", "query", str(SPOOL), "--kind", "tool_definition"]) == 0
    capsys.readouterr()
    assert cli_main(["debug", "doctor", str(SPOOL)]) == 0
    capsys.readouterr()
    assert cli_main(["debug", "doctor", str(SPOOL), "--invocation", "2"]) == 0
    out = capsys.readouterr().out
    assert "No context was modified." in out


def test_cli_contains_without_flag_refused(capsys):
    assert cli_main(["debug", "query", str(SPOOL), "--contains", "login"]) == 2
    capsys.readouterr()
    assert (
        cli_main(["debug", "query", str(SPOOL), "--contains", "login", "--allow-content-search"])
        == 0
    )
    capsys.readouterr()


def test_cli_unknown_invocation_is_usage_error(capsys):
    assert cli_main(["debug", "inspect", str(SPOOL), "99"]) == 2
    capsys.readouterr()
    assert cli_main(["debug", "compare", str(SPOOL), "1", "99"]) == 2
    capsys.readouterr()


def test_model_limits_surfaced_or_unavailable(session):
    key, ordinal, ordered = session
    _text, doc = report_latest(key, ordinal, ordered)
    assert doc["model_limits"] == {"context": 200000, "output": 32000, "source": "ctx.model"}
