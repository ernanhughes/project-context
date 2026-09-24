"""Stage 6B Context Activation tests: selective, explainable, abstaining.

Nothing here calls models or network. Oracle truth files are loaded only
to assert outcomes; activation runtime code never reads them. Metrics
helpers below are test-only evaluation, mirroring how compiler tests load
truth directly.
"""

import ast
import json
import re
from pathlib import Path

from project_context.activation import model as M
from project_context.activation.engine import activate, result_digest
from project_context.activation.model import (
    ActivationMode,
    ActivationPolicy,
    ActivationRequest,
    ActivationResult,
    ActivationState,
)
from project_context.cli.main import main as cli_main
from project_context.ledger.projection import project
from project_context.ledger.store import load_events

SUITE = Path("fixtures") / "activation-v1"
CASES = SUITE / "cases"
HELDOUT = SUITE / "heldout"
TYPED = ActivationPolicy()


def _load_case(case_dir):
    state = project(load_events(case_dir / "events.jsonl"))
    requests = {}
    for path in sorted((case_dir / "requests").glob("*.json")):
        request = ActivationRequest.from_dict(json.loads(path.read_text(encoding="utf-8")))
        requests[request.request_id] = request
    truth = json.loads((case_dir / "truth.json").read_text(encoding="utf-8"))["requests"]
    return state, requests, truth


def _all_cases():
    names = sorted(p.name for p in CASES.iterdir() if p.is_dir())
    names += [f"heldout/{p.name}" for p in sorted(HELDOUT.iterdir()) if p.is_dir()]
    return names


def _case_dir(name):
    return HELDOUT / name.split("/", 1)[1] if name.startswith("heldout/") else CASES / name


def _metrics(state, requests, truth, policy):
    tp = fp = fn = unknown = 0
    for request_id, request in requests.items():
        result = activate(state, request, policy)
        for decision in result.decisions:
            want = truth[request_id][decision.item_id]
            oracle_active = want["state"] == "active"
            decided_active = decision.state is ActivationState.ACTIVE
            if decision.state is ActivationState.UNKNOWN:
                unknown += 1
            if decided_active and oracle_active:
                tp += 1
            elif decided_active:
                fp += 1
            elif oracle_active:
                fn += 1
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {
        "tp": tp,
        "precision": precision,
        "recall": recall,
        "false": fp,
        "missed": fn,
        "unknown": unknown,
    }


# --- determinism and records ----------------------------------------------------


def test_activation_is_deterministic():
    state, requests, _ = _load_case(CASES / "migration")
    request = requests["req-edit-migration"]
    first = activate(state, request, TYPED)
    second = activate(state, request, TYPED)
    assert result_digest(first) == result_digest(second)
    assert first.to_dict() == second.to_dict()


def test_activation_records_round_trip():
    state, requests, _ = _load_case(CASES / "schema")
    request = requests["req-schema-task"]
    assert ActivationRequest.from_dict(request.to_dict()) == request
    assert ActivationPolicy.from_dict(TYPED.to_dict()) == TYPED
    result = activate(state, request, TYPED)
    assert ActivationResult.from_dict(result.to_dict()) == result
    for decision in result.decisions:
        assert M.ActivationDecision.from_dict(decision.to_dict()) == decision
    assert [d.item_id for d in result.decisions] == sorted(d.item_id for d in result.decisions)


def test_policy_identifies_itself_in_every_decision():
    state, requests, _ = _load_case(CASES / "migration")
    result = activate(state, requests["req-edit-migration"], TYPED)
    assert result.policy_id == "activation-policy-v1"
    assert all(d.policy_id == "activation-policy-v1" for d in result.decisions)


# --- validity before relevance ----------------------------------------------------


def test_terminal_and_superseded_state_never_becomes_active_truth():
    state, requests, truth = _load_case(CASES / "schema")
    result = activate(state, requests["req-schema-task"], TYPED)
    decision = result.decision_for("decision-001")
    assert decision.state is ActivationState.INELIGIBLE
    assert decision.reason_codes == ("superseded",)
    assert "decision-001" not in result.active_ids()
    assert result.decision_for("decision-002").state is ActivationState.ACTIVE


def test_contradicted_claims_are_never_promoted():
    state, requests, _ = _load_case(CASES / "contradicted-claim")
    result = activate(state, requests["req-race-tests"], TYPED)
    decision = result.decision_for("claim-001")
    assert decision.state is ActivationState.INELIGIBLE
    assert decision.reason_codes == ("contradicted",)
    assert decision.epistemic is None


def test_no_typed_active_decision_is_terminal_or_contradicted_anywhere():
    for name in _all_cases():
        state, requests, _ = _load_case(_case_dir(name))
        for request in requests.values():
            result = activate(state, request, TYPED)
            for item_id in result.active_ids():
                entry = state.get(item_id)
                assert entry.status.value in ("active", "blocked"), (name, item_id)
                assert entry.verification.value != "contradicted", (name, item_id)


# --- selectivity ---------------------------------------------------------------------


def test_unrelated_valid_state_remains_dormant():
    state, requests, _ = _load_case(CASES / "irrelevant-valid")
    result = activate(state, requests["req-edit-migration"], TYPED)
    assert result.active_ids() == ()
    for item_id in ("assumption-001", "failure-002"):
        decision = result.decision_for(item_id)
        assert decision.state is ActivationState.DORMANT
        assert decision.reason_codes == ("no_activation_reason",)


def test_exact_scope_match_activates():
    state, requests, _ = _load_case(CASES / "migration")
    decision = activate(state, requests["req-edit-migration"], TYPED).decision_for("constraint-001")
    assert decision.state is ActivationState.ACTIVE
    assert set(decision.reason_codes) == {
        "operation_in_governed_scope",
        "scope_component_match",
        "scope_path_match",
    }
    assert decision.matched_scope["paths"] == ["db/migrations/017"]


def test_scope_mismatch_rejects_without_leak():
    state, requests, _ = _load_case(CASES / "scope-leak")
    alpha = activate(state, requests["req-alpha-schema"], TYPED)
    assert alpha.decision_for("decision-a").state is ActivationState.ACTIVE
    beta_item = alpha.decision_for("decision-b")
    assert beta_item.state is ActivationState.INELIGIBLE
    assert beta_item.reason_codes == ("scope_repo_mismatch",)
    mirror = activate(state, requests["req-beta-schema"], TYPED)
    assert mirror.decision_for("decision-b").state is ActivationState.ACTIVE
    assert mirror.decision_for("decision-a").reason_codes == ("scope_repo_mismatch",)


def test_repo_equality_alone_never_activates():
    from project_context.ledger import events as E
    from project_context.ledger import records as R

    def _item(item_id):
        return {
            "schema_version": R.LEDGER_ITEM_SCHEMA,
            "item_id": item_id,
            "kind": "decision",
            "statement": "repo-only note",
            "authority": "project",
            "scope": {"repo": "project-context"},
            "source": {},
        }

    events = [
        E.LedgerEvent.from_dict(
            {
                "schema_version": E.LEDGER_EVENT_SCHEMA,
                "event_id": "e1",
                "event": "item_created",
                "item_id": "r1",
                "recorded_at": "2026-09-24T10:00:00Z",
                "item": _item("r1"),
            }
        )
    ]
    request = ActivationRequest(
        request_id="q",
        task_id="t",
        created_at="2026-09-24T11:00:00Z",
        repo="project-context",
        components=("other",),
    )
    decision = activate(project(events), request, TYPED).decision_for("r1")
    assert decision.state is ActivationState.DORMANT


# --- abstention ---------------------------------------------------------------------------


def test_missing_request_metadata_returns_unknown():
    state, requests, _ = _load_case(CASES / "missing-metadata")
    result = activate(state, requests["req-bare"], TYPED)
    for item_id in ("constraint-001", "note-001"):
        decision = result.decision_for(item_id)
        assert decision.state is ActivationState.UNKNOWN, item_id
        assert decision.reason_codes == ("request_features_absent",), item_id


def test_scopeless_item_with_featured_request_abstains():
    state, requests, _ = _load_case(CASES / "missing-metadata")
    decision = activate(state, requests["req-edit-migration"], TYPED).decision_for("note-001")
    assert decision.state is ActivationState.UNKNOWN
    assert decision.reason_codes == ("insufficient_scope_to_decide",)


def test_unknown_never_defaults_to_active():
    for name in _all_cases():
        state, requests, truth = _load_case(_case_dir(name))
        for request_id, request in requests.items():
            result = activate(state, request, TYPED)
            for decision in result.decisions:
                if truth[request_id][decision.item_id]["state"] == "unknown":
                    assert decision.state is ActivationState.UNKNOWN, (name, decision.item_id)


# --- dependencies and relationships --------------------------------------------------------------


def test_dependency_readiness_gates_obligation_activation():
    pre, pre_requests, _ = _load_case(CASES / "obligation-pre")
    post, post_requests, _ = _load_case(CASES / "obligation-post")
    narrow_pre = activate(pre, pre_requests["req-adapter-narrow"], TYPED).decision_for(
        "obligation-002"
    )
    assert narrow_pre.state is ActivationState.DORMANT
    assert narrow_pre.reason_codes == ("blocked_dependency_unmet",)
    assert narrow_pre.matched_scope["paths"] == ["src/project_context/compat/adapter"]
    narrow_post = activate(post, post_requests["req-adapter-narrow"], TYPED).decision_for(
        "obligation-002"
    )
    assert narrow_post.state is ActivationState.ACTIVE
    assert set(narrow_post.reason_codes) == {"dependency_ready", "scope_path_match"}


def test_blocking_condition_request_wakes_blocked_obligation():
    state, requests, _ = _load_case(CASES / "obligation-pre")
    decision = activate(state, requests["req-run-suite"], TYPED).decision_for("obligation-002")
    assert decision.state is ActivationState.ACTIVE
    assert "blocking_condition_relevant" in decision.reason_codes


def test_relationship_propagation_is_bounded_to_one_hop():
    from project_context.ledger import events as E
    from project_context.ledger import records as R

    def _item(item_id):
        return {
            "schema_version": R.LEDGER_ITEM_SCHEMA,
            "item_id": item_id,
            "kind": "decision",
            "statement": f"link {item_id}",
            "authority": "agent",
            "scope": {"component": "chain"} if item_id == "c" else {},
            "source": {},
        }

    def _rel(event_id, src, tgt):
        return E.LedgerEvent.from_dict(
            {
                "schema_version": E.LEDGER_EVENT_SCHEMA,
                "event_id": event_id,
                "event": "relationship_added",
                "item_id": src,
                "recorded_at": "2026-09-24T10:10:00Z",
                "relationship": {"type": "depends_on", "source_id": src, "target_id": tgt},
            }
        )

    events = [
        E.LedgerEvent.from_dict(
            {
                "schema_version": E.LEDGER_EVENT_SCHEMA,
                "event_id": f"create-{i}",
                "event": "item_created",
                "item_id": i,
                "recorded_at": "2026-09-24T10:00:00Z",
                "item": _item(i),
            }
        )
        for i in ("a", "b", "c")
    ] + [_rel("r1", "b", "c"), _rel("r2", "a", "b")]
    request = ActivationRequest(
        request_id="q",
        task_id="t",
        created_at="2026-09-24T11:00:00Z",
        repo="project-context",
        components=("chain",),
    )
    result = activate(project(events), request, TYPED)
    assert result.decision_for("c").state is ActivationState.ACTIVE
    propagated = result.decision_for("b")
    assert propagated.state is ActivationState.ACTIVE
    assert "dependency_active" in propagated.reason_codes
    assert propagated.matched_dependencies == ("c",)
    assert result.decision_for("a").state is not ActivationState.ACTIVE


def test_multiple_items_may_activate_together():
    state, requests, _ = _load_case(CASES / "multi-item")
    result = activate(state, requests["req-compat-release"], TYPED)
    assert set(result.active_ids()) == {"obligation-002", "result-001", "verification-004"}
    assert result.decision_for("failure-001").state is ActivationState.DORMANT


def test_epistemic_status_survives_activation():
    state, requests, _ = _load_case(CASES / "pending-claim")
    active = activate(state, requests["req-race-tests"], TYPED).decision_for("claim-001")
    assert active.state is ActivationState.ACTIVE
    assert active.epistemic == "unverified"
    multi, _, _ = _load_case(CASES / "multi-item")
    verified = activate(
        multi,
        ActivationRequest.from_dict(
            json.loads(
                (CASES / "multi-item" / "requests" / "compat-release.json").read_text(
                    encoding="utf-8"
                )
            )
        ),
        TYPED,
    ).decision_for("verification-004")
    assert verified.epistemic == "verified"


# --- oracle match and baselines -----------------------------------------------------------------


def test_typed_policy_matches_every_core_oracle_decision():
    for name in sorted(p.name for p in CASES.iterdir() if p.is_dir()):
        state, requests, truth = _load_case(CASES / name)
        for request_id, request in requests.items():
            result = activate(state, request, TYPED)
            for decision in result.decisions:
                want = truth[request_id][decision.item_id]
                assert decision.state.value == want["state"], (name, request_id, decision.item_id)
                assert list(decision.reason_codes) == want["reasons"], (
                    name,
                    request_id,
                    decision.item_id,
                )


def test_typed_policy_matches_every_heldout_oracle_decision():
    for name in sorted(p.name for p in HELDOUT.iterdir() if p.is_dir()):
        state, requests, truth = _load_case(HELDOUT / name)
        for request_id, request in requests.items():
            result = activate(state, request, TYPED)
            for decision in result.decisions:
                want = truth[request_id][decision.item_id]
                assert decision.state.value == want["state"], (name, request_id, decision.item_id)
                assert list(decision.reason_codes) == want["reasons"], (
                    name,
                    request_id,
                    decision.item_id,
                )


def test_heldout_generation_is_reproducible():
    manifest = json.loads((SUITE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["heldout"]["seed"] == 7
    assert manifest["heldout"]["generator"] == "experiments/activation-v1/generate.py"
    assert sorted(manifest["heldout"]["cases"]) == sorted(
        p.name for p in HELDOUT.iterdir() if p.is_dir()
    )


def _baseline_mismatches(mode):
    policy = ActivationPolicy(mode=mode)
    misses = []
    for name in _all_cases():
        state, requests, truth = _load_case(_case_dir(name))
        for request_id, request in requests.items():
            result = activate(state, request, policy)
            for decision in result.decisions:
                if decision.state.value != truth[request_id][decision.item_id]["state"]:
                    misses.append((name, request_id, decision.item_id))
    return misses


def test_all_unresolved_baseline_fails_adversarial_fixtures():
    misses = _baseline_mismatches(ActivationMode.ALL_UNRESOLVED)
    families = {m[0] for m in misses}
    assert "irrelevant-valid" in families
    assert "migration" in families
    assert len(misses) > 0


def test_scope_only_baseline_fails_adversarial_fixtures():
    misses = _baseline_mismatches(ActivationMode.SCOPE_ONLY)
    assert any(m[0] == "schema" for m in misses)  # superseded decision activates
    assert any(m[0] == "scope-leak" for m in misses)


def test_newest_baseline_fails_adversarial_fixtures():
    misses = _baseline_mismatches(ActivationMode.NEWEST)
    assert len(misses) > 0
    assert {m[0] for m in misses} != set()


def test_typed_precision_and_recall_are_perfect_and_baselines_are_not():
    tp = fp = fn = 0
    for name in sorted(p.name for p in CASES.iterdir() if p.is_dir()):
        state, requests, truth = _load_case(CASES / name)
        typed = _metrics(state, requests, truth, TYPED)
        assert typed["false"] == 0 and typed["missed"] == 0, name
        tp += typed["tp"]
        fp += typed["false"]
        fn += typed["missed"]
    assert tp > 0 and fp == 0 and fn == 0
    assert tp / (tp + fp) == 1.0 and tp / (tp + fn) == 1.0
    any_baseline_false = False
    for mode in (
        ActivationMode.ALL_UNRESOLVED,
        ActivationMode.SCOPE_ONLY,
        ActivationMode.NEWEST,
    ):
        for name in _all_cases():
            state, requests, truth = _load_case(_case_dir(name))
            metrics = _metrics(state, requests, truth, ActivationPolicy(mode=mode))
            any_baseline_false = any_baseline_false or metrics["false"] > 0
    assert any_baseline_false


# --- hidden truth and boundaries ------------------------------------------------------


def test_fixture_runtime_files_carry_no_oracle_tokens():
    for base in (CASES, HELDOUT):
        for case in [p for p in base.iterdir() if p.is_dir()]:
            events_blob = (case / "events.jsonl").read_text(encoding="utf-8").lower()
            for token in ("oracle", "expected", "truth", "eval_class", "distractor", "harmful"):
                assert token not in events_blob, (case, token)
            for req_path in (case / "requests").glob("*.json"):
                blob = req_path.read_text(encoding="utf-8").lower()
                for token in ("oracle", "expected", "truth", "eval_class", "active", "dormant"):
                    assert token not in blob, (req_path, token)


def test_hidden_truth_never_enters_runtime_sources():
    import project_context.activation as activation_pkg
    import project_context.ledger as ledger_pkg

    for root in (Path(activation_pkg.__file__).parent, Path(ledger_pkg.__file__).parent):
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in ("oracle", "eval_class", "DISTRACTOR", "HARMFUL", "truth.json"):
                assert token not in text, (path.name, token)


def test_no_forbidden_imports_in_activation():
    import project_context.activation as activation_pkg

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
    root = Path(activation_pkg.__file__).parent
    for path in root.glob("*.py"):
        if path.name == "__init__.py":
            continue
        found = set(pattern.findall(path.read_text(encoding="utf-8")))
        assert not (found & denied), f"{path}: {found & denied}"


def test_activation_import_direction():
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

    activation_imports = imports_of("activation")
    assert {m for m in activation_imports if "project_context" in m} <= {
        "project_context.activation.engine",
        "project_context.activation.model",
        "project_context.ledger.events",
        "project_context.ledger.lifecycle",
        "project_context.ledger.projection",
        "project_context.ledger.records",
        "project_context.ledger.relationships",
        "project_context.ledger.store",
    }
    for package in ("compiler", "opencode", "evaluation", "readers", "behavior"):
        target = root / package
        if not target.is_dir():
            continue
        for path in target.rglob("*.py"):
            assert "project_context.activation" not in path.read_text(encoding="utf-8"), path


def test_ledger_projection_behaviour_is_unchanged():
    state = project(load_events(Path("fixtures") / "ledger-v1" / "events.jsonl"))
    assert state.digest() == "cce87221e00ad7cb28e74a9ff72f1ad2a82fc3389a64dc855691138efe69a399"
    assert len(state.items) == 13


def test_compiler_has_no_activation_presence():
    import project_context

    root = Path(project_context.__file__).parent
    for path in (root / "compiler").rglob("*.py"):
        assert "activation" not in path.read_text(encoding="utf-8").lower(), path


def test_opencode_capture_has_no_activation_presence():
    import project_context

    root = Path(project_context.__file__).parent
    for path in (root / "opencode").rglob("*.py"):
        assert "activation" not in path.read_text(encoding="utf-8").lower(), path
    ts_root = Path("integrations") / "opencode" / "src"
    if ts_root.is_dir():
        for path in ts_root.rglob("*.ts"):
            assert "activation" not in path.read_text(encoding="utf-8").lower(), path


# --- CLI ------------------------------------------------------------------------------


def test_cli_activate_and_eval(capsys):
    req = str(CASES / "migration" / "requests" / "edit-migration.json")
    assert cli_main(["ledger", "activate", "migration", "--request-file", req]) == 0
    out = capsys.readouterr().out
    assert "[SYNTHETIC]" in out
    assert "constraint-001" in out and "governed" in out
    assert "truth" not in out.lower()
    assert (
        cli_main(
            [
                "ledger",
                "activate",
                "migration",
                "--request-file",
                req,
                "--mode",
                "scope_only",
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert cli_main(["ledger", "eval-activations", "activation-v1"]) == 0
    summary = capsys.readouterr().out
    assert "typed: precision=1.0 recall=1.0" in summary
    assert cli_main(["ledger", "activate", "nope", "--request-file", req]) != 0
