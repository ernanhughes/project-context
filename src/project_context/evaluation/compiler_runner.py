"""compiler-v1 suite runner. Deterministic over explicit inputs: fixtures,
strategies, budgets, policy, weights, run_id, timestamp, git commit.
No models, no network. Writes a frozen run directory via runs.artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from project_context.compiler.domain import (
    ContextCandidate,
    ContextRequest,
    DecisionTrace,
)
from project_context.compiler.engine import compile_context
from project_context.compiler.fixtures import (
    load_candidate_file,
    load_fixture_set,
    load_request_file,
)
from project_context.compiler.policy import CompilerPolicy
from project_context.domain.bundles import ContextBundle
from project_context.domain.evaluation import EvaluationLog, EvaluationObservation, Verdict
from project_context.domain.runs import RunManifest
from project_context.evaluation.compiler_baselines import (
    run_dump,
    run_gated,
    run_topk,
    run_weighted,
)
from project_context.evaluation.compiler_eval import (
    EVALUATOR_ID,
    AssemblyTruth,
    evaluate_bundle,
    load_truth_file,
    oracle_assemble,
    run_staged,
)
from project_context.runs.artifacts import validate_artifact, write_artifact

StrategyFn = Callable[
    [ContextRequest, list[ContextCandidate], CompilerPolicy],
    tuple[ContextBundle | None, DecisionTrace, str | None],
]

EXPERIMENT_ID = "compiler-v1"
EXPERIMENT_VERSION = "1"
FIXTURE_ID = "compiler-v1"


def build_strategies(
    weights: dict[str, float],
) -> dict[str, StrategyFn]:
    def weighted(
        request: ContextRequest,
        candidates: list[ContextCandidate],
        policy: CompilerPolicy,
    ) -> tuple[ContextBundle | None, DecisionTrace, str | None]:
        return run_weighted(request, candidates, policy, weights)

    return {
        "dump": run_dump,
        "topk": run_topk,
        "weighted": weighted,
        "gated": run_gated,
        "staged": run_staged,
    }


def run_suite(
    *,
    fixtures_root: Path,
    strategies: list[str],
    budgets: list[str],
    policy: CompilerPolicy,
    weights: dict[str, float],
    fixture_budgets: dict[str, dict[str, int]],
    expected_by_fixture_budget: dict[str, dict[str, dict[str, Any]]],
    fixture_version: str,
    run_id: str,
    timestamp: str,
    git_commit: str,
    vcs_dirty: bool,
    out_root: Path,
) -> Path:
    """Run every fixture x strategy x budget. Returns the run directory."""
    available = build_strategies(weights)
    for name in strategies:
        if name not in available and name != "oracle":
            raise ValueError(f"unknown strategy: {name}")
    fixture_set = load_fixture_file_set(fixtures_root)

    compilations: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    log = EvaluationLog()
    index = 0
    for fixture_name in sorted(fixture_set):
        paths = fixture_set[fixture_name]
        candidates = load_candidate_file(paths["candidates"])
        base_request = load_request_file(paths["request"])
        truth = load_truth_file(fixtures_root / f"{fixture_name}.truth.json")
        for budget_name in budgets:
            budget_tokens = fixture_budgets[fixture_name][budget_name]
            request = ContextRequest(
                request_id=f"{base_request.request_id}-{budget_name}",
                task_id=base_request.task_id,
                usable_token_budget=budget_tokens,
                created_at=base_request.created_at,
                active_scope=base_request.active_scope,
                required_ids=base_request.required_ids,
                policy_version=policy.policy_version,
            )
            for strategy in strategies:
                index += 1
                bundle, trace, reason = run_one(
                    strategy, available, request, candidates, truth, policy
                )
                metrics = evaluate_bundle(
                    bundle=bundle,
                    trace=trace,
                    candidates=candidates,
                    request=request,
                    truth=truth,
                    failure_reason=reason,
                    expected_success=expected_by_fixture_budget[fixture_name][budget_name][
                        "success"
                    ],
                    expected_reason=expected_by_fixture_budget[fixture_name][budget_name]["reason"],
                )
                compilations.append(
                    {
                        "fixture": fixture_name,
                        "strategy": strategy,
                        "budget": budget_name,
                        "budget_tokens": budget_tokens,
                        "request_id": request.request_id,
                        "success": bundle is not None,
                        "reason": reason,
                        "bundle_id": bundle.id if bundle else None,
                        "bundle_tokens": metrics["rendered_tokens"] if bundle is not None else None,
                        "bundle_hash": bundle.content_hash() if bundle else None,
                        "trace": trace.to_dict(),
                    }
                )
                evaluations.append(
                    {
                        "fixture": fixture_name,
                        "strategy": strategy,
                        "budget": budget_name,
                        "budget_tokens": budget_tokens,
                        "success": bundle is not None,
                        "reason": reason,
                        **metrics,
                    }
                )
                expected = expected_by_fixture_budget[fixture_name][budget_name]
                observed_ok = (bundle is not None) == expected["success"] and (
                    expected["success"]
                    or reason == expected.get("reason")
                    or expected.get("reason") is None
                )
                log = log.append(
                    EvaluationObservation(
                        id=f"obs-{index:04d}",
                        target_type="compiler-run",
                        target_id=f"{fixture_name}/{strategy}/{budget_name}",
                        metric="compiler-v1:compile-status",
                        value=f"{'success' if bundle is not None else 'failure:' + str(reason)}",
                        verdict=Verdict.PASS if observed_ok else Verdict.FAIL,
                        evidence=(
                            f"expected success={expected['success']}; "
                            f"must_recall={metrics['must_recall']}; "
                            f"illegal={metrics['illegal_admission']}; "
                            f"tokens={metrics['rendered_tokens']}"
                        ),
                        evaluator=EVALUATOR_ID,
                        created_at=timestamp,
                    )
                )

    manifest = RunManifest(
        run_id=run_id,
        experiment_id=EXPERIMENT_ID,
        experiment_version=EXPERIMENT_VERSION,
        git_commit=git_commit,
        timestamp=timestamp,
        provider="synthetic",
        model="synthetic-deterministic-v1",
        evidence_class="synthetic",
        policy_version=policy.policy_version,
        fixture_id=FIXTURE_ID,
        fixture_version=fixture_version,
        environment=(
            ("token_mode", "estimate_tokens-words1.3"),
            ("vcs_dirty", str(vcs_dirty)),
        ),
    )
    results = {
        "experiment": EXPERIMENT_ID,
        "experiment_version": EXPERIMENT_VERSION,
        "policy_version": policy.policy_version,
        "fixture_version": fixture_version,
        "strategies": strategies,
        "budgets": budgets,
        "weights": weights,
        "evaluations": evaluations,
    }
    readme = (
        f"# compiler-v1 run {run_id}\n\n"
        "SYNTHETIC — NOT A BOOK RESULT. Deterministic synthetic compiler\n"
        "experiment: no models, no network, no ecological corpus.\n\n"
        f"Question: can a deterministic staged compiler produce policy-valid\n"
        "bundles with higher required-information coverage and fewer\n"
        "illegal/harmful admissions than dump, top-k, weighted, and\n"
        "hard-gated greedy baselines?\n\n"
        f"Strategies: {', '.join(strategies)}. Budgets: {', '.join(budgets)}.\n"
        f"Policy: {policy.policy_version}. Fixtures: {FIXTURE_ID} v{fixture_version}.\n"
        "See experiments/compiler-v1/spec.yaml for the frozen contract.\n"
    )
    run_dir = write_artifact(out_root, manifest, log, results, readme_text=readme)
    (run_dir / "compilation.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in compilations),
        encoding="utf-8",
    )
    problems = validate_artifact(run_dir)
    if problems:
        raise ValueError(f"run artifact invalid: {problems}")
    return run_dir


def run_one(
    strategy: str,
    available: dict[str, StrategyFn],
    request: ContextRequest,
    candidates: list[ContextCandidate],
    truth: AssemblyTruth,
    policy: CompilerPolicy,
) -> tuple[ContextBundle | None, DecisionTrace, str | None]:
    if strategy == "oracle":
        return oracle_assemble(request, candidates, truth, policy)
    if strategy == "staged":
        output = compile_context(request, candidates, policy)
        reason = output.result.failure.reason.value if output.result.failure else None
        return output.bundle, output.result.trace, reason
    return available[strategy](request, candidates, policy)


def load_fixture_file_set(root: Path) -> dict[str, dict[str, Path]]:
    return load_fixture_set(root)
