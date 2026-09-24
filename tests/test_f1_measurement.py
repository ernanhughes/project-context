"""F1 measurement dry run, on synthetic sessions whose numbers are known in advance.

Expected values here come from what the builder wrote (the part texts), or are worked out
by hand and written as literals. None comes from running the analyser and copying its
output. There is no embedding and no model similarity judge anywhere.

The sessions have the shape OpenCode 2.0.16 really produces: role plus a content list of
text, reasoning, tool-call and tool-result parts.
"""

import json
import sqlite3
from pathlib import Path

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
    A,
    Call,
    Msg,
    Req,
    Result,
    Think,
    build_session,
    definition_text,
    growth_session,
    long_session,
    no_tools_session,
    rewrite_session,
)
from project_context.corpus.usage import read_session_usage
from project_context.opencode.bridge import integrity_of

DEFS = [definition_text(n, d) for n, d in sorted(TOOLS.items())]
SYSTEM = "S" * 100


def b(text: str) -> int:
    return len(text.encode("utf-8"))


def expected_request(history):
    return DEFS + [SYSTEM] + [m.rendered() for m in history]


@pytest.fixture(scope="module")
def growth():
    records, histories = growth_session()
    return records, histories, analyse_session(records)


def test_hand_worked_part_sizes_match_the_literals(growth):
    """The fixture itself: worked-out lengths written as literals."""
    _, histories, _ = growth
    assert b(histories[1][2].rendered()) == 19  # read {"path": "f1"}
    assert b(histories[2][4].rendered()) == 29  # shell {"command": "npm test"}
    assert b(histories[1][3].rendered()) == 500
    assert b(DEFS[0]) + b(DEFS[1]) == 68 + 79


def test_rendered_input_growth_per_request(growth):
    _, histories, l1 = growth
    sizes = [sum(b(t) for t in expected_request(h)) for h in histories]
    assert [r["bytes"] for r in l1["requests"]] == sizes == GROWTH_EXPECTED["bytes"]
    assert sizes[1] - sizes[0] == 60 + 19 + 500  # the assistant text, a call and its result
    assert sizes[4] - sizes[3] == 29 + 350


def test_contribution_by_category(growth):
    _, _, l1 = growth
    last = l1["requests"][-1]["bytes_by_category"]
    assert last == GROWTH_EXPECTED["last_request_category_bytes"]
    assert sum(last.values()) == l1["requests"][-1]["bytes"]
    assert l1["session"]["largest_growing_category"] == "tool_result"


def test_carry_over_and_redundant_payload_are_different_quantities(growth):
    """History re-sent is expected (carry-over). The same output twice in one request is not."""
    _, _, l1 = growth
    req = l1["requests"]
    assert [r["new_bytes"] for r in req] == GROWTH_EXPECTED["new_bytes"]
    assert [r["carry_over_bytes"] for r in req] == GROWTH_EXPECTED["carry_over_bytes"]
    assert [r["redundant_payload_bytes"] for r in req] == GROWTH_EXPECTED["redundant_payload_bytes"]
    assert [r["duplicate_part_bytes"] for r in req] == GROWTH_EXPECTED["duplicate_part_bytes"]
    assert req[3]["redundant_payload_parts"] == 1 and req[3]["redundant_file_bytes"] == 500
    assert req[4]["carry_over_bytes"] > req[4]["redundant_payload_bytes"] * 3


def test_a_repeated_read_is_new_material_not_carry_over(growth):
    """The third request already held one copy of the file; the fourth adds a second copy.
    The second copy is not carried over, because the previous request held it only once."""
    _, _, l1 = growth
    fourth = l1["requests"][3]
    assert fourth["new_bytes"] == 19 + 500 + 20  # the repeated call, its repeated output, an answer


def test_duplicate_share_is_the_redundant_payload_over_the_request(growth):
    _, _, l1 = growth
    assert l1["session"]["last_request_redundant_payload_share"] == round(500 / 2143, 6)


def test_stable_prefix_under_the_assumed_order(growth):
    _, _, l1 = growth
    prefixes = [r["prefix"] for r in l1["requests"]]
    assert prefixes[0] is None
    assert [p["bytes"] if p else None for p in prefixes] == GROWTH_EXPECTED["prefix_bytes"]
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
    assert (
        l1["session"]["last_request_tool_result_share"]
        == GROWTH_EXPECTED["last_request_tool_result_share"]
    )


def test_call_identity_uses_the_observed_arguments(growth):
    """Same tool, same arguments, different bytes back: one identity. Same tool, different
    arguments would not be. The arguments are observed, so no title is needed."""
    _, _, l1 = growth
    assert [r["identities_with_differing_bytes"] for r in l1["requests"]] == GROWTH_EXPECTED[
        "identities_with_differing_bytes"
    ]
    assert [r["max_calls_per_identity"] for r in l1["requests"]] == GROWTH_EXPECTED[
        "max_calls_per_identity"
    ]
    assert l1["session"]["identities_with_differing_bytes"] == 1
    assert OBSERVABILITY["tool_call_arguments"][0] == "OBSERVED"
    assert OBSERVABILITY["same_call_different_bytes"][0] == "DERIVED"
    assert OBSERVABILITY["repository_state_or_version"][0] == UNOBSERVED


def test_different_arguments_are_different_calls():
    a = Call("c1", "read", path="one")
    a2 = Call("c2", "read", path="two")
    out = ("x" * 40, "y" * 40)
    reqs = [Req([a, Result("c1", "read", out[0]), a2, Result("c2", "read", out[1])])]
    session = analyse_session(build_session("synthetic-args", reqs))["session"]
    assert session["identities_with_differing_bytes"] == 0
    assert session["max_calls_per_identity_last_request"] == 1


def test_stratum_inputs_come_from_call_arguments():
    from project_context.corpus.synthetic import edit_session, repeated_test_run_session

    assert analyse_session(edit_session(3))["session"]["distinct_edit_targets"] == 3
    assert analyse_session(edit_session(1))["session"]["distinct_edit_targets"] == 1
    assert analyse_session(repeated_test_run_session(3))["session"]["test_command_call_count"] == 3
    growth_s = analyse_session(growth_session()[0])["session"]
    assert growth_s["test_command_call_count"] == 2 and growth_s["edit_call_count"] == 0


def test_window_pressure_is_reported_three_ways_and_not_merged(growth):
    _, histories, l1 = growth
    from project_context.domain.items import estimate_tokens

    last = l1["requests"][-1]
    texts = expected_request(histories[-1])
    assert last["est_tokens_words"] == sum(estimate_tokens(t)[0] for t in texts)
    assert last["est_tokens_bytes"] == -(-2143 // 4) == 536
    assert last["window_fraction_bytes_estimate"] == round(536 / 1000, 6)
    assert last["window_fraction_word_estimate"] == round(last["est_tokens_words"] / 1000, 6)
    assert last["window_fraction_measured"] == UNOBSERVED  # no usage record was joined
    assert l1["session"]["usage_join"] == UNOBSERVED
    assert l1["session"]["window_fraction_max_measured"] == UNOBSERVED
    assert l1["session"]["window_fraction_max_bytes_estimate"] == round(536 / 1000, 6)


def test_the_input_limit_is_used_when_the_harness_records_one():
    reqs = [Req([Msg("user", "u" * 400)], limits={"context": 2000, "input": 500})]
    l1 = analyse_session(build_session("synthetic-limit", reqs))
    assert l1["session"]["window_limit_kind"] == "input"
    assert l1["requests"][0]["window_fraction_bytes_estimate"] == round(125 / 500, 6)


def test_appending_history_is_not_a_rewrite(growth):
    _, _, l1 = growth
    assert l1["session"]["history_rewrite_events"] == 0
    assert not any(r["history_rewrite"] for r in l1["requests"])


def test_context_rewriting_and_compaction_are_detected_and_kept_apart():
    l1 = analyse_session(rewrite_session())
    assert l1["session"]["primary_requests"] == 4  # the compaction record is not a primary request
    assert l1["session"]["other_requests"] == {"compaction": 1}
    assert l1["session"]["compaction_records"] == 1
    flags = [r["history_rewrite"] for r in l1["requests"]]
    assert flags == [False, False, True, False]  # after the compaction the history was replaced
    assert l1["session"]["history_rewrite_events"] == 1
    last = l1["requests"][-1]
    assert last["system_changed"] and last["prefix"]["first_divergence"] == "system"
    assert last["prefix"]["parts"] == 2  # only the two definitions still match
    assert l1["session"]["system_change_events"] == 1


def test_reasoning_is_its_own_category_and_a_dropped_reasoning_part_is_a_rewrite():
    keep = [Msg("user", "u" * 40), Think("t" * 50), A("a" * 30)]
    reqs = [Req(keep[:2]), Req(keep), Req([keep[0], keep[2]])]  # the last drops the reasoning
    l1 = analyse_session(build_session("synthetic-think", reqs))
    assert l1["requests"][1]["bytes_by_category"]["reasoning"] == 50
    assert [r["history_rewrite"] for r in l1["requests"]] == [False, False, True]


def test_unobserved_is_not_zero_and_reaches_the_aggregate():
    l1 = analyse_session(no_tools_session())
    assert l1["session"]["first_request_tool_definition_share"] == UNOBSERVED
    assert l1["session"]["tools_available_first_request"] == UNOBSERVED
    assert l1["session"]["window_fraction_max_bytes_estimate"] == UNOBSERVED
    assert l1["session"]["window_limit_kind"] == UNOBSERVED
    assert all(r["tool_definition_share"] == UNOBSERVED for r in l1["requests"])
    assert all(r["window_fraction_bytes_estimate"] == UNOBSERVED for r in l1["requests"])
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
    ca, cb, cc = (Call(f"c{i}", "read", path=f"f{i}") for i in range(3))
    body = "line one\nline two" * 4
    respaced = "line one  line   two" * 4  # spacing only
    reqs = [
        Req(
            [
                ca,
                Result("c0", "read", body),
                cb,
                Result("c1", "read", respaced),
                cc,
                Result("c2", "read", body),
            ]
        )
    ]
    r = analyse_session(build_session("synthetic-norm", reqs))["requests"][0]
    assert r["redundant_payload_bytes"] == b(body)  # the byte-identical copy
    assert r["normalised_only_redundant_bytes"] == b(respaced)  # the respaced one, kept apart


def test_a_tiny_repeated_output_is_not_redundant_payload():
    reqs = [
        Req(
            [
                Call("a", "edit", path="x"),
                Result("a", "edit", "ok"),
                Call("b", "edit", path="y"),
                Result("b", "edit", "ok"),
            ]
        )
    ]
    r = analyse_session(build_session("synthetic-tiny", reqs))["requests"][0]
    assert r["redundant_payload_bytes"] == 0 and r["duplicate_part_bytes"] == 2


def test_a_result_list_is_read_as_its_text():
    """Shell results arrive as a list of content items; their text is what counts."""
    record = build_session("synthetic-list", [Req([Call("a", "shell", command="x")])])[0]
    record["messages"].append(
        {
            "role": "tool",
            "content": [
                {
                    "type": "tool-result",
                    "id": "a",
                    "name": "shell",
                    "result": {"type": "content", "value": [{"type": "text", "text": "out" * 20}]},
                    "providerExecuted": False,
                }
            ],
        }
    )
    record["integrity"] = {"sha256": integrity_of(record)}
    assert analyse_session([record])["requests"][0]["bytes_by_category"]["tool_result"] == 60


# ------------------------------------------------------------------------- completeness
def test_completeness_of_the_synthetic_sessions():
    for records in (growth_session()[0], rewrite_session(), no_tools_session()):
        assert assess_session(records).complete
    records = growth_session()[0]
    assert "sequence_gap" in assess_session(records[:2] + records[3:]).reasons
    assert "first_record_not_sequence_one" in assess_session(records[1:]).reasons
    assert "sequence_duplicate_or_restart" in assess_session(records + records[:1]).reasons
    assert "skipped_lines" in assess_session(records, skipped_lines=1).reasons
    tampered = json.loads(json.dumps(records))
    tampered[0]["messages"][0]["content"][0]["text"] = "changed"
    assert "integrity_mismatch" in assess_session(tampered).reasons
    assert assess_session([]).reasons == ("no_records",)
    only_compaction = [dict(records[0], request_kind="compaction")]
    only_compaction[0]["integrity"] = {"sha256": integrity_of(only_compaction[0])}
    assert "no_primary_request" in assess_session(only_compaction).reasons


def test_a_persisted_sequence_across_restarts_is_a_complete_session():
    """After a harness restart the adapter carries on numbering, so the session stays whole."""
    records = long_session(12)
    assert [r["invocation_sequence"] for r in records] == list(range(1, 13))
    assert assess_session(records).complete
    restarted = json.loads(json.dumps(records))
    for r in restarted[6:]:  # the old in-memory counter would have started again at 1 here
        r["invocation_sequence"] -= 6
        r["integrity"] = {"sha256": integrity_of(r)}
    assert "sequence_duplicate_or_restart" in assess_session(restarted).reasons


def test_an_ordering_failure_marker_makes_the_session_incomplete_even_if_numbers_look_whole():
    from project_context.corpus.completeness import CONTROL_SCHEMA, split_control

    records = growth_session()[0]
    marker = {
        "schema": CONTROL_SCHEMA,
        "event": "sequence_state_lost",
        "session_id": records[0]["session_id"],
        "captured_at": "2030-01-01T00:00:00Z",
    }
    mixed = [marker, *records]
    result = assess_session(mixed)
    assert not result.complete and result.reasons == ("ordering_state_lost",)
    data, control = split_control(mixed)
    assert len(data) == 5 and len(control) == 1
    assert result.primary_requests == 5  # the marker is not counted as a request


def test_a_message_in_another_shape_is_refused_not_misread():
    records = json.loads(json.dumps(growth_session()[0]))
    records[0]["messages"] = [
        {"info": {"id": "m1", "role": "user"}, "parts": [{"type": "text", "text": "old shape"}]}
    ]
    records[0]["integrity"] = {"sha256": integrity_of(records[0])}
    assert "unrecognised_message_shape" in assess_session(records).reasons


def test_observability_matrix_is_closed_and_states_what_the_calibration_changed():
    assert all(status in STATUSES for status, _ in OBSERVABILITY.values())
    for name in (
        "provider_cache_decisions",
        "render_order",
        "repository_state_or_version",
        "standing_instruction_split",
        "provider_added_material",
        "reasoning_sent_to_provider",
        "subagent_relations",
    ):
        assert name in unobserved_quantities()
    # Refuted by the calibration run, so no longer unobserved:
    assert OBSERVABILITY["tool_call_arguments"][0] == "OBSERVED"
    assert OBSERVABILITY["model_limit"][0] == "OBSERVED"
    for name in (
        "provider_reported_tokens",
        "provider_cost",
        "latency",
        "window_pressure_measured",
    ):
        assert OBSERVABILITY[name][0] == "JOINED"
    assert set(proxies()) == {"stable_prefix"}


def test_the_completeness_spec_lists_every_quantity_with_its_status():
    text = Path("specs/f1-capture-completeness.md").read_text(encoding="utf-8")
    for name, (status, _basis) in OBSERVABILITY.items():
        assert f"| `{name}` | {status} |" in text, name


# ------------------------------------------------------------------------- usage join
def usage_db(path, session, rows, other_session_rows=()):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE session_message (id TEXT, session_id TEXT, type TEXT, seq INTEGER, data TEXT)"
    )
    con.execute("CREATE TABLE credential (id TEXT, value TEXT)")
    con.execute("INSERT INTO credential VALUES ('x', 'never-read-this')")
    n = 0
    for sid, kind, data in [(session, k, d) for k, d in rows] + list(other_session_rows):
        n += 1
        con.execute(
            "INSERT INTO session_message VALUES (?,?,?,?,?)",
            (f"m{n}", sid, kind, n, json.dumps(data)),
        )
    con.commit()
    con.close()


def assistant(inp, out, read=0, write=0, cost=0.0, created=1000, completed=1500):
    return (
        "assistant",
        {
            "tokens": {
                "input": inp,
                "output": out,
                "reasoning": 0,
                "cache": {"read": read, "write": write},
            },
            "cost": cost,
            "time": {"created": created, "completed": completed},
            "content": [{"type": "text", "text": "private words that must never leave"}],
        },
    )


def test_usage_is_read_by_session_and_only_from_assistant_messages(tmp_path):
    db = tmp_path / "opencode.db"
    usage_db(
        db,
        "ses-a",
        [
            ("user", {"text": "hello"}),
            assistant(100, 20, read=50, write=10, cost=0.5),
            assistant(30, 5, read=160),
        ],
        other_session_rows=[("ses-b", "assistant", assistant(999, 9)[1])],
    )
    rows = read_session_usage(db, "ses-a")
    assert rows == [
        {
            "prompt_tokens": 160,
            "output_tokens": 20,
            "cache_read_tokens": 50,
            "cost": 0.5,
            "latency_ms": 500,
        },
        {
            "prompt_tokens": 190,
            "output_tokens": 5,
            "cache_read_tokens": 160,
            "cost": 0.0,
            "latency_ms": 500,
        },
    ]
    assert read_session_usage(db, "ses-none") == []
    assert read_session_usage(tmp_path / "missing.db", "ses-a") is None
    assert "private words" not in json.dumps(rows)


def test_the_usage_reader_never_names_credential_tables():
    text = Path("src/project_context/corpus/usage.py").read_text(encoding="utf-8")
    code = text.split('"""', 2)[2]  # everything after the module docstring
    for forbidden in ("credential", "account", "control_account", "workspace", "kv"):
        assert forbidden not in code.lower().replace("_query", ""), forbidden
    assert "mode=ro" in code


def test_the_usage_reader_opens_read_only(tmp_path):
    db = tmp_path / "opencode.db"
    usage_db(db, "ses-a", [assistant(1, 1)])
    before = db.read_bytes()
    read_session_usage(db, "ses-a")
    assert db.read_bytes() == before


def test_measured_usage_is_joined_only_when_the_counts_agree(tmp_path):
    records, _ = growth_session()
    good = [
        {
            "prompt_tokens": 300 + 100 * i,
            "output_tokens": 10,
            "cache_read_tokens": 100 * i,
            "cost": 0.25,
            "latency_ms": 40,
        }
        for i in range(5)
    ]
    l1 = analyse_session(records, usage=good)
    assert l1["session"]["usage_join"] == "aligned"
    assert [r["measured_prompt_tokens"] for r in l1["requests"]] == [300, 400, 500, 600, 700]
    assert l1["session"]["window_fraction_max_measured"] == 0.7  # 700 of the 1000-token window
    assert l1["session"]["measured_cost_total"] == 1.25
    assert l1["requests"][1]["measured_cache_read_tokens"] == 100
    assert l1["session"]["provider_cache_read_fraction_median"] == round(
        sorted([100 / 400, 200 / 500, 300 / 600, 400 / 700])[1:3][0] / 2
        + sorted([100 / 400, 200 / 500, 300 / 600, 400 / 700])[1:3][1] / 2,
        6,
    )
    bad = analyse_session(records, usage=good[:4])
    assert bad["session"]["usage_join"] == "count_mismatch"
    assert bad["requests"][0]["measured_prompt_tokens"] == UNOBSERVED
    assert bad["session"]["window_fraction_max_measured"] == UNOBSERVED


def test_the_estimates_can_be_compared_with_what_the_provider_measured():
    """The calibration run found bytes divided by four close and words times 1.3 far low. This
    only checks that both are kept beside the measurement so that comparison is possible."""
    records, _ = growth_session()
    measured = [
        {
            "prompt_tokens": 250 + 70 * i,
            "output_tokens": 1,
            "cache_read_tokens": 0,
            "cost": 0.0,
            "latency_ms": 1,
        }
        for i in range(5)
    ]
    last = analyse_session(records, usage=measured)["requests"][-1]
    assert {"measured_prompt_tokens", "est_tokens_bytes", "est_tokens_words"} <= set(last)
    assert last["est_tokens_bytes"] != last["est_tokens_words"]


def test_aggregates_drop_unobserved_sessions_and_count_them():
    from project_context.corpus.f1_aggregate import summarise

    assert summarise([0.1, 0.2, UNOBSERVED, 0.3]) == {
        "used": 3,
        "unobserved": 1,
        "median": 0.2,
        "min": 0.1,
        "max": 0.3,
    }
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


def test_worked_out_table_matches_the_analyser(growth):
    """The same table the dry-run script reconciles against, kept in one place."""
    _, _, l1 = growth
    session = l1["session"]
    for key in (
        "first_request_tool_definition_share",
        "last_request_redundant_payload_share",
        "last_request_tool_result_share",
    ):
        assert session[key] == GROWTH_EXPECTED[key], key
