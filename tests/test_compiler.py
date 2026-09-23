"""Stage 3 compiler tests: determinism, legality, traps, traces, leaks.

Conventions: fixtures load from fixtures/compiler-v1 (committed JSON).
 Budgets come from the fixture manifest. Nothing here calls models or
network. Oracle truth is loaded only to assert outcomes, never fed to
the staged compiler.
"""

import json
from pathlib import Path

import pytest

from project_context.cli.main import main as cli_main
from project_context.compiler import domain as C
from project_context.compiler.engine import compile_context
from project_context.compiler.fixtures import (
    load_candidate_file,
    load_fixture_set,
    load_request_file,
)
from project_context.compiler.policy import CompilerPolicy

ROOT = Path("fixtures") / "compiler-v1"
POLICY_PATH = Path("experiments") / "compiler-v1" / "policies" / "compiler-policy-v1.json"
WEIGHTS_PATH = Path("experiments") / "compiler-v1" / "weights.json"


def _manifest():
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def _policy():
    return CompilerPolicy.from_dict(json.loads(POLICY_PATH.read_text(encoding="utf-8")))


def _load(name, budget):
    manifest = _manifest()
    fixture_set = load_fixture_set(ROOT)
    candidates = load_candidate_file(fixture_set[name]["candidates"])
    base = load_request_file(fixture_set[name]["request"])
    request = C.ContextRequest(
        request_id=f"{base.request_id}-{budget}",
        task_id=base.task_id,
        usable_token_budget=manifest["budgets"][name][budget],
        created_at=base.created_at,
        active_scope=base.active_scope,
        required_ids=base.required_ids,
        policy_version=base.policy_version,
    )
    return request, candidates


def _compile(name, budget, policy=None):
    request, candidates = _load(name, budget)
    return request, candidates, compile_context(request, candidates, policy or _policy())


def _truth(name):
    from project_context.evaluation.compiler_eval import load_truth_file

    return load_truth_file(ROOT / f"{name}.truth.json")


# --- determinism and purity -------------------------------------------------


def test_deterministic_compile_equality():
    request, candidates, first = _compile("heterogeneous-basic", "medium")
    second = compile_context(request, candidates, _policy())
    assert first.result.to_dict() == second.result.to_dict()
    assert first.bundle.content_hash() == second.bundle.content_hash()


def test_inputs_not_mutated():
    request, candidates = _load("dependency-trap", "tight")
    before_c = [c.to_dict() for c in candidates]
    before_r = request.to_dict()
    policy = _policy()
    before_p = policy.to_dict()
    compile_context(request, candidates, policy)
    assert [c.to_dict() for c in candidates] == before_c
    assert request.to_dict() == before_r
    assert policy.to_dict() == before_p


def test_no_forbidden_imports_in_compiler():
    import re

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
    for path in (Path("src/project_context/compiler")).glob("*.py"):
        if path.name == "__init__.py":
            continue
        roots = set(pattern.findall(path.read_text(encoding="utf-8")))
        assert not (roots & denied), f"{path}: {roots & denied}"


def test_compiler_never_imports_evaluation():
    import re

    for path in Path("src/project_context/compiler").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "project_context.evaluation" not in text, path
        assert "project_context\\evaluation" not in text, path
        for token in ("eval_class", "oracle_", "DISTRACTOR", "HARMFUL"):
            assert token not in text, f"{path}: {token}"
        assert not re.search(r"^\s*(import|from)\s+evaluation\b", text, re.M), path


def test_fixture_files_carry_no_oracle_truth():
    for path in ROOT.glob("*.candidates.json"):
        blob = path.read_text(encoding="utf-8")
        assert "eval_class" not in blob, path
        assert "oracle" not in blob.lower(), path
    for path in ROOT.glob("*.request.json"):
        blob = path.read_text(encoding="utf-8")
        assert "eval_class" not in blob, path


def test_truth_presence_changes_nothing():
    # Staged output must be identical whether truth files exist or not.
    request, candidates = _load("stale-cheap", "tight")
    first = compile_context(request, candidates, _policy())
    _truth("stale-cheap")
    second = compile_context(request, candidates, _policy())
    assert first.result.to_dict() == second.result.to_dict()


# --- hard gates ---------------------------------------------------------------


def test_illegal_high_relevance_never_admitted():
    request, candidates, output = _compile("wrong-scope", "tight")
    assert output.result.success
    admitted = [item.id for item in output.bundle.items]
    assert "scope-out" not in admitted
    entry = output.result.trace.decisions_for("scope-out")[0]
    assert entry.decision == C.TraceDecision.REJECTED_HARD
    assert entry.reason_code == "scope_ineligible"


def test_stale_cheap_rejected_despite_cost():
    request, candidates, output = _compile("stale-cheap", "tight")
    assert output.result.success
    admitted = [item.id for item in output.bundle.items]
    assert "stale-compact" not in admitted
    assert "fresh-full" in admitted


def test_mandatory_overflow_fails():
    for budget in ("tight", "medium"):
        request, candidates, output = _compile("mandatory-overflow", budget)
        assert not output.result.success
        assert output.result.failure.reason == C.FailureReason.INSUFFICIENT_BUDGET
        assert output.bundle is None


def test_no_legal_representation_fails():
    request, candidates, output = _compile("no-legal-representation", "medium")
    assert not output.result.success
    assert output.result.failure.reason == C.FailureReason.NO_LEGAL_REPRESENTATION


def test_required_unavailable_fails():
    request, candidates, output = _compile("required-unavailable", "tight")
    assert not output.result.success
    assert output.result.failure.reason == C.FailureReason.REQUIRED_SOURCE_UNAVAILABLE
    assert "ghost-1" in output.result.failure.blocking_ids


def test_monotonic_failure_below_mandatory_minimum():
    # Below the minimum legal mandatory cost, only explicit failure is legal.
    request, candidates = _load("budget-slack", "tight")
    tiny = C.ContextRequest(
        request_id="tiny",
        task_id=request.task_id,
        usable_token_budget=10,
        created_at=request.created_at,
        active_scope=request.active_scope,
        required_ids=request.required_ids,
        policy_version=request.policy_version,
    )
    output = compile_context(tiny, candidates, _policy())
    assert not output.result.success
    assert output.result.failure.reason == C.FailureReason.INSUFFICIENT_BUDGET


# --- representations ------------------------------------------------------------


def test_alternatives_never_double_selected():
    request, candidates, output = _compile("representation-alternatives", "roomy")
    assert output.result.success
    identities = [
        c.content_identity
        for c in candidates
        if c.candidate_id in [i.id for i in output.bundle.items]
    ]
    assert len(identities) == len(set(identities))


def test_composite_anchor_reference_admitted_together():
    request, candidates, output = _compile("dependency-trap", "tight")
    assert output.result.success
    admitted = [item.id for item in output.bundle.items]
    assert "ref-cheap" in admitted
    assert "resolver-tool" in admitted


def test_form_choice_recomputed_per_budget():
    # Cheapest fitting legal form wins at every budget: anchor in tight and
    # in roomy. No superset relation is encoded anywhere in the engine;
    # each budget recompiles from scratch (determinism tests pin this).
    # A sufficiency-aware policy variant could select richer forms when
    # affordable, which is precisely why superset must never be assumed.
    _, _, tight = _compile("representation-alternatives", "tight")
    _, _, roomy = _compile("representation-alternatives", "roomy")
    tight_ids = {i.id for i in tight.bundle.items}
    roomy_ids = {i.id for i in roomy.bundle.items}
    assert "inc-anchor" in tight_ids and "inc-anchor" in roomy_ids
    slack_tight = 400 - tight.result.bundle_tokens
    slack_roomy = 2000 - roomy.result.bundle_tokens
    assert slack_roomy > slack_tight


# --- dependencies and groups ------------------------------------------------------


def test_dependency_closure_commits_requirements():
    request, candidates, output = _compile("dependency-trap", "tight")
    admitted = [item.id for item in output.bundle.items]
    assert "resolver-tool" in admitted  # pulled in by ref-cheap, not by rank


def test_shared_dependency_emitted_once():
    request, candidates, output = _compile("shared-dependency", "tight")
    assert output.result.success
    admitted = [item.id for item in output.bundle.items]
    assert admitted.count("tool-def") == 1
    assert "ref-a" in admitted and "ref-b" in admitted


def test_shared_dependency_exact_accounting():
    from project_context.compiler.engine import (
        _SEPARATOR_TOKENS,
        _decoration_tokens,
        header_tokens,
    )

    request, candidates, output = _compile("shared-dependency", "tight")
    by_id = {c.candidate_id: c for c in candidates}
    admitted = [item.id for item in output.bundle.items]
    expected = (
        sum(by_id[cid].token_count + _decoration_tokens(by_id[cid]) for cid in admitted)
        + max(0, len(admitted) - 1) * _SEPARATOR_TOKENS
        + header_tokens(request)
    )
    assert output.result.bundle_tokens == expected


def test_dependency_cycle_terminates():
    request, candidates, output = _compile("dependency-cycle", "tight")
    assert output.result.success
    admitted = [item.id for item in output.bundle.items]
    assert "cyc-a" in admitted and "cyc-b" in admitted


def test_missing_dependency_is_config_error():
    request, candidates = _load("budget-slack", "tight")
    raw = candidates[0].to_dict()
    raw["depends_on"] = ["no-such-record"]
    bad = C.ContextCandidate.from_dict(raw)
    with pytest.raises(ValueError, match="unknown dependency"):
        compile_context(request, [bad], _policy())


def test_ineligible_dependency_blocks_mandatory():
    request, candidates = _load("wrong-scope", "tight")
    raw = candidates[0].to_dict()
    raw.update(
        candidate_id="mand-parent",
        content_identity="mand-parent",
        requirement="MANDATORY",
        depends_on=["scope-out"],
    )
    parent = C.ContextCandidate.from_dict(raw)
    output = compile_context(request, [parent] + candidates[1:], _policy())
    assert not output.result.success
    assert output.result.failure.reason == C.FailureReason.UNSATISFIED_DEPENDENCY


def test_required_group_atomic():
    request, candidates, output = _compile("qualification-trap", "tight")
    assert output.result.success
    admitted = [item.id for item in output.bundle.items]
    assert "claim-positive" in admitted
    assert "exception-tenant" in admitted


def test_conflict_group_preserved():
    request, candidates, output = _compile("conflict-trap", "medium")
    assert output.result.success
    admitted = [item.id for item in output.bundle.items]
    assert "claim-a" in admitted and "claim-b" in admitted
    assert "conflict-marker" in admitted


def test_group_band_mixing_rejected():
    request, candidates = _load("qualification-trap", "tight")
    raw = candidates[2].to_dict()
    raw["requirement"] = "DISCRETIONARY"
    with pytest.raises(ValueError, match="spans bands"):
        compile_context(
            request,
            [
                c if c.candidate_id != "claim-positive" else C.ContextCandidate.from_dict(raw)
                for c in candidates
            ],
            _policy(),
        )


# --- budget behaviour ---------------------------------------------------------------


def test_roomy_budget_leaves_slack():
    request, candidates, output = _compile("budget-slack", "roomy")
    assert output.result.success
    assert output.result.bundle_tokens < request.usable_token_budget
    slack = request.usable_token_budget - output.result.bundle_tokens
    assert slack > 2000
    admitted = [item.id for item in output.bundle.items]
    assert "distract-d1" not in admitted and "distract-d2" not in admitted


def test_rendered_overflow_repairs_discretionary_only():
    request, candidates, output = _compile("rendered-overflow", "tight")
    assert output.result.success
    admitted = [item.id for item in output.bundle.items]
    assert "instr-1" in admitted and "taskreq-1" in admitted
    assert "disc-a" not in admitted
    assert output.result.bundle_tokens <= request.usable_token_budget
    dropped = output.result.trace.decisions_for("disc-a")[0]
    assert dropped.reason_code == "repair-drop"


@pytest.mark.parametrize(
    "name,budget",
    [
        (name, budget)
        for name in (
            "dependency-trap",
            "qualification-trap",
            "conflict-trap",
            "stale-cheap",
            "wrong-scope",
            "budget-slack",
            "representation-alternatives",
            "shared-dependency",
            "dependency-cycle",
            "rendered-overflow",
            "heterogeneous-basic",
            "mandatory-overflow",
        )
        for budget in ("tight", "medium", "roomy")
    ],
)
def test_rendered_never_exceeds_budget_on_success(name, budget):
    request, candidates, output = _compile(name, budget)
    if output.result.success:
        assert output.result.bundle_tokens <= request.usable_token_budget


def test_trace_covers_every_record():
    request, candidates, output = _compile("heterogeneous-basic", "medium")
    traced = {e.candidate_id for e in output.result.trace.entries}
    assert traced == {c.candidate_id for c in candidates}


def test_early_rejection_keeps_evidence():
    request, candidates, output = _compile("heterogeneous-basic", "medium")
    entry = output.result.trace.decisions_for("scope-bad")[0]
    assert entry.decision == C.TraceDecision.REJECTED_HARD
    assert "project-b" in entry.reason_detail


def test_trace_ordering_deterministic():
    output = _compile("heterogeneous-basic", "medium")[2]
    ids = [e.candidate_id for e in output.result.trace.entries]
    assert ids == sorted(ids)


def test_policy_version_recorded():
    request, candidates, output = _compile("budget-slack", "tight")
    assert output.result.policy_version == "compiler-policy-v1"
    assert output.result.trace.policy_version == "compiler-policy-v1"


def test_failure_deterministic_and_complete():
    first = _compile("mandatory-overflow", "tight")[2]
    second = _compile("mandatory-overflow", "tight")[2]
    assert first.result.to_dict() == second.result.to_dict()
    failure = first.result.failure
    assert failure.blocking_ids
    assert failure.diagnostic
    assert failure.budget_total == 4000


# --- records ------------------------------------------------------------------------


def test_json_round_trips():
    request, candidates = _load("budget-slack", "tight")
    for record in candidates:
        assert C.ContextCandidate.from_dict(record.to_dict()) == record
    assert C.ContextRequest.from_dict(request.to_dict()) == request
    policy = _policy()
    assert CompilerPolicy.from_dict(policy.to_dict()) == policy
    output = compile_context(request, candidates, policy)
    assert C.DecisionTrace.from_dict(output.result.trace.to_dict()) == output.result.trace
    assert C.CompilationResult.from_dict(output.result.to_dict()) == output.result


def test_strict_loader_rejects_unknown_keys(tmp_path):
    from project_context.compiler.fixtures import load_candidate_file

    bad = {
        "candidates": [
            {
                "candidate_id": "x",
                "content_identity": "x",
                "representation_id": "f",
                "form_rank": 3,
                "min_rank": 0,
                "source_kind": "s",
                "source_ref": "r",
                "kind": "k",
                "content": "c",
                "token_count": 5,
                "requirement": "MANDATORY",
                "order_role": "evidence",
                "scope_eligible": True,
                "freshness_eligible": True,
                "authority_eligible": True,
                "eval_class": "must",
            }
        ]
    }
    path = tmp_path / "x.candidates.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown candidate keys"):
        load_candidate_file(path)


def test_fixture_manifest_lists_committed_files():
    manifest = _manifest()
    assert manifest["fixture_version"] == "1"
    assert manifest["evidence_class"] == "synthetic"
    for name in manifest["fixtures"]:
        assert (ROOT / f"{name}.candidates.json").is_file()
        assert (ROOT / f"{name}.request.json").is_file()
        assert (ROOT / f"{name}.truth.json").is_file()
        assert set(manifest["budgets"][name]) == {"tight", "medium", "roomy"}


def test_synthetic_labels_preserved():
    request, candidates, output = _compile("budget-slack", "tight")
    assert output.bundle.evidence_class == "synthetic"


# --- CLI ------------------------------------------------------------------------------


def test_cli_compiler_fixtures(capsys):
    assert cli_main(["compiler", "fixtures"]) == 0
    out = capsys.readouterr().out
    assert "dependency-trap" in out
    assert "[SYNTHETIC]" in out


def test_cli_compiler_inspect(capsys):
    assert cli_main(["compiler", "inspect", "wrong-scope"]) == 0
    out = capsys.readouterr().out
    assert "ADMITTED" in out and "scope-out" in out
    assert cli_main(["compiler", "inspect", "nope"]) == 2


def test_cli_compiler_run_validate_and_determinism(tmp_path, capsys):
    runs_a = tmp_path / "runs-a"
    runs_b = tmp_path / "runs-b"
    args = ["compiler", "run", "compiler-v1", "--timestamp", "2026-09-23T00:00:00Z"]
    assert cli_main([*args, "--run-id", "det-1", "--runs-dir", str(runs_a)]) == 0
    assert cli_main([*args, "--run-id", "det-1", "--runs-dir", str(runs_b)]) == 0
    first = (runs_a / "compiler-v1" / "det-1" / "compilation.jsonl").read_text(encoding="utf-8")
    second = (runs_b / "compiler-v1" / "det-1" / "compilation.jsonl").read_text(encoding="utf-8")
    assert first == second
    first_results = (runs_a / "compiler-v1" / "det-1" / "results.json").read_text(encoding="utf-8")
    second_results = (runs_b / "compiler-v1" / "det-1" / "results.json").read_text(encoding="utf-8")
    assert first_results == second_results
    assert cli_main(["compiler", "validate-run", str(runs_a / "compiler-v1" / "det-1")]) == 0
    assert "valid" in capsys.readouterr().out
