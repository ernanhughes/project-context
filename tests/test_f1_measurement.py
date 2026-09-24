"""F1 measurement dry run, on synthetic sessions whose numbers are known in advance.

Expected values here come from what the builder wrote (the part texts), or are worked out
by hand and written as literals. None comes from running the analyser and copying its
output. There is no embedding and no model similarity judge anywhere.
"""

import json

import pytest

from project_context.corpus.completeness import (
    OBSERVABILITY,
    STATUSES,
    UNOBSERVED,
    assess_session,
    proxies,
    unobserved_quantities,
)
from project_context.corpus.f1_analysis import analyse_session, dumps, growth_shape, reconcile
from project_context.corpus.synthetic import (
    GROWTH_EXPECTED,
    TOOLS,
    definition_text,
    growth_session,
    long_session,
    no_tools_session,
    rewrite_session,
)
from project_context.opencode.bridge import integrity_of

DEFS = [definition_text(n, d) for n, d in sorted(TOOLS.items())]
SYSTEM = "S" * 100


def b(text: str) -> int:
    return len(text.encode("utf-8"))


def expected_request(history):
    texts = DEFS + [SYSTEM] + [m.rendered() for m in history]
    return texts


@pytest.fixture(scope="module")
def growth():
    records, histories = growth_session()
    return records, histories, analyse_session(records)


def test_hand_worked_sizes_match_the_worked_literals(growth):
    """Sanity of the fixture itself: worked-out literals for the tool result lengths."""
    _, histories, _ = growth
    assert b(histories[1][2].rendered()) == 529  # "[tool:read call:c1 title:f1]" 28 + "\n" + 500
    assert b(histories[2][3].rendered()) == 335  # "[tool:bash call:c2 title:npm test]" 34 + 1 + 300
    assert b(histories[4][7].rendered()) == 385  # 34 + 1 + 350


def test_rendered_input_growth_per_request(growth):
    _, histories, l1 = growth
    sizes = [sum(b(t) for t in expected_request(h)) for h in histories]
    assert [r["bytes"] for r in l1["requests"]] == sizes
    assert sizes[1] - sizes[0] == 60 + 529  # A1 and T1
    assert sizes[2] - sizes[1] == 335 + 30
    assert sizes[3] - sizes[2] == 529 + 20
    assert sizes[4] - sizes[3] == 385


def test_contribution_by_category_and_source(growth):
    _, histories, l1 = growth
    last = l1["requests"][-1]["bytes_by_category"]
    assert last["system"] == 100
    assert last["user"] == 40 + 30
    assert last["assistant"] == 60 + 20
    assert last["tool_result"] == 529 + 335 + 529 + 385
    assert last["tool_definition"] == sum(b(t) for t in DEFS)
    assert sum(last.values()) == l1["requests"][-1]["bytes"]
    assert l1["session"]["largest_growing_category"] == "tool_result"


def test_carry_over_and_redundant_payload_are_different_quantities(growth):
    """History re-sent is expected (carry-over). The same output twice in one request is not."""
    _, _, l1 = growth
    req = l1["requests"]
    assert [r["new_bytes"] for r in req] == [286, 589, 365, 549, 385]
    assert [r["carry_over_bytes"] for r in req] == [0, 286, 875, 1240, 1789]
    # T3 repeats T1's output under a different call id: 529 bytes, one part, a file read.
    assert [r["redundant_payload_bytes"] for r in req] == [0, 0, 0, 529, 529]
    assert req[3]["redundant_payload_parts"] == 1 and req[3]["redundant_file_bytes"] == 529
    assert req[4]["carry_over_bytes"] > req[4]["redundant_payload_bytes"] * 3


def test_duplicate_share_is_the_redundant_payload_over_the_request(growth):
    _, _, l1 = growth
    assert l1["session"]["last_request_redundant_payload_share"] == round(529 / 2174, 6)


def test_stable_prefix_under_the_assumed_order(growth):
    _, _, l1 = growth
    prefixes = [r["prefix"] for r in l1["requests"]]
    assert prefixes[0] is None
    assert [p["bytes"] for p in prefixes[1:]] == [286, 875, 1240, 1789]  # each previous request
    assert all(p["first_divergence"] == "append_only" for p in prefixes[1:])
    assert l1["assumed_render_order"] == ["tool_definition", "system", "messages"]


def test_tool_definition_share_and_stability(growth):
    _, histories, l1 = growth
    defs = sum(b(t) for t in DEFS)
    first_total = sum(b(t) for t in expected_request(histories[0]))
    assert l1["session"]["first_request_tool_definition_share"] == round(defs / first_total, 6)
    assert l1["session"]["definition_change_events"] == 0
    assert l1["session"]["tools_available_first_request"] == 2


def test_tool_output_growth_and_tool_result_share(growth):
    _, _, l1 = growth
    shares = [r["tool_result_share"] for r in l1["requests"]]
    assert shares[0] == 0.0 and shares == sorted(shares)
    assert l1["session"]["last_request_tool_result_share"] == round(1778 / 2174, 6)


def test_observed_freshness_is_only_a_proxy_and_is_flagged(growth):
    """T4 returns different bytes from T2 under the same tool and title: one identity."""
    _, _, l1 = growth
    assert [r["identities_with_differing_bytes"] for r in l1["requests"]] == [0, 0, 0, 0, 1]
    assert l1["session"]["identities_with_differing_bytes"] == 1
    assert OBSERVABILITY["same_call_different_bytes"][0] == "PROXY"
    assert OBSERVABILITY["repository_state_or_version"][0] == UNOBSERVED


def test_window_distance_uses_the_declared_limit(growth):
    _, histories, l1 = growth
    from project_context.domain.items import estimate_tokens

    est = sum(estimate_tokens(t)[0] for t in expected_request(histories[-1]))
    assert l1["requests"][-1]["window_fraction_estimate"] == round(est / 1000, 6)


def test_appending_history_is_not_a_rewrite(growth):
    _, _, l1 = growth
    assert l1["session"]["history_rewrite_events"] == 0
    assert not any(r["history_rewrite"] for r in l1["requests"])


def test_context_rewriting_and_compaction_are_detected_and_kept_apart():
    records = rewrite_session()
    l1 = analyse_session(records)
    assert l1["session"]["primary_requests"] == 4  # the compaction record is not a primary request
    assert l1["session"]["other_requests"] == {"compaction": 1}
    assert l1["session"]["compaction_records"] == 1
    flags = [r["history_rewrite"] for r in l1["requests"]]
    assert flags == [False, False, True, False]  # third primary request replaced earlier history
    assert l1["session"]["history_rewrite_events"] == 1
    # The system prompt changes in the last request: prefix stops after the definitions.
    last = l1["requests"][-1]
    assert last["system_changed"] and last["prefix"]["first_divergence"] == "system"
    assert last["prefix"]["parts"] == 2
    assert l1["session"]["system_change_events"] == 1


def test_unobserved_is_not_zero_and_reaches_the_aggregate():
    l1 = analyse_session(no_tools_session())
    assert l1["session"]["first_request_tool_definition_share"] == UNOBSERVED
    assert l1["session"]["tools_available_first_request"] == UNOBSERVED
    assert l1["session"]["window_fraction_max"] == UNOBSERVED
    assert all(r["tool_definition_share"] == UNOBSERVED for r in l1["requests"])
    assert all(r["window_fraction_estimate"] == UNOBSERVED for r in l1["requests"])
    # What the capture does see stays a real number, including a real zero.
    assert l1["requests"][0]["bytes_by_category"].get("tool_definition", 0) == 0
    assert l1["session"]["primary_requests"] == 3


def test_a_real_zero_is_kept_distinct_from_unobserved():
    records, _ = growth_session()
    l1 = analyse_session(records)
    assert l1["requests"][0]["redundant_payload_bytes"] == 0  # observed, and zero
    assert l1["session"]["compaction_records"] == 0  # observed, and zero
    assert 0 != UNOBSERVED


def test_the_derivative_reconciles_with_its_source():
    for records in (growth_session()[0], rewrite_session(), no_tools_session(), long_session()):
        assert reconcile(records, analyse_session(records)) == []


def test_reconciliation_notices_a_derivative_that_lost_a_part():
    records, _ = growth_session()
    l1 = analyse_session(records)
    l1["requests"][2]["parts"] -= 1
    assert reconcile(records, l1)


def test_analysis_is_deterministic_to_the_byte():
    records, _ = growth_session()
    assert dumps(analyse_session(records)) == dumps(
        analyse_session(json.loads(json.dumps(records)))
    )


def test_growth_shape_rule():
    assert growth_shape([100, 110, 121, 133]) == "steady"
    assert growth_shape([100, 200, 210, 215]) == "step"  # a request at least 1.5 times the last
    assert growth_shape([100, 110, 121, 135, 160, 200, 260]) == "accelerating"
    assert growth_shape([100, 130]) == "undefined_too_few_requests"


def test_exact_normalised_identity_is_reported_apart_from_byte_identity():
    from project_context.corpus.synthetic import Msg, Req, build_session

    a = Msg("tool", tool="read", call="c1", title="f", body="line one\nline two")
    b_ = Msg("tool", tool="read", call="c2", title="f", body="line one  line   two")  # spacing only
    c = Msg("tool", tool="read", call="c3", title="f", body="line one\nline two")  # byte identical
    l1 = analyse_session(build_session("synthetic-norm", [Req([a, b_, c])]))
    r = l1["requests"][0]
    assert r["redundant_payload_bytes"] == b(c.rendered())
    assert r["normalised_only_redundant_bytes"] == b(b_.rendered())


def test_completeness_of_the_synthetic_sessions():
    for records in (growth_session()[0], rewrite_session(), no_tools_session()):
        assert assess_session(records).complete
    records = growth_session()[0]
    assert "sequence_gap" in assess_session(records[:2] + records[3:]).reasons
    assert "first_record_not_sequence_one" in assess_session(records[1:]).reasons
    assert "sequence_duplicate_or_restart" in assess_session(records + records[:1]).reasons
    assert "skipped_lines" in assess_session(records, skipped_lines=1).reasons
    tampered = json.loads(json.dumps(records))
    tampered[0]["messages"][0]["parts"][0]["text"] = "changed"
    assert "integrity_mismatch" in assess_session(tampered).reasons
    assert assess_session([]).reasons == ("no_records",)
    only_compaction = [dict(records[0], request_kind="compaction")]
    only_compaction[0]["integrity"] = {"sha256": integrity_of(only_compaction[0])}
    assert "no_primary_request" in assess_session(only_compaction).reasons


def test_observability_matrix_is_closed_and_states_its_unobservables():
    assert all(status in STATUSES for status, _ in OBSERVABILITY.values())
    for name in (
        "provider_cache_behaviour",
        "provider_usage_and_cost",
        "latency",
        "tool_call_arguments",
        "render_order",
        "repository_state_or_version",
        "standing_instruction_split",
    ):
        assert name in unobserved_quantities()
    assert {"stable_prefix", "tool_call_identity", "same_call_different_bytes"} <= set(proxies())


def test_worked_out_table_matches_the_analyser(growth):
    """The same table the dry-run script reconciles against, kept in one place."""
    _, _, l1 = growth
    req, session = l1["requests"], l1["session"]
    for key in ("bytes", "new_bytes", "carry_over_bytes", "redundant_payload_bytes"):
        assert [r[key] for r in req] == GROWTH_EXPECTED[key], key
    assert [r["prefix"]["bytes"] if r["prefix"] else None for r in req] == GROWTH_EXPECTED[
        "prefix_bytes"
    ]
    assert [r["identities_with_differing_bytes"] for r in req] == GROWTH_EXPECTED[
        "identities_with_differing_bytes"
    ]
    for key in (
        "first_request_tool_definition_share",
        "last_request_redundant_payload_share",
        "last_request_tool_result_share",
    ):
        assert session[key] == GROWTH_EXPECTED[key], key


def test_the_completeness_spec_lists_every_quantity_with_its_status():
    from pathlib import Path

    text = Path("specs/f1-capture-completeness.md").read_text(encoding="utf-8")
    for name, (status, _basis) in OBSERVABILITY.items():
        assert f"| `{name}` | {status} |" in text, name


def test_aggregates_drop_unobserved_sessions_and_count_them():
    from project_context.corpus.f1_aggregate import summarise

    assert summarise([0.1, 0.2, UNOBSERVED, 0.3]) == {
        "used": 3,
        "unobserved": 1,
        "median": 0.2,
        "min": 0.1,
        "max": 0.3,
    }
    # Treating the unobserved one as zero would have moved the median to 0.15.
    assert summarise([UNOBSERVED, UNOBSERVED]) == {"used": 0, "unobserved": 2, "value": UNOBSERVED}
    assert summarise([0.0, 0.0])["median"] == 0.0  # a real zero stays a zero
    four = summarise([0.1, 0.2, 0.3, 0.4])
    assert four["q1"] == 0.175 and four["q3"] == 0.325


def test_aggregate_over_real_derivatives_keeps_the_no_tools_session_out_of_tool_shares():
    from project_context.corpus.f1_aggregate import aggregate

    sessions = [
        analyse_session(growth_session()[0])["session"],
        analyse_session(no_tools_session())["session"],
        analyse_session(growth_session()[0])["session"],
    ]
    agg = aggregate(sessions)
    share = agg["quantities"]["first_request_tool_definition_share"]
    assert share["used"] == 2 and share["unobserved"] == 1
    assert share["median"] == GROWTH_EXPECTED["first_request_tool_definition_share"]
    assert agg["quantities"]["primary_requests"]["used"] == 3
