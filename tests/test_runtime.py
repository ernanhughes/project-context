"""Stage 6D runtime tests: render, inject, observe, reconcile.

Nothing here calls models or network. Oracle truth files are loaded only
to assert outcomes; runtime code never reads them. The synthetic
observer is the existing V2 ingester, unchanged.
"""

import copy
import json
import re
from pathlib import Path

import pytest

from project_context.cli.main import main as cli_main
from project_context.domain.bundles import ContextBundle
from project_context.opencode.bridge import validate_record
from project_context.opencode.ingest import ingest_record
from project_context.runtime.inject import RUNTIME_MODE, inject
from project_context.runtime.model import (
    BLOCK_CLOSE,
    BLOCK_OPEN,
    INJECTION_LOCATION,
    InjectionReceipt,
    ReconciliationResult,
    RenderedBlock,
    RenderPolicy,
    RuntimeError,
)
from project_context.runtime.reconcile import reconcile
from project_context.runtime.render import render_bundle

SUITE = Path("fixtures") / "runtime-v1"
POLICY = RenderPolicy()


def _request(name="ordinary.json"):
    return json.loads((SUITE / "requests" / name).read_text(encoding="utf-8"))


def _bundle(name):
    return ContextBundle.from_dict(
        json.loads((SUITE / "bundles" / name).read_text(encoding="utf-8"))
    )


def _truth():
    return json.loads((SUITE / "truth.json").read_text(encoding="utf-8"))["cases"]


def _loop(case, request_id="rt-test"):
    spec = _truth()[case]
    bundle = _bundle(spec["bundle"])
    request = _request(spec["request"])
    rendered = render_bundle(bundle, POLICY)
    injected, receipt = inject(
        request,
        rendered,
        request_id=request_id,
        mode=RUNTIME_MODE,
        candidate_ids=tuple(item.id for item in bundle.items),
    )
    return bundle, request, rendered, injected, receipt


# --- renderer ---------------------------------------


def test_renderer_is_deterministic():
    bundle = _bundle("mixed.bundle.json")
    first = render_bundle(bundle, POLICY)
    second = render_bundle(bundle, POLICY)
    assert first.to_dict() == second.to_dict()
    assert RenderedBlock.from_dict(first.to_dict()) == first
    assert RenderPolicy.from_dict(POLICY.to_dict()) == POLICY


def test_empty_selection_renders_empty_and_injects_nothing():
    bundle, request, rendered, injected, receipt = _loop("a-empty")
    assert rendered.item_count == 0 and rendered.text == ""
    assert receipt.status == "noop_empty"
    assert injected == request
    assert receipt.pre_digest == receipt.post_digest
    result = reconcile(receipt, rendered, injected)
    assert result.status == "pass"
    assert result.checks["markers_absent"] is True


def test_selected_candidate_renders_exactly_once():
    _, _, rendered, _, _ = _loop("b-one-ordinary")
    assert rendered.text.count("Fix path handling on all platforms.") == 1
    assert rendered.text.startswith(BLOCK_OPEN) and rendered.text.endswith(BLOCK_CLOSE)


def test_unselected_candidate_is_never_rendered():
    _, _, rendered, _, _ = _loop("e-rejected-absent")
    for absent in _truth()["e-rejected-absent"]["absent_contents"]:
        assert absent not in rendered.text


def test_mixed_bundle_preserves_compiler_order():
    _, _, rendered, _, _ = _loop("d-mixed")
    bodies = _truth()["d-mixed"]["expect_order"]
    positions = [rendered.text.index(body) for body in bodies]
    assert positions == sorted(positions)


def test_epistemic_labels_survive_rendering():
    _, _, rendered, _, _ = _loop("c-ledger-pending")
    assert "[PENDING VERIFICATION]" in rendered.text
    assert "The race condition appears fixed but has not been verified." in rendered.text
    _, _, mixed, _, _ = _loop("d-mixed")
    assert "[Unverified assumption]" in mixed.text
    assert "[CONSTRAINT]" in mixed.text


def test_machine_metadata_stays_out_of_model_block():
    for case in ("b-one-ordinary", "c-ledger-pending", "d-mixed"):
        _, _, rendered, _, _ = _loop(case)
        lowered = rendered.text.lower()
        for token in ("ledger-item", "activation-policy", "event-", "digest", "run-", "sha256"):
            assert token not in lowered, (case, token)


def test_render_sees_only_the_bundle():
    bundle = _bundle("one-ordinary.bundle.json")
    rendered = render_bundle(bundle, POLICY)
    assert rendered.item_count == 1
    assert rendered.bundle_id == bundle.id


# --- injection --------------------------------------


def test_request_digests_differ_only_when_injection_occurs():
    _, request, _, injected, receipt = _loop("b-one-ordinary")
    assert receipt.status == "injected"
    assert receipt.pre_digest != receipt.post_digest
    assert request != injected
    assert receipt.injection_location == INJECTION_LOCATION == "system-append"
    assert receipt.injected_bytes == len(injected["system"][-1]["text"].encode("utf-8"))
    _, _, _, untouched, noop = _loop("a-empty")
    assert untouched["system"] == _request()["system"]


def test_repeated_injection_is_idempotent():
    bundle = _bundle("one-ordinary.bundle.json")
    request = _request()
    rendered = render_bundle(bundle, POLICY)
    once, first = inject(request, rendered, request_id="rt-1", mode=RUNTIME_MODE)
    twice, second = inject(once, rendered, request_id="rt-1", mode=RUNTIME_MODE)
    assert first.status == "injected"
    assert second.status == "noop_idempotent"
    assert once == twice
    assert second.pre_digest == second.post_digest == first.post_digest


def test_conflicting_block_fails_without_mutation():
    _, request, rendered, injected, receipt = _loop("g-conflict")
    assert receipt.status == "failed"
    assert receipt.failure_reason == "injection_conflict"
    assert injected == request
    assert receipt.pre_digest == receipt.post_digest


def test_injection_requires_explicit_opt_in():
    bundle = _bundle("one-ordinary.bundle.json")
    rendered = render_bundle(bundle, POLICY)
    for bad_mode in ("observe", "", "auto", "inject"):
        with pytest.raises(RuntimeError) as exc:
            inject(_request(), rendered, request_id="rt-x", mode=bad_mode)
        assert exc.value.code == "opt_in_required"


def test_malformed_request_fails_loudly():
    bundle = _bundle("one-ordinary.bundle.json")
    rendered = render_bundle(bundle, POLICY)
    with pytest.raises(RuntimeError) as exc:
        inject(
            {"system": "not-a-list", "messages": [], "tools": {}, "options": {}},
            rendered,
            request_id="rt-x",
            mode=RUNTIME_MODE,
        )
    assert exc.value.code == "unsupported_request_shape"


def test_receipt_carries_lineage_and_round_trips():
    _, _, _, _, receipt = _loop("d-mixed")
    assert receipt.candidate_ids == (
        "ledger-constraint-001-111111111111",
        "ord-mand",
        "ledger-assumption-001-222222222222",
    )
    assert receipt.render_policy_id == "runtime-render-v1"
    assert InjectionReceipt.from_dict(receipt.to_dict()) == receipt


# --- observation and reconciliation -----------------


def test_observer_captures_post_injection_request():
    _, _, _, injected, _ = _loop("d-mixed")
    assert validate_record(injected) == []
    bundle, _ = ingest_record(injected)
    assert len(bundle.items) == 4  # two original system blocks + message + runtime block


def test_reconciliation_passes_on_correct_request():
    for case in ("b-one-ordinary", "c-ledger-pending", "d-mixed", "e-rejected-absent"):
        _, _, rendered, injected, receipt = _loop(case)
        result = reconcile(receipt, rendered, injected)
        assert result.status == "pass", case
        assert all(result.checks.values()), case
        assert ReconciliationResult.from_dict(result.to_dict()) == result


def _tamper(injected, mode):
    tampered = copy.deepcopy(injected)
    system = tampered["system"]
    if mode == "drop":
        tampered["system"] = [b for b in system if BLOCK_OPEN not in b.get("text", "")]
    elif mode == "duplicate":
        block = next(b for b in system if BLOCK_OPEN in b.get("text", ""))
        tampered["system"] = [*system, copy.deepcopy(block)]
    elif mode == "reorder":
        idx = next(i for i, b in enumerate(system) if BLOCK_OPEN in b.get("text", ""))
        block = system.pop(idx)
        tampered["system"] = [block, *system]
    elif mode == "extra":
        tampered["system"] = [*system, {"type": "text", "text": "Sneaky extra instruction."}]
    return tampered


def test_reconciliation_fails_on_tampered_requests():
    _, _, rendered, injected, receipt = _loop("b-one-ordinary")
    dropped = reconcile(receipt, rendered, _tamper(injected, "drop"))
    assert dropped.status == "fail"
    assert dropped.checks["markers_present"] is False
    duplicated = reconcile(receipt, rendered, _tamper(injected, "duplicate"))
    assert duplicated.status == "fail"
    assert duplicated.checks["block_once"] is False
    assert duplicated.duplication_count == 1
    reordered = reconcile(receipt, rendered, _tamper(injected, "reorder"))
    assert reordered.status == "fail"
    assert reordered.checks["order_preserved"] is False
    extra = reconcile(receipt, rendered, _tamper(injected, "extra"))
    assert extra.status == "fail"
    assert extra.checks["integrity_match"] is False


def test_privacy_trap_content_cannot_leak():
    _, _, rendered, _, _ = _loop("j-privacy-trap")
    for forbidden in _truth()["j-privacy-trap"]["forbidden_contents"]:
        assert forbidden not in rendered.text


def test_dormant_unknown_state_cannot_reach_runtime():
    from project_context.activation.engine import activate
    from project_context.activation.model import ActivationPolicy, ActivationRequest

    case_dir = Path("fixtures") / "activation-v1" / "cases" / "missing-metadata"
    from project_context.ledger.projection import project
    from project_context.ledger.store import load_events

    state = project(load_events(case_dir / "events.jsonl"))
    request = ActivationRequest.from_dict(
        json.loads((case_dir / "requests" / "bare.json").read_text(encoding="utf-8"))
    )
    result = activate(state, request, ActivationPolicy())
    assert result.active_ids() == ()
    from project_context.ledger_adapter.adapter import adapt

    candidates, _ = adapt(state, result)
    assert candidates == ()


# --- separation -----------------------------------------


def test_runtime_consumes_bundles_not_ledger_state():
    import project_context.runtime as runtime_pkg

    root = Path(runtime_pkg.__file__).parent
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "project_context.ledger" not in text, path
        assert "project_context.activation" not in text, path
        assert "project_context.compiler" not in text, path
        assert "project_context.evaluation" not in text, path
        assert "project_context.behavior" not in text, path
        assert "project_context.readers" not in text, path


def test_no_forbidden_imports_in_runtime():
    import project_context.runtime as runtime_pkg

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
    root = Path(runtime_pkg.__file__).parent
    for path in root.glob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        found = set(pattern.findall(text))
        assert not (found & denied), f"{path}: {found & denied}"
        # The only opencode touchpoint is the read-only bridge
        # (validation + integrity hashing), never the ingester or hooks.
        for line in text.splitlines():
            if "project_context.opencode" in line:
                assert "bridge" in line, (path, line)


def test_observer_package_has_no_runtime_presence():
    ts_observer = Path("integrations") / "opencode"
    for path in (ts_observer / "src").rglob("*.ts"):
        blob = path.read_text(encoding="utf-8")
        assert "opencode-runtime" not in blob, path
        assert "context-runtime-injection" not in blob, path
        assert "PROJECT_CONTEXT_RUNTIME" not in blob, path
    assert "opencode-runtime" not in (ts_observer / "package.json").read_text(encoding="utf-8")
    import project_context.opencode as opencode_pkg

    for path in Path(opencode_pkg.__file__).parent.rglob("*.py"):
        assert "project_context.runtime" not in path.read_text(encoding="utf-8"), path


def test_runtime_package_does_not_mutate_observer_inputs():
    bundle = _bundle("one-ordinary.bundle.json")
    request = _request()
    snapshot = copy.deepcopy(request)
    rendered = render_bundle(bundle, POLICY)
    inject(request, rendered, request_id="rt-x", mode=RUNTIME_MODE)
    reconcile(
        inject(request, rendered, request_id="rt-x", mode=RUNTIME_MODE)[1],
        rendered,
        request,
    )
    assert request == snapshot


def test_observer_remains_read_only():
    ts_observer = Path("integrations") / "opencode" / "src" / "index.ts"
    blob = ts_observer.read_text(encoding="utf-8")
    assert "event.result" not in blob or "NEVER set" in blob
    assert "event.system =" not in blob
    assert "event.messages =" not in blob
    assert "event.tools =" not in blob
    assert "event.options =" not in blob


def test_runtime_ts_owns_mutation_alone():
    ts_runtime = Path("integrations") / "opencode-runtime" / "src" / "runtime.ts"
    assert ts_runtime.is_file()
    blob = ts_runtime.read_text(encoding="utf-8")
    assert "UNVERIFIED" in blob
    assert "PROJECT_CONTEXT_RUNTIME" in blob
    ts_observer_src = Path("integrations") / "opencode" / "src"
    for path in ts_observer_src.rglob("*.ts"):
        assert "opencode-runtime" not in path.read_text(encoding="utf-8"), path
    py_runtime = Path("src") / "project_context" / "runtime"
    for path in py_runtime.rglob("*.py"):
        assert "opencode-runtime" not in path.read_text(encoding="utf-8"), path


# --- stability of earlier stages --------------------------


def test_stage_boundaries_still_hold():
    from project_context.activation.engine import activate as activate_fn
    from project_context.activation.model import ActivationPolicy
    from project_context.ledger.projection import project as project_fn
    from project_context.ledger.store import load_events as load_fn

    state = project_fn(load_fn(Path("fixtures") / "ledger-v1" / "events.jsonl"))
    assert state.digest() == "cce87221e00ad7cb28e74a9ff72f1ad2a82fc3389a64dc855691138efe69a399"
    case_dir = Path("fixtures") / "activation-v1" / "cases" / "migration"
    case_state = project_fn(load_fn(case_dir / "events.jsonl"))
    truth = json.loads((case_dir / "truth.json").read_text(encoding="utf-8"))["requests"]
    for req_path in sorted((case_dir / "requests").glob("*.json")):
        from project_context.activation.model import ActivationRequest

        request = ActivationRequest.from_dict(json.loads(req_path.read_text(encoding="utf-8")))
        result = activate_fn(case_state, request, ActivationPolicy())
        for decision in result.decisions:
            want = truth[request.request_id][decision.item_id]
            assert decision.state.value == want["state"]
    from project_context.compiler.domain import ContextRequest
    from project_context.compiler.engine import compile_context
    from project_context.compiler.fixtures import load_candidate_file
    from project_context.compiler.policy import CompilerPolicy

    case = Path("fixtures") / "adapter-v1" / "cases" / "a-admitted"
    from project_context.ledger_adapter.adapter import adapt_case

    adapter_state = project_fn(load_fn(case / "events.jsonl"))
    from project_context.activation.model import ActivationRequest as AR

    areq = AR.from_dict(json.loads((case / "request.json").read_text(encoding="utf-8")))
    pool, _ = adapt_case(
        adapter_state,
        activate_fn(adapter_state, areq, ActivationPolicy()),
        load_candidate_file(case / "ordinary.candidates.json"),
    )
    creq = ContextRequest.from_dict(json.loads((case / "compile.json").read_text(encoding="utf-8")))
    out = compile_context(
        creq,
        list(pool),
        CompilerPolicy.from_dict(
            json.loads(
                (
                    Path("experiments") / "compiler-v1" / "policies" / "compiler-policy-v1.json"
                ).read_text(encoding="utf-8")
            )
        ),
    )
    assert out.result.success
    assert {e.candidate_id for e in out.result.trace.entries if e.decision.value == "ADMITTED"} >= {
        "ord-mand"
    }


def test_fixture_runtime_files_carry_no_oracle_tokens():
    for case in [p for p in (SUITE / "bundles").glob("*.json")]:
        blob = case.read_text(encoding="utf-8").lower()
        for token in ("oracle", "truth", "eval_class", "distractor", "harmful"):
            assert token not in blob, (case, token)
    for name in ("ordinary.json", "conflict.json"):
        blob = (SUITE / "requests" / name).read_text(encoding="utf-8").lower()
        for token in ("oracle", "truth", "eval_class", "runtime block", "sk-live", "sess-secret"):
            assert token not in blob, (name, token)


# --- CLI ------------------------------------------------


def test_cli_runtime_demo(capsys):
    assert cli_main(["runtime", "demo", "d-mixed"]) == 0
    out = capsys.readouterr().out
    assert "[SYNTHETIC]" in out
    assert "RECONCILIATION" in out and "PASS" in out
    assert "truth" not in out.lower()
    assert cli_main(["runtime", "demo", "d-mixed", "--format", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["reconciliation"]["status"] == "pass"
    assert cli_main(["runtime", "demo", "nope"]) == 2
