"""Stage 6C adapter tests: ordinary candidates, no privilege, compatibility.

Nothing here calls models or network. Oracle truth files are loaded only
to assert outcomes; adapter and compiler runtime code never reads them.
"""

import ast
import json
import re
from pathlib import Path

from project_context.activation.engine import activate
from project_context.activation.model import ActivationPolicy, ActivationRequest
from project_context.cli.main import main as cli_main
from project_context.compiler.domain import ContextRequest, RequirementClass
from project_context.compiler.engine import compile_context
from project_context.compiler.fixtures import load_candidate_file
from project_context.compiler.policy import CompilerPolicy
from project_context.ledger.projection import project
from project_context.ledger.store import load_events
from project_context.ledger_adapter.adapter import (
    ADAPTER_RELEVANCE,
    LedgerAdapterReceipt,
    adapt,
    adapt_case,
)

SUITE = Path("fixtures") / "adapter-v1" / "cases"
TYPED = ActivationPolicy()
POLICY = CompilerPolicy.from_dict(
    json.loads(
        (Path("experiments") / "compiler-v1" / "policies" / "compiler-policy-v1.json").read_text(
            encoding="utf-8"
        )
    )
)


def _load_case(name):
    case_dir = SUITE / name
    state = project(load_events(case_dir / "events.jsonl"))
    request = ActivationRequest.from_dict(
        json.loads((case_dir / "request.json").read_text(encoding="utf-8"))
    )
    activation = activate(state, request, TYPED)
    ordinary = load_candidate_file(case_dir / "ordinary.candidates.json")
    compile_request = ContextRequest.from_dict(
        json.loads((case_dir / "compile.json").read_text(encoding="utf-8"))
    )
    truth = json.loads((case_dir / "truth.json").read_text(encoding="utf-8"))
    return state, activation, ordinary, compile_request, truth


def _compile_case(name):
    state, activation, ordinary, compile_request, truth = _load_case(name)
    pool, receipts = adapt_case(state, activation, ordinary)
    output = compile_context(compile_request, list(pool), POLICY)
    return state, activation, pool, receipts, output, truth


def _by_source_ref(pool, item_id):
    matches = [c for c in pool if c.source_ref == item_id]
    assert len(matches) == 1, item_id
    return matches[0]


# --- conversion -----------------------------------------------------------------------------------


def test_active_item_becomes_exactly_one_candidate():
    state, activation, _, _, _ = _load_case("a-admitted")
    candidates, receipts = adapt(state, activation)
    assert len(candidates) == 2
    assert {c.source_ref for c in candidates} == {"obligation-002", "verification-004"}
    assert len(receipts) == 2
    for receipt in receipts:
        assert receipt.candidate_id is not None
        assert receipt.activation_state == "active"


def test_non_active_decisions_produce_receipts_without_candidates():
    from project_context.activation.model import ActivationResult

    state, activation, _, _, _ = _load_case("a-admitted")
    dormant = activation.decision_for("obligation-002")
    forged = ActivationResult(
        request_id=activation.request_id,
        policy_id=activation.policy_id,
        decisions=(
            dormant,
            type(dormant)(
                item_id="verification-004",
                state=__import__(
                    "project_context.activation.model", fromlist=["ActivationState"]
                ).ActivationState.DORMANT,
                reason_codes=("no_activation_reason",),
                matched_scope={},
                matched_dependencies=(),
                request_features_used=(),
                epistemic=None,
                policy_id=activation.policy_id,
            ),
        ),
    )
    candidates, receipts = adapt(state, forged)
    assert [c.source_ref for c in candidates] == ["obligation-002"]
    by_id = {r.item_id: r for r in receipts}
    assert by_id["verification-004"].candidate_id is None
    assert by_id["verification-004"].mapped_requirement is None


def test_adapter_consumes_activation_without_recomputing_it():
    # The adapter signature takes state + activation; it calls no
    # activation engine entry point.
    import project_context.ledger_adapter.adapter as adapter_mod

    text = Path(adapter_mod.__file__).read_text(encoding="utf-8")
    assert "project_context.activation.engine" not in text
    assert "activate(" not in text.replace("adapt_case(", "").replace("def adapt(", "")


# --- metadata preservation --------------------------------------------------------


def test_authority_mapping_is_correct():
    _, _, pool, receipts, _, _ = _compile_case("d-authority-not-source")
    by_id = {r.item_id: r for r in receipts}
    assert by_id["constraint-001"].mapped_requirement == "PREFERRED"
    assert by_id["note-002"].mapped_requirement == "DISCRETIONARY"
    user_candidate = _by_source_ref(pool, "constraint-001")
    assert user_candidate.requirement is RequirementClass.PREFERRED
    assert user_candidate.authority_reason.startswith("user-derived")
    agent_candidate = _by_source_ref(pool, "note-002")
    assert agent_candidate.requirement is RequirementClass.DISCRETIONARY
    assert "never user/project authority" in agent_candidate.authority_reason


def test_agent_state_cannot_acquire_user_authority():
    _, _, pool, _, _, _ = _compile_case("e-epistemic-survives")
    claim = _by_source_ref(pool, "claim-001")
    assert claim.requirement is RequirementClass.DISCRETIONARY
    assert "user" not in claim.authority_reason or "never user" in claim.authority_reason


def test_project_authority_survives_mapping():
    from project_context.activation.model import ActivationResult
    from project_context.ledger import events as E
    from project_context.ledger import records as R

    item = {
        "schema_version": R.LEDGER_ITEM_SCHEMA,
        "item_id": "d1",
        "kind": "decision",
        "statement": "project canonical choice",
        "authority": "project",
        "scope": {"component": "schema"},
        "source": {},
    }
    created = E.LedgerEvent.from_dict(
        {
            "schema_version": E.LEDGER_EVENT_SCHEMA,
            "event_id": "e1",
            "event": "item_created",
            "item_id": "d1",
            "recorded_at": "2026-09-24T10:00:00Z",
            "item": item,
        }
    )
    state = project([created])
    decision = M_Decision(
        "d1",
        ("scope_component_match",),
        {"components": ["schema"]},
    )
    activation = ActivationResult(
        request_id="q", policy_id="activation-policy-v1", decisions=(decision,)
    )
    candidates, _ = adapt(state, activation)
    assert candidates[0].requirement is RequirementClass.PREFERRED
    assert candidates[0].authority_reason == "project standing"


def M_Decision(item_id, reasons, matched_scope):
    from project_context.activation.model import ActivationDecision, ActivationState

    return ActivationDecision(
        item_id=item_id,
        state=ActivationState.ACTIVE,
        reason_codes=tuple(sorted(reasons)),
        matched_scope=dict(matched_scope),
        matched_dependencies=(),
        request_features_used=("components",),
        epistemic=None,
        policy_id="activation-policy-v1",
    )


def test_tool_evidence_remains_evidence():
    _, _, pool, _, _, _ = _compile_case("f-multiple")
    result = _by_source_ref(pool, "result-001")
    assert result.order_role == "evidence"
    assert result.requirement is RequirementClass.DISCRETIONARY
    assert "never directive" in result.authority_reason


def test_epistemic_state_survives_adaptation():
    _, _, pool, _, output, _ = _compile_case("e-epistemic-survives")
    claim = _by_source_ref(pool, "claim-001")
    assert claim.kind == "pending_verification"
    assert claim.content.startswith("[Pending verification] ")
    assert "unverified" in claim.freshness_reason
    admitted_ids = [item.id for item in output.bundle.items]
    assert claim.candidate_id in admitted_ids
    rendered = [item.content for item in output.bundle.items if item.id == claim.candidate_id]
    assert rendered[0].startswith("[Pending verification] ")


def test_scope_survives_adaptation():
    _, _, pool, _, _, _ = _compile_case("d-authority-not-source")
    constraint = _by_source_ref(pool, "constraint-001")
    assert "migrations" in constraint.scope_reason
    assert "db/migrations/017" in constraint.scope_reason


def test_provenance_survives_adaptation():
    _, _, pool, receipts, _, _ = _compile_case("a-admitted")
    ledger_pool = [c for c in pool if c.source_kind == "ledger"]
    assert {c.source_ref for c in ledger_pool} == {"obligation-002", "verification-004"}
    by_id = {r.item_id: r for r in receipts}
    assert (
        by_id["obligation-002"].candidate_id == _by_source_ref(pool, "obligation-002").candidate_id
    )
    assert by_id["obligation-002"].scope["component"] == "compat"


def test_receipts_round_trip():
    _, _, _, receipts, _, _ = _compile_case("a-admitted")
    for receipt in receipts:
        assert LedgerAdapterReceipt.from_dict(receipt.to_dict()) == receipt


# --- identity and determinism -------------------------------------------------------


def test_candidate_identity_is_deterministic():
    first = _compile_case("f-multiple")[2]
    second = _compile_case("f-multiple")[2]
    assert [c.candidate_id for c in first] == [c.candidate_id for c in second]
    assert [c.to_dict() for c in first] == [c.to_dict() for c in second]


def test_state_change_alters_candidate_identity():
    pre, _, _, _, _ = _load_case("a-admitted")
    from project_context.ledger import events as E

    extra = E.LedgerEvent.from_dict(
        {
            "schema_version": E.LEDGER_EVENT_SCHEMA,
            "event_id": "evt-x",
            "event": "blocked",
            "item_id": "obligation-002",
            "recorded_at": "2026-09-24T12:00:00Z",
            "reason": "reblocked",
        }
    )
    events = list(
        __import__("project_context.ledger.store", fromlist=["load_events"]).load_events(
            SUITE / "a-admitted" / "events.jsonl"
        )
    ) + [extra]
    changed = project(events)
    assert changed.get("obligation-002").status.value == "blocked"
    old_ids = {c.candidate_id for c in _compile_case("a-admitted")[2]}
    state_request = ActivationRequest.from_dict(
        json.loads((SUITE / "a-admitted" / "request.json").read_text(encoding="utf-8"))
    )
    new_activation = activate(changed, state_request, TYPED)
    new_candidates, _ = adapt(changed, new_activation)
    new_ids = {c.candidate_id for c in new_candidates}
    assert old_ids != new_ids
    assert len({c.content_identity for c in new_candidates}) == len(new_candidates)


def test_adapter_does_not_rank_candidates():
    for name in ("f-multiple", "g-mixed-pool", "a-admitted"):
        _, _, pool, _, _, _ = _compile_case(name)
        ledger_relevance = {c.relevance for c in pool if c.source_kind == "ledger"}
        assert ledger_relevance == {ADAPTER_RELEVANCE}, name


def test_dependency_remap_names_coadapted_candidates():
    _, _, pool, receipts, _, _ = _compile_case("a-admitted")
    obligation = _by_source_ref(pool, "obligation-002")
    verification = _by_source_ref(pool, "verification-004")
    assert obligation.depends_on == (verification.candidate_id,)
    by_id = {r.item_id: r for r in receipts}
    assert by_id["obligation-002"].dropped_dependencies == ()


# --- no privilege -------------------------------------------------------------------------------


def test_no_adapted_candidate_is_mandatory_or_required():
    for name in sorted(p.name for p in SUITE.iterdir() if p.is_dir()):
        _, _, pool, _, _, _ = _compile_case(name)
        for candidate in pool:
            if candidate.source_kind == "ledger":
                assert candidate.requirement in (
                    RequirementClass.PREFERRED,
                    RequirementClass.DISCRETIONARY,
                ), (name, candidate.candidate_id)


def test_active_ledger_candidate_may_lose_under_policy():
    _, _, _, _, output, truth = _compile_case("b-ordinary-wins")
    assert output.result.success
    assert truth["ledger"]["obligation-002"]["admitted"] is False
    entry = output.result.trace.decisions_for(
        next(
            e.candidate_id
            for e in output.result.trace.entries
            if e.candidate_id.startswith("ledger-obligation-002-")
        )
    )[0]
    assert entry.decision.value == "REJECTED_BUDGET"


def test_active_ledger_candidate_may_be_omitted_by_budget():
    _, _, _, _, output, truth = _compile_case("c-budget-excludes")
    assert output.result.success
    assert truth["ledger"]["obligation-002"]["admitted"] is False
    assert truth["ledger"]["verification-004"]["admitted"] is False


def test_source_kind_confers_no_standing():
    _, _, pool, _, _, _ = _compile_case("g-mixed-pool")
    disguised = []
    for candidate in pool:
        raw = candidate.to_dict()
        raw["source_kind"] = "synthetic-fixture" if candidate.source_kind == "ledger" else "ledger"
        from project_context.compiler.domain import ContextCandidate

        disguised.append(ContextCandidate.from_dict(raw))
    compile_request = ContextRequest.from_dict(
        json.loads((SUITE / "g-mixed-pool" / "compile.json").read_text(encoding="utf-8"))
    )
    first = compile_context(compile_request, list(pool), POLICY)
    second = compile_context(compile_request, disguised, POLICY)
    # Source labels change nothing about who wins: the trace decides
    # identically when only source_kind is relabelled.
    assert [i.id for i in first.bundle.items] == [i.id for i in second.bundle.items]
    assert [e.to_dict() for e in first.result.trace.entries] == [
        e.to_dict() for e in second.result.trace.entries
    ]


def test_compiler_sources_contain_no_ledger_branch():
    import project_context.compiler as compiler_pkg

    root = Path(compiler_pkg.__file__).parent
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "ledger" not in text, path
        assert "activation" not in text, path
        assert "from_ledger" not in text, path
        assert "always_include" not in text, path


# --- compatibility cases ------------------------------------------------------------


def test_all_compatibility_cases_match_oracle():
    for name in sorted(p.name for p in SUITE.iterdir() if p.is_dir()):
        _, _, pool, _, output, truth = _compile_case(name)
        assert output.result.success == truth["success"], name
        by_ref = {c.source_ref: c for c in pool if c.source_kind == "ledger"}
        for item_id, want in truth["ledger"].items():
            candidate = by_ref[item_id]
            entry = output.result.trace.decisions_for(candidate.candidate_id)[0]
            admitted = entry.decision.value == "ADMITTED"
            assert admitted == want["admitted"], (name, item_id)
            assert entry.reason_code == want["trace_reason"], (name, item_id)
        for candidate_id, want in truth["ordinary"].items():
            entry = output.result.trace.decisions_for(candidate_id)[0]
            admitted = entry.decision.value == "ADMITTED"
            assert admitted == want["admitted"], (name, candidate_id)
            assert entry.reason_code == want["trace_reason"], (name, candidate_id)


def test_mixed_pool_trace_covers_every_record_and_bundle_validates():
    _, _, pool, _, output, _ = _compile_case("g-mixed-pool")
    traced = {e.candidate_id for e in output.result.trace.entries}
    assert traced == {c.candidate_id for c in pool}
    assert output.result.bundle_tokens <= 200
    assert [i.id for i in output.bundle.items] == list(output.bundle.layout_trace)


def test_legacy_compiler_fixtures_unchanged():
    from project_context.compiler.engine import compile_context as compile_fn

    manifest = json.loads(
        (Path("fixtures") / "compiler-v1" / "manifest.json").read_text(encoding="utf-8")
    )
    budgets = manifest["budgets"]["heterogeneous-basic"]
    candidates = load_candidate_file(
        Path("fixtures") / "compiler-v1" / "heterogeneous-basic.candidates.json"
    )
    base = ContextRequest.from_dict(
        json.loads(
            (Path("fixtures") / "compiler-v1" / "heterogeneous-basic.request.json").read_text(
                encoding="utf-8"
            )
        )
    )
    request = ContextRequest(
        request_id=f"{base.request_id}-medium",
        task_id=base.task_id,
        usable_token_budget=budgets["medium"],
        created_at=base.created_at,
        active_scope=base.active_scope,
        required_ids=base.required_ids,
        policy_version=base.policy_version,
    )
    first = compile_fn(request, candidates, POLICY)
    second = compile_fn(request, candidates, POLICY)
    assert first.result.to_dict() == second.result.to_dict()
    assert first.result.success


# --- boundaries ---------------------------------------------------------------------


def test_no_forbidden_imports_in_adapter():
    import project_context.ledger_adapter as adapter_pkg

    denied = {
        "os",
        "sys",
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "http",
        "time",
        "datetime",
        "random",
        "openai",
        "anthropic",
        "torch",
        "numpy",
    }
    pattern = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_]+)", re.M)
    root = Path(adapter_pkg.__file__).parent
    for path in root.glob("*.py"):
        if path.name == "__init__.py":
            continue
        found = set(pattern.findall(path.read_text(encoding="utf-8")))
        assert not (found & denied), f"{path}: {found & denied}"
        assert "project_context.opencode" not in path.read_text(encoding="utf-8"), path
        assert "project_context.evaluation" not in path.read_text(encoding="utf-8"), path


def test_adapter_import_direction_is_one_way():
    import project_context

    root = Path(project_context.__file__).parent

    def imports_of(package):
        found = set()
        for path in (root / package).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module:
                    found.add(node.module)
                elif isinstance(node, ast.Import):
                    found.update(a.name for a in node.names)
        return found

    adapter_imports = imports_of("ledger_adapter")
    assert {m for m in adapter_imports if "project_context" in m} <= {
        "project_context.activation.model",
        "project_context.compiler.domain",
        "project_context.domain.items",
        "project_context.ledger.projection",
        "project_context.ledger.records",
        "project_context.ledger_adapter.adapter",
    }
    for package in ("compiler", "ledger", "activation", "opencode"):
        target = root / package
        for path in target.rglob("*.py"):
            assert "project_context.ledger_adapter" not in path.read_text(encoding="utf-8"), path


def test_stage_boundaries_still_hold():
    state = project(load_events(Path("fixtures") / "ledger-v1" / "events.jsonl"))
    assert state.digest() == "cce87221e00ad7cb28e74a9ff72f1ad2a82fc3389a64dc855691138efe69a399"
    from project_context.activation.engine import activate as activate_fn

    manifest = json.loads(
        (Path("fixtures") / "activation-v1" / "manifest.json").read_text(encoding="utf-8")
    )
    _ = manifest
    case_dir = Path("fixtures") / "activation-v1" / "cases" / "migration"
    case_state = project(load_events(case_dir / "events.jsonl"))
    truth = json.loads((case_dir / "truth.json").read_text(encoding="utf-8"))["requests"]
    for req_path in sorted((case_dir / "requests").glob("*.json")):
        request = ActivationRequest.from_dict(json.loads(req_path.read_text(encoding="utf-8")))
        result = activate_fn(case_state, request, TYPED)
        for decision in result.decisions:
            want = truth[request.request_id][decision.item_id]
            assert decision.state.value == want["state"]
            assert list(decision.reason_codes) == want["reasons"]


def test_fixture_runtime_files_carry_no_oracle_tokens():
    for case in [p for p in SUITE.iterdir() if p.is_dir()]:
        for name in ("events.jsonl", "request.json", "ordinary.candidates.json", "compile.json"):
            blob = (case / name).read_text(encoding="utf-8").lower()
            for token in ("oracle", "truth", "eval_class", "distractor", "harmful"):
                assert token not in blob, (case, name, token)


def test_opencode_capture_has_no_adapter_presence():
    import project_context

    root = Path(project_context.__file__).parent
    for path in (root / "opencode").rglob("*.py"):
        assert "ledger_adapter" not in path.read_text(encoding="utf-8"), path
    ts_root = Path("integrations") / "opencode" / "src"
    if ts_root.is_dir():
        for path in ts_root.rglob("*.ts"):
            blob = path.read_text(encoding="utf-8").lower()
            assert "ledger_adapter" not in blob, path


# --- CLI ------------------------------------------------------------------------------


def test_cli_candidates_and_compile(capsys):
    req = str(SUITE / "d-authority-not-source" / "request.json")
    assert cli_main(["ledger", "candidates", "d-authority-not-source", "--request-file", req]) == 0
    out = capsys.readouterr().out
    assert "[SYNTHETIC]" in out and "constraint-001" in out
    assert "truth" not in out.lower()
    assert (
        cli_main(
            ["ledger", "candidates", "d-authority-not-source", "--request-file", req, "--compile"]
        )
        == 0
    )
    compiled = capsys.readouterr().out
    assert "COMPILE: success" in compiled
    assert cli_main(["ledger", "candidates", "nope", "--request-file", req]) == 2
