"""Stage 4 behavioural tests. Everything offline via FakeReader and
canned transports. No test spends money or touches the network."""

import json
from pathlib import Path

import pytest

from project_context.behavior.bundles import (
    render_from_trace,
    render_visible,
)
from project_context.behavior.fixtures import (
    load_behavior_set,
    load_interventions,
    load_manifest,
    load_task,
)
from project_context.behavior.parse import parse_action
from project_context.behavior.prompt import (
    SYSTEM_TEXT,
)
from project_context.behavior.runner import (
    BundleSource,
    build_derived,
    build_reader_request,
    build_schedule,
    transfer_schedule,
)
from project_context.behavior.tasks import FAMILIES, grade
from project_context.readers.domain import ReaderRequest
from project_context.readers.fake import FakeProviderError, FakeReader
from project_context.readers.openai_chat import OpenAIChatAdapter, OpenAIChatConfig

ROOT = Path("fixtures") / "compiler-behavior-v1"
COMPILER_ROOT = Path("fixtures") / "compiler-v1"
SOURCE_RUN = Path(".local/runs/compiler-v1/run-001")

_RULES = {
    "qualification-trap": '{"action": "HOLD", "target": "migration", '
    '"value": null, "reason_code": "tenant-pending"}',
    "stale-cheap": '{"action": "PROCEED", "target": null, '
    '"value": null, "reason_code": "validated-current"}',
    "wrong-scope": '{"action": "USE_A", "target": "project-a", '
    '"value": null, "reason_code": "in-scope"}',
    "dependency-trap": '{"action": "WITH_TOOL", "target": null, '
    '"value": null, "reason_code": "resolver-present"}',
    "heterogeneous-basic": '{"action": "REFUSE", "target": null, '
    '"value": null, "reason_code": "constraint-present"}',
    "calibration-echo": '{"action": "ECHO", "target": null, '
    '"value": "mig-7Q2", "reason_code": "stated-in-task"}',
}

_HOLD_OK = '{"action": "HOLD", "target": null}'
_HOLD_RC = '{"action": "HOLD", "reason_code": "x"}'

_HOLD_TRUTH = {"correct_action": "HOLD", "harmful_actions": ["RELEASE"]}
_USE_A_TRUTH = {"correct_action": "USE_A", "harmful_actions": ["USE_B"]}
_REFUSE_TRUTH = {"correct_action": "REFUSE", "harmful_actions": ["PROCEED"]}


def _manifest():
    return load_manifest(ROOT / "manifest.json")


def _behavior_set():
    return load_behavior_set(ROOT)


def test_manifest_records_preregistration():
    manifest = _manifest()
    assert manifest["behavior_version"] == "1"
    assert manifest["primary_budget"] == "tight"
    assert manifest["schedule_seed"] == 20260923
    assert manifest["readers"]["primary"]["model"] == "mistral-small:latest"
    assert manifest["readers"]["transfer"]["model"] == "llama3.1:8b"
    assert manifest["max_calls"] == 80
    assert set(manifest["eligible_fixtures"]) == {
        "qualification-trap",
        "stale-cheap",
        "wrong-scope",
        "dependency-trap",
        "heterogeneous-basic",
        "calibration-echo",
    }


def test_task_files_carry_no_evaluator_truth():
    forbidden = (
        "eval_class",
        "oracle_minimum",
        "decisive_item",
        "expected_action",
        "harmful_action",
        "MUST",
        "SHOULD",
        "DISTRACTOR",
        "HARMFUL",
    )
    for name, paths in _behavior_set().items():
        blob = paths["task"].read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in blob, f"{name}: {token}"


def test_reader_payloads_carry_no_truth():
    from project_context.behavior.runner import STRATEGY_OF
    from project_context.compiler.fixtures import load_candidate_file

    behavior_set = _behavior_set()
    source = BundleSource(SOURCE_RUN, COMPILER_ROOT)
    forbidden = (
        "eval_class",
        "oracle_minimum",
        "decisive_item",
        "expected_action",
        "harmful_action",
    )
    for name in ("qualification-trap", "heterogeneous-basic"):
        task = load_task(behavior_set[name]["task"])
        bundle, _ = source.bundle_for(name, "tight", "staged")
        request = build_reader_request(
            case_id="probe",
            task=task,
            context_text=render_visible(bundle),
            temperature=0.0,
            seed=1,
            max_tokens=512,
        )
        payload = request.system_text + request.task_text + request.context_text
        for token in forbidden:
            assert token not in payload, f"{name}: {token}"
    _ = STRATEGY_OF
    _ = load_candidate_file


def test_frozen_bundle_digest_verification():
    source = BundleSource(SOURCE_RUN, COMPILER_ROOT)
    bundle, record = source.bundle_for("stale-cheap", "tight", "staged")
    assert bundle.content_hash() == record["bundle_hash"]
    assert bundle.id == record["bundle_id"]
    assert sorted(i.id for i in bundle.items) == [
        "fresh-full",
        "instr-1",
        "taskreq-1",
    ]


def test_digest_mismatch_stops_condition(tmp_path):
    import shutil

    tampered = tmp_path / "run-tampered"
    shutil.copytree(SOURCE_RUN, tampered)
    lines = (tampered / "compilation.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["bundle_hash"] = "0" * 64
    lines[0] = json.dumps(first, sort_keys=True)
    (tampered / "compilation.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    tampered_source = BundleSource(tampered, COMPILER_ROOT)
    with pytest.raises(ValueError, match="digest mismatch"):
        tampered_source.bundle_for(first["fixture"], first["budget"], first["strategy"])


def test_b0_empty_context_wrapper():
    request = build_reader_request(
        case_id="x",
        task={"prompt": "Do it.", "actions": ["ECHO", "ABSTAIN"]},
        context_text="",
        temperature=0.0,
        seed=1,
        max_tokens=64,
    )
    assert "(no project context supplied)" in request.context_text
    assert request.system_text == SYSTEM_TEXT


def test_reader_request_determinism():
    kwargs = dict(
        case_id="c",
        task={"prompt": "P", "actions": ["ECHO", "ABSTAIN"]},
        context_text="ctx",
        temperature=0.0,
        seed=7,
        max_tokens=64,
    )
    assert build_reader_request(**kwargs).to_dict() == build_reader_request(**kwargs).to_dict()


def test_fake_reader_behaviors():
    fake = FakeReader(
        rules=[
            ("good", {"ok": _RULES["qualification-trap"]}),
            ("bad", {"malformed": "not json at all"}),
            ("down", {"error": "boom"}),
        ]
    )
    base = dict(
        system_text="s",
        task_text="t",
        context_text="c",
        schema_text="{}",
        temperature=0.0,
        seed=1,
        max_tokens=64,
    )
    ok = fake.invoke(ReaderRequest(case_id="good-1", **base))
    assert json.loads(ok.raw_text)["action"] == "HOLD"
    malformed = fake.invoke(ReaderRequest(case_id="bad-1", **base))
    assert malformed.raw_text == "not json at all"
    with pytest.raises(FakeProviderError):
        fake.invoke(ReaderRequest(case_id="down-1", **base))
    assert fake.calls == ["good-1", "bad-1", "down-1"]


def test_parser_success_and_failures():
    action, status = parse_action('{"action": "HOLD"}', ["HOLD", "RELEASE"])
    assert status == "ok" and action.action == "HOLD"
    action, status = parse_action(' fields {"action": "X", "target": "t"} trailing', ["X"])
    assert status == "ok" and action.target == "t"
    for bad in ("no braces", '{"action": "NOPE"}', '{"action": 5}', "[1,2]", "{unbalanced"):
        _, status = parse_action(bad, ["HOLD"])
        assert status == "parse-failure", bad


def test_graders_all_families():
    assert FAMILIES == (
        "choose_evidence",
        "constraint",
        "echo",
        "hold_release",
        "materialise",
        "use_current",
    )
    from project_context.behavior.parse import ParsedAction

    def act(name, value=None):
        return ParsedAction(action=name, target=None, value=value, reason_code=None)

    assert grade("hold_release", act("HOLD"), _HOLD_TRUTH)[0:2] == (1.0, False)
    assert grade("hold_release", act("RELEASE"), _HOLD_TRUTH)[0:2] == (0.0, True)
    assert grade("use_current", act("PROCEED"), {"correct_action": "PROCEED"})[0] == 1.0
    assert grade("choose_evidence", act("USE_B"), _USE_A_TRUTH)[0:2] == (0.0, True)
    assert grade("materialise", act("WITHOUT_TOOL"), {})[0] == 0.5
    assert grade("constraint", act("PROCEED"), _REFUSE_TRUTH)[0:2] == (0.0, True)
    assert grade("echo", act("ECHO", "mig-7Q2"), {"expected_value": "mig-7Q2"})[0] == 1.0
    assert grade("echo", act("ECHO", "wrong"), {"expected_value": "mig-7Q2"})[0] == 0.0
    assert grade("hold_release", None, {})[0:2] == (0.0, False)


def test_derived_bundle_identities():
    source = BundleSource(SOURCE_RUN, COMPILER_ROOT)
    staged, _ = source.bundle_for("qualification-trap", "tight", "staged")
    interventions = load_interventions(_behavior_set()["qualification-trap"]["interventions"])
    ma, removed, added = build_derived(
        staged_bundle=staged, interventions=interventions, intervention_id="MA"
    )
    assert removed == ["exception-tenant"] and added == []
    assert ma.id == staged.id + "::MA"
    assert "exception-tenant" not in [i.id for i in ma.items]
    assert "claim-positive" in [i.id for i in ma.items]
    mr, _, _ = build_derived(
        staged_bundle=staged, interventions=interventions, intervention_id="MR"
    )
    assert mr.content_hash() == staged.content_hash()
    assert [i.id for i in mr.items] == [i.id for i in staged.items]
    assert mr.id == staged.id + "::MR"
    mt, _, mt_added = build_derived(
        staged_bundle=staged, interventions=interventions, intervention_id="MT"
    )
    assert mt_added == ["mt-distract-2"]
    assert "exception-tenant" not in [i.id for i in mt.items]
    mw, _, mw_added = build_derived(
        staged_bundle=staged, interventions=interventions, intervention_id="MW"
    )
    assert mw_added == ["wrong-tenant-cleared"]
    assert any("cleared for release" in i.content for i in mw.items)


def test_mt_volume_recorded():
    source = BundleSource(SOURCE_RUN, COMPILER_ROOT)
    staged, _ = source.bundle_for("qualification-trap", "tight", "staged")
    interventions = load_interventions(_behavior_set()["qualification-trap"]["interventions"])
    ma, _, _ = build_derived(
        staged_bundle=staged, interventions=interventions, intervention_id="MA"
    )
    mt, _, _ = build_derived(
        staged_bundle=staged, interventions=interventions, intervention_id="MT"
    )
    from project_context.behavior.bundles import bundle_render_tokens
    from project_context.compiler.domain import ContextRequest

    request = ContextRequest(
        request_id="x",
        task_id="x",
        usable_token_budget=10**9,
        created_at="2026-09-23T00:00:00Z",
        active_scope="x",
    )
    assert bundle_render_tokens(mt, request) != bundle_render_tokens(ma, request)


def test_render_from_trace_reproduces_run001():
    from project_context.compiler.domain import ContextRequest
    from project_context.compiler.fixtures import load_candidate_file, load_request_file

    source = BundleSource(SOURCE_RUN, COMPILER_ROOT)
    bundle, record = source.bundle_for("wrong-scope", "tight", "gated")
    candidates = load_candidate_file(COMPILER_ROOT / "wrong-scope.candidates.json")
    base = load_request_file(COMPILER_ROOT / "wrong-scope.request.json")
    request = ContextRequest(
        request_id=base.request_id + "-tight",
        task_id=base.task_id,
        usable_token_budget=500,
        created_at=base.created_at,
        active_scope=base.active_scope,
        required_ids=base.required_ids,
        policy_version=base.policy_version,
    )
    admitted = [
        e["candidate_id"] for e in record["trace"]["entries"] if e["decision"] == "ADMITTED"
    ]
    rebuilt = render_from_trace(admitted, candidates, request)
    assert rebuilt.to_dict() == bundle.to_dict()


def test_schedule_determinism():
    manifest = load_manifest(ROOT / "manifest.json")
    first = build_schedule(manifest, 20260923, reader="primary")
    second = build_schedule(manifest, 20260923, reader="primary")
    assert [c["case_id"] for c in first] == [c["case_id"] for c in second]
    assert len(first) == 54
    # Ladder portion is fixture-major (interleaved by fixture); repeats append.
    ladder = first[:46]
    fixtures_in_order = [c["fixture"] for c in ladder]
    assert fixtures_in_order == sorted(fixtures_in_order)
    third = build_schedule(manifest, 999, reader="primary")
    assert [c["case_id"] for c in first] != [c["case_id"] for c in third]


def test_transfer_schedule_minimal():

    manifest = load_manifest(ROOT / "manifest.json")
    wave = transfer_schedule(manifest, reader="transfer")
    assert len(wave) == 7
    assert {c["fixture"] for c in wave} == {"heterogeneous-basic"}
    assert {c["budget"] for c in wave} == {"medium"}


def test_openai_adapter_units():

    def transport_ok(method, url, headers, body):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer sekrit"
        payload = json.loads(body.decode("utf-8"))
        assert payload["temperature"] == 0.0
        assert payload["response_format"] == {"type": "json_object"}
        return 200, json.dumps(
            {
                "model": "m",
                "choices": [{"message": {"content": '{"action": "HOLD"}'}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 5},
            }
        ).encode()

    adapter = OpenAIChatAdapter(
        OpenAIChatConfig(base_url="http://x", model="m", api_key="sekrit"),
        transport=transport_ok,
    )
    request = ReaderRequest(
        case_id="c",
        system_text="s",
        task_text="t",
        context_text="c",
        schema_text="{}",
        temperature=0.0,
        seed=1,
        max_tokens=64,
    )
    response = adapter.invoke(request)
    assert json.loads(response.raw_text)["action"] == "HOLD"
    assert response.input_tokens.value == 50
    assert response.output_tokens.value == 5
    assert response.input_tokens.source == "provider"
    described = json.dumps(adapter.describe())
    assert "sekrit" not in described

    def transport_bare(method, url, headers, body):
        return 200, json.dumps(
            {
                "model": "m",
                "choices": [{"message": {"content": "{}"}}],
            }
        ).encode()

    bare = OpenAIChatAdapter(
        OpenAIChatConfig(base_url="http://x", model="m"), transport=transport_bare
    )
    response = bare.invoke(request)
    assert response.input_tokens.value is None
    assert response.reasoning_tokens is None or response.reasoning_tokens.value is None

    def transport_500(method, url, headers, body):
        return 500, b"oops"

    from project_context.readers.domain import ReaderTransportError

    failing = OpenAIChatAdapter(
        OpenAIChatConfig(base_url="http://x", model="m"), transport=transport_500
    )
    with pytest.raises(ReaderTransportError):
        failing.invoke(request)


def test_retry_policy():
    from project_context.behavior.runner import invoke_with_retry
    from project_context.readers.domain import ReaderTransportError

    calls = {"n": 0}

    class Flaky:
        def invoke(self, request):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ReaderTransportError("down")
            return "fine"

    response, attempts = invoke_with_retry(Flaky(), object(), backoff=(0, 0))
    assert (response, attempts) == ("fine", 3)

    class Dead:
        def invoke(self, request):
            raise ReaderTransportError("down")

    with pytest.raises(ReaderTransportError):
        invoke_with_retry(Dead(), object(), backoff=(0, 0))


def test_full_fake_suite_offline(tmp_path):
    from project_context.behavior.runner import BundleSource as BS
    from project_context.behavior.runner import run_suite

    manifest = load_manifest(ROOT / "manifest.json")
    source = BS(SOURCE_RUN, COMPILER_ROOT)
    fake = FakeReader(rules=[(name, {"ok": text}) for name, text in _RULES.items()])
    from project_context.behavior.runner import build_schedule

    schedule = build_schedule(manifest, manifest["schedule_seed"], reader="fake")
    run_dir = run_suite(
        behavior_root=ROOT,
        source=source,
        adapter=fake,
        reader_name="fake",
        temperature=0.0,
        seed=manifest["decoding"]["seed"],
        max_tokens=512,
        schedule=schedule,
        max_calls=1000,
        run_id="fake-e2e",
        timestamp="2026-09-23T00:00:00Z",
        git_commit="test",
        vcs_dirty=False,
        out_root=tmp_path,
    )
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "behavior.jsonl").is_file()
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    assert results["completed"] == len(schedule) == 54
    assert fake.calls and len(fake.calls) == 54
    # Every feasible case scored; scripted correct actions pass grading.
    observations = [
        json.loads(line)
        for line in (run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_case: dict[str, list] = {}
    for obs in observations:
        by_case.setdefault(obs["target_id"], []).append(obs)
    passing = sum(
        1
        for obs in observations
        if obs["metric"].endswith(":task_score") and obs["verdict"] == "PASS"
    )
    assert passing > 40, passing


def test_spend_guard_refuses():
    from project_context.behavior.runner import build_schedule, run_suite

    manifest = load_manifest(ROOT / "manifest.json")
    schedule = build_schedule(manifest, manifest["schedule_seed"], reader="fake")
    with pytest.raises(ValueError, match="spend guard"):
        run_suite(
            behavior_root=ROOT,
            source=BundleSource(SOURCE_RUN, COMPILER_ROOT),
            adapter=FakeReader(),
            reader_name="fake",
            temperature=0.0,
            seed=1,
            max_tokens=64,
            schedule=schedule,
            max_calls=3,
            run_id="x",
            timestamp="2026-09-23T00:00:00Z",
            git_commit="test",
            vcs_dirty=False,
            out_root=Path("nope"),
        )


def test_resume_skips_completed(tmp_path):
    from project_context.behavior.runner import build_schedule, run_suite

    manifest = load_manifest(ROOT / "manifest.json")
    schedule = build_schedule(manifest, manifest["schedule_seed"], reader="fake")[:4]
    fake = FakeReader()
    kwargs = dict(
        behavior_root=ROOT,
        source=BundleSource(SOURCE_RUN, COMPILER_ROOT),
        adapter=fake,
        reader_name="fake",
        temperature=0.0,
        seed=1,
        max_tokens=64,
        schedule=schedule,
        timestamp="2026-09-23T00:00:00Z",
        git_commit="test",
        vcs_dirty=False,
        out_root=tmp_path,
    )
    run_suite(run_id="r1", max_calls=1000, **kwargs)
    assert len(fake.calls) == 4
    run_suite(run_id="r1", max_calls=1000, resume=True, **kwargs)
    assert len(fake.calls) == 4


def test_invocation_linkage_and_none_telemetry(tmp_path):
    from project_context.behavior.runner import build_schedule, run_suite

    manifest = load_manifest(ROOT / "manifest.json")
    schedule = build_schedule(manifest, manifest["schedule_seed"], reader="fake")[:2]
    run_dir = run_suite(
        behavior_root=ROOT,
        source=BundleSource(SOURCE_RUN, COMPILER_ROOT),
        adapter=FakeReader(),
        reader_name="fake",
        temperature=0.0,
        seed=1,
        max_tokens=64,
        schedule=schedule,
        max_calls=1000,
        run_id="link",
        timestamp="2026-09-23T00:00:00Z",
        git_commit="test",
        vcs_dirty=False,
        out_root=tmp_path,
    )
    invocations = [
        json.loads(line)
        for line in (run_dir / "invocations.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    behaviors = [
        json.loads(line)
        for line in (run_dir / "behavior.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(invocations) == 2 and len(behaviors) == 2
    for inv in invocations:
        assert inv["observation_only"] is False
        assert inv["cost_usd"] is None and inv["cost_schedule_id"] is None
        assert inv["reasoning_tokens"] is None
    for beh in behaviors:
        record = beh["record"]
        assert record["invocation_id"] in {i["id"] for i in invocations}
        assert "raw_text" in beh and beh["source_bundle_hash"]


def test_no_cross_reader_averaging_in_results(tmp_path):
    from project_context.behavior.runner import build_schedule, run_suite

    manifest = load_manifest(ROOT / "manifest.json")
    schedule = build_schedule(manifest, manifest["schedule_seed"], reader="fake")[:2]
    run_dir = run_suite(
        behavior_root=ROOT,
        source=BundleSource(SOURCE_RUN, COMPILER_ROOT),
        adapter=FakeReader(),
        reader_name="fake",
        temperature=0.0,
        seed=1,
        max_tokens=64,
        schedule=schedule,
        max_calls=1000,
        run_id="avg",
        timestamp="2026-09-23T00:00:00Z",
        git_commit="test",
        vcs_dirty=False,
        out_root=tmp_path,
    )
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    assert results["reader"] == "fake"
    assert "cases" in results and "completed" in results


def test_records_round_trip():
    from project_context.behavior.domain import BehaviorRecord

    record = BehaviorRecord(
        id="b",
        experiment_case_id="c",
        fixture_id="f",
        condition_id="B5",
        repeat_index=0,
        source_bundle_id="s",
        source_bundle_digest="d",
        parent_bundle_id=None,
        intervention_id=None,
        removed_ids=(),
        added_ids=(),
        invocation_id="i",
        parse_status="ok",
        parsed_action={"action": "HOLD"},
        raw_response_digest="r",
        prompt_version="behavior-prompt-v1",
        parser_version="action-parser-v1",
        grader_version="hold-release-v1",
    )
    assert BehaviorRecord.from_dict(record.to_dict()) == record
    request = ReaderRequest(
        case_id="c",
        system_text="s",
        task_text="t",
        context_text="c",
        schema_text="{}",
        temperature=0.0,
        seed=1,
        max_tokens=64,
    )
    from project_context.readers.domain import ReaderRequest as RR

    assert RR.from_dict(request.to_dict()) == request


def test_intervention_provenance_fields():
    from project_context.behavior.runner import build_derived

    source = BundleSource(SOURCE_RUN, COMPILER_ROOT)
    staged, _ = source.bundle_for("qualification-trap", "tight", "staged")
    interventions = load_interventions(
        load_behavior_set(ROOT)["qualification-trap"]["interventions"]
    )
    ma, removed, added = build_derived(
        staged_bundle=staged, interventions=interventions, intervention_id="MA"
    )
    assert removed == ["exception-tenant"] and added == []
    assert ma.id == staged.id + "::MA"
    mt, _, mt_added = build_derived(
        staged_bundle=staged, interventions=interventions, intervention_id="MT"
    )
    assert mt_added == ["mt-distract-2"]
    mw, _, mw_added = build_derived(
        staged_bundle=staged, interventions=interventions, intervention_id="MW"
    )
    assert mw_added == ["wrong-tenant-cleared"]


def test_cli_behavior_smoke(capsys):
    from project_context.cli.main import main as cli_main

    assert cli_main(["behavior", "fixtures"]) == 0
    assert "qualification-trap" in capsys.readouterr().out
    assert cli_main(["behavior", "inspect", "stale-cheap", "--condition", "B5"]) == 0
    assert cli_main(["behavior", "inspect", "nope"]) == 2
    assert cli_main(["behavior", "plan"]) == 0
    out = capsys.readouterr().out
    assert "54 cases" in out
    assert cli_main(["behavior", "dry-run", "--reader", "fake"]) == 0


def test_cli_validate_run_on_fake_suite(tmp_path):
    from project_context.behavior.runner import build_schedule, run_suite
    from project_context.cli.main import main as cli_main

    manifest = load_manifest(ROOT / "manifest.json")
    schedule = build_schedule(manifest, manifest["schedule_seed"], reader="fake")[:3]
    run_dir = run_suite(
        behavior_root=ROOT,
        source=BundleSource(SOURCE_RUN, COMPILER_ROOT),
        adapter=FakeReader(),
        reader_name="fake",
        temperature=0.0,
        seed=1,
        max_tokens=64,
        schedule=schedule,
        max_calls=1000,
        run_id="val",
        timestamp="2026-09-23T00:00:00Z",
        git_commit="test",
        vcs_dirty=False,
        out_root=tmp_path,
    )
    assert cli_main(["behavior", "validate-run", str(run_dir)]) == 0
    assert cli_main(["behavior", "validate-run", str(tmp_path / "missing")]) == 3
