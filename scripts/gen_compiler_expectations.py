"""Generate tests/compiler_v1_external_expectations.json.

Regression tripwire for the external compiler dependency (NOT book
evidence): admitted ids, tokens, hashes, and failure reasons per
compiler-v1 fixture x budget, produced by the installed
context_compiler package. Regenerate deliberately after reviewed
compiler upgrades, never silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import context_compiler as cc
from context_compiler.conformance import BUDGETS, CONFORMANCE_ROOT, _manifest, _policy
from context_compiler.domain import ContextRequest
from context_compiler.fixtures import (
    load_candidate_file,
    load_fixture_set,
    load_request_file,
)

OUT = Path("tests") / "compiler_v1_external_expectations.json"


def main() -> None:
    manifest = _manifest()
    policy = _policy()
    fixture_set = load_fixture_set(CONFORMANCE_ROOT)
    cases = {}
    for name in sorted(fixture_set):
        candidates = load_candidate_file(fixture_set[name]["candidates"])
        base = load_request_file(fixture_set[name]["request"])
        for budget in BUDGETS:
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
            failure = output.result.failure
            cases[f"{name}/{budget}"] = {
                "success": output.result.success,
                "reason": failure.reason.value if failure else None,
                "blocking_ids": list(failure.blocking_ids) if failure else [],
                "admitted_ids": (
                    [item.id for item in output.bundle.items]
                    if output.bundle
                    else []
                ),
                "bundle_tokens": output.result.bundle_tokens,
                "bundle_hash": output.result.bundle_hash,
            }
    doc = {
        "note": (
            "Regression tripwire for the external project-context-compiler "
            "dependency. NOT book evidence. Regenerate deliberately after "
            "reviewed compiler upgrades."
        ),
        "compiler_package": "project-context-compiler",
        "compiler_version": cc.__version__,
        "cases": cases,
    }
    OUT.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
