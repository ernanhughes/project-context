"""F1 pipeline: strata, shape cards, routing triggers, session index, and the privacy dry run.

Everything here is synthetic. Nothing enters the ecological corpus: the indexes built in
these tests are dry-run indexes in a temporary directory.
"""

import inspect
import json

import pytest

from project_context.corpus import f1_pipeline, routing, strata
from project_context.corpus.completeness import UNOBSERVED
from project_context.corpus.f1_analysis import analyse_session, dumps
from project_context.corpus.f1_pipeline import derivative_bytes, process_session
from project_context.corpus.privacy import gate, scan_raw, validate_l1
from project_context.corpus.session_index import (
    DRY_RUN,
    ECOLOGICAL,
    SessionIndex,
    SessionIndexError,
)
from project_context.corpus.shapecards import SHAPES, catalogue, derive_cards, validate_card
from project_context.corpus.synthetic import (
    PLANTED,
    SCANNER_BLIND_SPOT,
    A,
    Req,
    U,
    build_session,
    edit_session,
    growth_session,
    long_session,
    no_tools_session,
    privacy_session,
    repeated_test_run_session,
    rewrite_session,
)

PLANTED_TOKEN_MIN = 8
SIDECAR = {
    "language_family": "python",
    "size_band": "small",
    "has_tests": True,
    "task_type": "bugfix",
}


def dry_index(tmp_path):
    return SessionIndex.create(tmp_path / "session-index.json", DRY_RUN, "dry-run-campaign")


# ------------------------------------------------------------------------------ strata
def summary(records, declared=None):
    return analyse_session(records, declared=declared)["session"]


def edits(n_files, requests=6):
    return edit_session(n_files, requests)


def test_primary_stratum_is_a_function_of_the_session_alone():
    assert "counts" not in inspect.signature(strata.assign).parameters
    assert list(inspect.signature(strata.assign).parameters) == ["session", "declared"]
    a = strata.assign(summary(long_session()))
    assert a.primary == "S6"
    assert strata.assign(summary(long_session())) == a  # same input, same label, always


def test_each_stratum_definition():
    assert strata.assign(summary(no_tools_session())).primary == "S1"  # 3 requests, no edit
    assert strata.assign(summary(edits(1))).primary == "S2"
    assert strata.assign(summary(edits(3))).primary == "S3"
    assert strata.assign(summary(growth_session()[0])).primary == "S5"  # tool results over half
    assert "S6" in strata.assign(summary(rewrite_session())).satisfied  # compaction observed


def test_test_loop_stratum_from_shell_commands():
    a = strata.assign(summary(repeated_test_run_session(3)))
    assert a.satisfied.count("S4") == 1 and a.basis["S4"] == "derived"
    assert "S4" not in strata.assign(summary(repeated_test_run_session(2))).satisfied


def test_tags_are_secondary_and_declared_or_proxy_bases_are_recorded():
    declared = {"project_instructions": True}
    a = strata.assign(summary(growth_session()[0], declared), declared)
    assert a.primary == "S5" and "S7" in a.tags and "S8" in a.tags
    assert (
        a.basis["S7"] == "declared" and a.basis["S8"] == "derived" and a.basis["S5"] == "observed"
    )
    assert "S7" not in strata.PRIMARY_PRECEDENCE and "S8" not in strata.PRIMARY_PRECEDENCE


def test_a_session_that_fits_nothing_is_kept_unclassified_not_forced():
    reqs = [Req([U("u" * 20)] + [A("a" * 20)] * i) for i in range(8)]
    a = strata.assign(summary(build_session("synthetic-none", reqs)))
    assert a.primary == strata.UNCLASSIFIED and a.satisfied == ()


def test_natural_absence_is_recorded():
    cov = strata.coverage(
        [strata.assign(summary(long_session())), strata.assign(summary(edits(1)))]
    )
    assert cov["by_stratum"]["S6"]["primary"] == 1
    assert "S3" in cov["naturally_absent"] and "S4" in cov["naturally_absent"]
    assert cov["sessions"] == 2


# ------------------------------------------------------------------------------ shape cards
def cards_for(records, declared=None):
    return derive_cards(analyse_session(records, declared=declared or {}))


def test_shape_cards_of_the_growth_session():
    by_shape = {c.shape: c for c in cards_for(growth_session()[0])}
    assert {
        "repeated_file_material",
        "stale_observation_surviving",
        "repeated_re_read",
        "large_recoverable_artifact",
    } <= set(by_shape)
    material = by_shape["repeated_file_material"]
    assert material.magnitude["bytes"] == 500 and material.requests_showing == 2
    assert material.recreate == {"parts": 2, "part_bytes": 500, "repeats": 1}
    assert "repeated_tool_output" not in by_shape  # the repeated output was from a file read


def test_cards_are_structure_only():
    for records in (growth_session()[0], rewrite_session(), long_session()):
        for card in cards_for(records):
            data = card.to_dict()
            assert validate_card(data) == []
            assert set(data) == {"shape", "basis", "requests_showing", "magnitude", "recreate"}
            blob = json.dumps(data)
            assert not any(word in blob.lower() for word in ("prune", "improve", "harm", "wast"))


def test_card_validator_rejects_free_text_and_conclusions():
    card = cards_for(growth_session()[0])[0].to_dict()
    assert validate_card({**card, "note": "pruning would improve this"})
    assert validate_card({**card, "shape": "pruning would improve this"})
    assert validate_card({**card, "magnitude": {**card["magnitude"], "advice": 1}})
    assert validate_card({**card, "magnitude": {**card["magnitude"], "bytes": "many"}})
    assert validate_card({**card, "basis": "OBSERVED" if card["basis"] != "OBSERVED" else "PROXY"})


def test_invisible_shapes_appear_only_when_declared():
    assert not {c.shape for c in cards_for(growth_session()[0])} & {
        "scope_crossover_opportunity",
        "authority_conflict",
    }
    declared = {"scope_crossover": True, "authority_conflict": True}
    shapes = {c.shape: c for c in cards_for(growth_session()[0], declared)}
    assert shapes["scope_crossover_opportunity"].basis == "DECLARED"
    assert shapes["authority_conflict"].basis == "DECLARED"


def test_rewrite_and_compaction_shapes_and_volatile_prefix():
    shapes = {c.shape for c in cards_for(rewrite_session())}
    assert "compaction_or_rewrite_event" in shapes


def test_catalogue_separates_recurring_from_single_occurrence():
    a = cards_for(growth_session()[0])
    b = cards_for(growth_session()[0])
    c = cards_for(rewrite_session())
    cat = catalogue([a, b, c])
    assert "repeated_file_material" in cat["recurring"]
    assert "compaction_or_rewrite_event" in cat["single_occurrence"]
    assert set(cat["sessions_showing"]) == set(SHAPES)


# ------------------------------------------------------------------------------ routing
def sess(**over):
    base = {
        "first_request_tool_definition_share": 0.2,
        "last_request_redundant_payload_share": 0.2,
        "window_fraction_max_measured": 0.1,
        "window_fraction_max_bytes_estimate": 0.1,
        "window_fraction_max_word_estimate": 0.07,
        "compaction_records": 0,
        "prefix_fraction_median": 0.8,
    }
    return {**base, **over}


WINDOW_KEYS = (
    "window_fraction_max_measured",
    "window_fraction_max_bytes_estimate",
    "window_fraction_max_word_estimate",
)


def by_name(records):
    return {r.trigger: r for r in records}


def test_the_four_routing_values_are_exactly_the_registered_ones():
    assert (
        routing.TOOL_DEFINITION_SHARE,
        routing.DUPLICATE_SHARE,
        routing.WINDOW_FRACTION,
        routing.STABLE_PREFIX_FRACTION,
    ) == (0.10, 0.10, 0.60, 0.50)


def test_a_near_miss_is_borderline_not_absent():
    sessions = [sess(first_request_tool_definition_share=v) for v in (0.05, 0.098, 0.30)]
    r = by_name(routing.evaluate(sessions, [False] * 3))["T1_tool_context"]
    assert r.status == routing.NOT_TRIGGERED
    assert r.observed_value == 0.098 and r.routing_threshold == 0.10
    assert r.distance == -0.002 and r.relative_distance == -0.02
    assert r.band == "borderline"
    assert r.leave_one_out_flips >= 1  # dropping one session would have changed the routing


def test_a_clear_result_is_clear_and_stable():
    sessions = [sess(first_request_tool_definition_share=v) for v in (0.30, 0.31, 0.32, 0.33)]
    r = by_name(routing.evaluate(sessions, [False] * 4))["T1_tool_context"]
    assert r.status == routing.TRIGGERED and r.band == "clear" and r.leave_one_out_flips == 0


def test_too_few_sessions_is_not_evaluable_rather_than_not_triggered():
    r = by_name(routing.evaluate([sess(), sess()], [False, False]))["T1_tool_context"]
    assert r.status == routing.NOT_EVALUABLE and r.observed_value == UNOBSERVED
    assert r.band == "not_evaluable" and r.distance == UNOBSERVED


def test_unobserved_sessions_are_counted_and_not_treated_as_zero():
    sessions = [
        sess(first_request_tool_definition_share=UNOBSERVED),
        sess(first_request_tool_definition_share=0.2),
        sess(first_request_tool_definition_share=0.3),
        sess(first_request_tool_definition_share=0.4),
    ]
    r = by_name(routing.evaluate(sessions, [False] * 4))["T1_tool_context"]
    assert r.sessions_used == 3 and r.sessions_unobserved == 1 and r.observed_value == 0.3


def test_duplicate_and_prefix_triggers_look_only_at_long_sessions():
    sessions = [sess(last_request_redundant_payload_share=0.01) for _ in range(3)] + [
        sess(last_request_redundant_payload_share=0.5) for _ in range(3)
    ]
    flags = [False] * 3 + [True] * 3
    r = by_name(routing.evaluate(sessions, flags))
    assert (
        r["T2_safe_removal"].status == routing.TRIGGERED and r["T2_safe_removal"].sessions_used == 3
    )
    assert r["T4_cache_probe"].sessions_used == 3


def test_window_trigger_needs_two_sessions_or_a_compaction():
    def status(*fractions, compaction=0):
        sessions = [sess(**{k: f for k in WINDOW_KEYS}) for f in fractions]
        if compaction:
            sessions[0]["compaction_records"] = compaction
        return by_name(routing.evaluate(sessions, [False] * len(sessions)))["T3_externalise_recall"]

    assert status(0.9, 0.2, 0.1).status == routing.NOT_TRIGGERED  # one session is not two
    assert status(0.9, 0.7, 0.1).status == routing.TRIGGERED
    assert status(0.9, 0.7, 0.1).observed_value == 0.7  # the second-highest is the decisive one
    assert status(0.1, 0.1, 0.1, compaction=1).status == routing.TRIGGERED


def test_every_record_says_what_it_does_not_mean():
    for r in routing.evaluate([sess() for _ in range(4)], [True] * 4):
        assert "says nothing about effect size" in r.meaning
        assert set(r.to_dict()) >= {
            "metric",
            "observed_value",
            "routing_threshold",
            "status",
            "distance",
        }


def test_the_prefix_line_can_be_moved_to_see_how_much_the_answer_depends_on_it():
    longs = [sess(prefix_fraction_median=v) for v in (0.40, 0.45, 0.55, 0.60)]
    out = routing.prefix_line_sensitivity(longs)
    assert out["line_lower"] >= out["line_as_registered"] >= out["line_higher"]


# ------------------------------------------------------------------------------ session index
def test_session_index_keeps_dry_runs_out_of_the_corpus(tmp_path):
    dry = dry_index(tmp_path)
    out = process_session(
        privacy_session(), session_key="dry-run-ses-7f3a91", sidecar=SIDECAR, session_index=dry
    )
    assert out.session_ordinal == 1 and dry.kind == DRY_RUN
    with pytest.raises(SessionIndexError):
        SessionIndex.load(tmp_path / "session-index.json", ECOLOGICAL)
    eco = SessionIndex.create(tmp_path / "eco.json", ECOLOGICAL, "campaign")
    with pytest.raises(SessionIndexError):
        process_session(
            privacy_session(), session_key="dry-run-ses-7f3a91", sidecar=SIDECAR, session_index=eco
        )
    with pytest.raises(SessionIndexError):
        process_session(
            growth_session()[0], session_key="synthetic-growth", sidecar=SIDECAR, session_index=eco
        )
    assert eco.entries == []
    assert SessionIndex.load(tmp_path / "eco.json", ECOLOGICAL).entries == []


def test_a_genuine_looking_key_cannot_enter_a_dry_run_index(tmp_path):
    dry = dry_index(tmp_path)
    with pytest.raises(SessionIndexError):
        process_session(
            growth_session()[0],
            session_key="ses-real-looking",
            sidecar=SIDECAR,
            session_index=dry,
        )


def test_sidecar_is_a_closed_vocabulary(tmp_path):
    dry = dry_index(tmp_path)
    for bad in (
        {"note": "free text"},
        {"task_type": "make it faster please"},
        {"has_tests": "yes"},
    ):
        with pytest.raises(SessionIndexError):
            process_session(
                growth_session()[0], session_key="synthetic-x", sidecar=bad, session_index=dry
            )


def test_incomplete_sessions_are_excluded_with_a_reason_and_still_recorded(tmp_path):
    dry = dry_index(tmp_path)
    records = growth_session()[0]
    out = process_session(
        records[1:], session_key="synthetic-gap", sidecar=SIDECAR, session_index=dry
    )
    assert out.excluded and out.exclusion_reason == "capture_incomplete" and out.l1 is None
    row = dry.entries[0]
    assert row.excluded and not row.derivative_present and not row.complete
    assert row.incomplete_reasons == ["first_record_not_sequence_one"]
    assert dry.usable() == []


def test_withdrawal_is_recorded_not_deleted(tmp_path):
    dry = dry_index(tmp_path)
    process_session(
        growth_session()[0], session_key="synthetic-w", sidecar=SIDECAR, session_index=dry
    )
    assert len(dry.usable()) == 1
    dry.withdraw(1)
    assert dry.usable() == [] and dry.entries[0].withdrawn and len(dry.entries) == 1
    with pytest.raises(SessionIndexError):
        dry.exclude(1, "it looked boring")


def test_public_projection_carries_no_identity_time_or_digest(tmp_path):
    dry = dry_index(tmp_path)
    process_session(
        privacy_session(), session_key="dry-run-ses-7f3a91", sidecar=SIDECAR, session_index=dry
    )
    process_session(
        growth_session()[0], session_key="synthetic-growth", sidecar=SIDECAR, session_index=dry
    )
    public = json.dumps(dry.public_projection())
    for private in (
        "dry-run-ses-7f3a91",
        "synthetic-growth",
        "2030-01-01",
        "session_key",
        "link",
        "captured_at",
    ):
        assert private not in public
    assert set(dry.entries[1].link) == {"raw", "derivative"}  # the session that was analysed
    assert dry.entries[0].link == {}  # the excluded one never got a derivative
    for digest in dry.entries[1].link.values():
        assert digest not in public


def test_stopping_rule_and_natural_absence(tmp_path):
    dry = dry_index(tmp_path)
    process_session(
        growth_session()[0], session_key="synthetic-a", sidecar=SIDECAR, session_index=dry
    )
    status = dry.stopping_status(weeks_elapsed=1)
    assert not status["stop"] and status["usable"] == 1
    assert "S3" in status["naturally_absent"] and "S5" in status["achievable_strata"]
    assert dry.stopping_status(weeks_elapsed=10)["because"] == ["ten calendar weeks"]


def test_a_session_index_is_created_once(tmp_path):
    dry_index(tmp_path)
    with pytest.raises(SessionIndexError):
        dry_index(tmp_path)


# ------------------------------------------------------------------------------ privacy dry run
def planted_fragments():
    """Every planted string, plus its distinctive pieces, so a partial leak is also caught."""
    pieces = set(PLANTED.all())
    for text in PLANTED.all():
        pieces.update(
            t
            for t in text.replace("\\", " ").replace("/", " ").split()
            if len(t) >= PLANTED_TOKEN_MIN
        )
    return sorted(pieces)


def test_the_planted_session_is_seen_by_the_scan_and_excluded(tmp_path):
    dry = dry_index(tmp_path)
    out = process_session(
        privacy_session(), session_key="dry-run-ses-7f3a91", sidecar=SIDECAR, session_index=dry
    )
    assert out.excluded and out.exclusion_reason == "secret_or_identifier_hit"
    assert out.l1 is None and out.stage_reached == "session_index"
    creds = out.scan.credentials
    for name in (
        "secret-pattern-1",
        "secret-pattern-0",
        "github-token",
        "url-credentials",
        "assigned-secret",
    ):
        assert creds.get(name, 0) >= 1, name
    ids = out.scan.identifiers
    for name in ("windows-path", "posix-home-path", "email", "ipv4", "hostname"):
        assert ids.get(name, 0) >= 1, name


def test_no_planted_material_reaches_the_derivative_even_when_the_scan_is_bypassed(tmp_path):
    """Defence in depth: build the derivative anyway and check it against every plant."""
    dry = dry_index(tmp_path)
    out = process_session(
        privacy_session(),
        session_key="dry-run-ses-7f3a91",
        sidecar=SIDECAR,
        session_index=dry,
        force_derivative=True,
        sensitive_terms=("contoso", "jdoe", "Priya Ramanathan"),
    )
    assert out.l1 is not None and out.gate.content_clean, out.gate.violations
    blob = derivative_bytes(out).decode("ascii")
    for planted in planted_fragments():
        assert planted not in blob, planted
    for lowered in (
        "contoso",
        "jdoe",
        "priya",
        "hunter2",
        "whsec",
        "invoice",
        "2030-01-01",
        "synthetic",
    ):
        assert lowered not in blob.lower(), lowered
    assert validate_l1(out.l1) == []
    assert out.excluded  # still excluded from analysis: the bypass never changes the index verdict
    assert not out.gate.publishable  # clean content is necessary, not sufficient
    assert dry.usable() == []


def test_a_secret_the_scanner_cannot_recognise_still_cannot_reach_the_derivative(tmp_path):
    dry = dry_index(tmp_path)
    records = privacy_session(with_blind_spot_only=True)
    scan = scan_raw(records)
    assert not scan.excludes_session  # the scan is blind to it, on purpose
    out = process_session(
        records, session_key="dry-run-ses-blind", sidecar=SIDECAR, session_index=dry
    )
    assert not out.excluded and out.gate.content_clean
    blob = derivative_bytes(out).decode("ascii")
    assert SCANNER_BLIND_SPOT not in blob and "passphrase" not in blob


def test_publication_needs_clean_content_and_a_recorded_approval(tmp_path):
    dry = dry_index(tmp_path)
    out = process_session(
        privacy_session(with_blind_spot_only=True),
        session_key="dry-run-ses-b",
        sidecar=SIDECAR,
        session_index=dry,
    )
    assert out.gate.content_clean and not out.gate.publishable
    approved = gate(out.l1, privacy_session(with_blind_spot_only=True), out.scan, approved=True)
    assert approved.publishable


def test_the_gate_blocks_a_leak_through_each_independent_line():
    records = privacy_session()
    scan = scan_raw(records, ("contoso",))
    from project_context.corpus.f1_analysis import analyse_session as build

    clean = build(records)
    assert gate(clean, records, scan).content_clean

    leaks = {
        "unknown key": lambda d: d["session"].__setitem__("note", "hello"),
        "planted path as a value": lambda d: d["session"].__setitem__(
            "growth_shape", PLANTED.classes["fake_paths"][0]
        ),
        "planted email in declared": lambda d: d["declared"].__setitem__(
            "task_type", PLANTED.classes["fake_emails"][0]
        ),
        "forbidden field name": lambda d: d["session"].__setitem__("content", 1),
        "timestamp": lambda d: d["session"].__setitem__("growth_shape", "2030-01-01T00:00:00Z"),
    }
    for label, mutate in leaks.items():
        broken = json.loads(json.dumps(clean))
        mutate(broken)
        result = gate(broken, records, scan)
        assert not result.content_clean, label


def test_verification_holds_even_if_the_schema_check_is_disabled(monkeypatch):
    """The schema and the raw-material comparison are separate lines of defence."""
    from project_context.corpus import privacy

    records = privacy_session()
    scan = scan_raw(records, ("contoso",))
    clean = analyse_session(records)
    broken = json.loads(json.dumps(clean))
    broken["session"]["growth_shape"] = "contoso-billing invoice_export compute_quarterly_bonus"
    monkeypatch.setattr(privacy, "validate_l1", lambda _l1: [])
    result = privacy.gate(broken, records, scan)
    assert not result.content_clean
    assert any("raw" in v for v in result.violations)


def test_scan_and_gate_reports_never_carry_matched_text():
    records = privacy_session()
    scan = scan_raw(records, ("contoso",))
    shown = json.dumps(scan.to_dict()) + repr(scan)
    for planted in PLANTED.all():
        assert planted not in shown
    result = gate(analyse_session(records), records, scan)
    assert not any(p in " ".join(result.violations) for p in PLANTED.all())


def test_the_derivative_is_deterministic():
    records = privacy_session(with_blind_spot_only=True)
    assert dumps(analyse_session(records)) == dumps(
        analyse_session(json.loads(json.dumps(records)))
    )


def test_stage_names_are_the_documented_pipeline():
    assert f1_pipeline.STAGES == (
        "local_validation",
        "privacy_scan",
        "structural_extraction",
        "reconciliation",
        "publication_gate",
        "shape_cards",
        "session_index",
    )


def test_the_preregistration_states_the_same_routing_values_as_the_code():
    from pathlib import Path

    text = Path("experiments/preregistrations/F1-ecological-corpus.md").read_text(encoding="utf-8")
    assert text.count("**10%**") == 2 and "**60%**" in text and "**50%**" in text
    assert "not empirical thresholds" in text
    for word in ("activation threshold", "effect threshold", "success criterion", "borderline"):
        assert word in text
    assert "Decision triggers" not in text


# ------------------------------------------------------------------------------ calibration
def test_a_calibration_session_can_use_only_the_calibration_index(tmp_path):
    from project_context.corpus.session_index import CALIBRATION, SessionIndex, SessionIndexError

    records = growth_session()[0]
    calibration = SessionIndex.create(tmp_path / "cal.json", CALIBRATION, "cal")
    out = process_session(
        records, session_key="calibration-01", sidecar=SIDECAR, session_index=calibration
    )
    assert out.session_ordinal == 1 and calibration.kind == CALIBRATION
    eco = SessionIndex.create(tmp_path / "eco.json", ECOLOGICAL, "campaign")
    with pytest.raises(SessionIndexError):
        process_session(records, session_key="calibration-02", sidecar=SIDECAR, session_index=eco)
    dry = SessionIndex.create(tmp_path / "dry.json", DRY_RUN, "dry")
    with pytest.raises(SessionIndexError):
        process_session(records, session_key="calibration-03", sidecar=SIDECAR, session_index=dry)
    with pytest.raises(SessionIndexError):
        SessionIndex.load(tmp_path / "cal.json", ECOLOGICAL)
    assert eco.entries == [] and dry.entries == []


def test_the_registry_refuses_a_session_whatever_key_it_arrives_under(tmp_path):
    from project_context.corpus.session_index import SessionIndex, SessionIndexError

    records = growth_session()[0]
    eco = SessionIndex.create(tmp_path / "eco.json", ECOLOGICAL, "campaign")
    with pytest.raises(SessionIndexError):
        process_session(
            records,
            session_key="ses-genuine-looking",
            sidecar=SIDECAR,
            session_index=eco,
            refuse_session_ids=frozenset({records[0]["session_id"]}),
        )
    assert eco.entries == []


def test_t3_reports_three_bases_and_names_the_one_near_the_line():
    def sessions(measured, bytes_est, words):
        return [
            sess(
                window_fraction_max_measured=m,
                window_fraction_max_bytes_estimate=b_,
                window_fraction_max_word_estimate=w,
            )
            for m, b_, w in zip(measured, bytes_est, words)
        ]

    # The second-highest session is what counts, so a single high session is not enough.
    data = sessions([0.90, 0.20, 0.10], [0.95, 0.20, 0.10], [0.60, 0.10, 0.05])
    r = by_name(routing.evaluate(data, [False] * 3))["T3_externalise_recall"]
    assert r.basis == "measured" and r.status == routing.NOT_TRIGGERED
    assert set(r.other_bases) == {"bytes_estimate", "word_estimate"}
    assert r.observed_value == 0.20 and r.band == "clear" and r.borderline_bases == []


def test_t3_prefers_the_measured_basis_and_falls_back_when_usage_is_missing():
    measured = [0.7, 0.65, 0.2]
    est = [0.5, 0.4, 0.1]
    both = [
        sess(
            window_fraction_max_measured=m,
            window_fraction_max_bytes_estimate=e,
            window_fraction_max_word_estimate=e / 2,
        )
        for m, e in zip(measured, est)
    ]
    r = by_name(routing.evaluate(both, [False] * 3))["T3_externalise_recall"]
    assert r.basis == "measured" and r.status == routing.TRIGGERED
    assert r.other_bases["bytes_estimate"]["status"] == routing.NOT_TRIGGERED  # disagreement kept
    none_measured = [dict(s, window_fraction_max_measured=UNOBSERVED) for s in both]
    r = by_name(routing.evaluate(none_measured, [False] * 3))["T3_externalise_recall"]
    assert (
        r.basis == "bytes_estimate" and r.other_bases["measured"]["status"] == routing.NOT_EVALUABLE
    )


def test_a_borderline_t3_names_which_estimate_put_it_there():
    data = [
        sess(
            window_fraction_max_measured=UNOBSERVED,
            window_fraction_max_bytes_estimate=v,
            window_fraction_max_word_estimate=v * 0.6,
        )
        for v in (0.58, 0.20, 0.10)
    ]
    r = by_name(routing.evaluate(data, [False] * 3))["T3_externalise_recall"]
    assert r.status == routing.NOT_TRIGGERED
    assert r.observed_value == 0.20 and r.borderline_bases == []  # second-highest is far below
    near = [dict(s, window_fraction_max_bytes_estimate=v) for s, v in zip(data, (0.9, 0.55, 0.1))]
    r = by_name(routing.evaluate(near, [False] * 3))["T3_externalise_recall"]
    assert r.band == "borderline" and r.borderline_bases == ["bytes_estimate"]
