"""External compiler dependency: parity and shim tests.

`project-context` consumes context assembly from the installed
`project-context-compiler` package. These tests prove:

1. the installed package reproduces the frozen compiler-v1
   expectations (admitted ids, tokens, hashes, failure reasons);
2. the `project_context.compiler` shim contains no implementation
   (re-exports only) and resolves to the canonical objects.
"""

import json
from pathlib import Path

import context_compiler as cc
from context_compiler.conformance import BUDGETS, CONFORMANCE_ROOT, _manifest, _policy
from context_compiler.domain import ContextRequest
from context_compiler.engine import CompileOutput, compile_context, eligibility
from context_compiler.fixtures import (
    load_candidate_file,
    load_fixture_set,
    load_request_file,
)
from context_compiler.policy import CompilerPolicy as CanonicalPolicy

import project_context.compiler.domain as shim_domain
import project_context.compiler.engine as shim_engine
import project_context.compiler.fixtures as shim_fixtures
import project_context.compiler.policy as shim_policy

EXPECTATIONS = Path(__file__).parent / "compiler_v1_external_expectations.json"


def _expected():
    return json.loads(EXPECTATIONS.read_text(encoding="utf-8"))


def test_external_package_matches_tripwire():
    doc = _expected()
    assert doc["compiler_package"] == "project-context-compiler"
    manifest = _manifest()
    policy = _policy()
    fixture_set = load_fixture_set(CONFORMANCE_ROOT)
    assert len(doc["cases"]) == 42
    for name in sorted(fixture_set):
        candidates = load_candidate_file(fixture_set[name]["candidates"])
        base = load_request_file(fixture_set[name]["request"])
        for budget in BUDGETS:
            tag = f"{name}/{budget}"
            request = ContextRequest(
                request_id=f"{base.request_id}-{budget}",
                task_id=base.task_id,
                usable_token_budget=manifest["budgets"][name][budget],
                created_at=base.created_at,
                active_scope=base.active_scope,
                required_ids=base.required_ids,
                policy_version=base.policy_version,
            )
            output = cc.compile_context(request, candidates, policy)
            want = doc["cases"][tag]
            failure = output.result.failure
            assert output.result.success == want["success"], tag
            assert (failure.reason.value if failure else None) == want["reason"], tag
            assert (list(failure.blocking_ids) if failure else []) == want[
                "blocking_ids"
            ], tag
            assert (
                [item.id for item in output.bundle.items] if output.bundle else []
            ) == want["admitted_ids"], tag
            assert output.result.bundle_tokens == want["bundle_tokens"], tag
            assert output.result.bundle_hash == want["bundle_hash"], tag


def test_external_package_version_recorded():
    doc = _expected()
    assert isinstance(doc["compiler_version"], str) and doc["compiler_version"]
    assert cc.__version__


def test_shim_resolves_to_canonical_objects():
    assert shim_domain.ContextCandidate is cc.ContextCandidate
    assert shim_domain.ContextRequest is cc.ContextRequest
    assert shim_domain.CompilationResult is cc.CompilationResult
    assert shim_policy.CompilerPolicy is CanonicalPolicy
    assert shim_engine.compile_context is compile_context
    assert shim_engine.CompileOutput is CompileOutput
    assert shim_engine.eligibility is eligibility
    assert shim_fixtures.load_candidate_file is load_candidate_file
    assert shim_fixtures.load_request_file is load_request_file


def test_shim_files_contain_no_implementation():
    for path in (Path(shim_domain.__file__).parent).glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "def " not in text, path
        assert "class " not in text, path
        assert "context_compiler" in text, path
