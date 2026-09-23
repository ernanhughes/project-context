"""Synthetic baseline strategies for compiler-v1. Experiment comparators,
not runtime policy. All operate on default-form records only (the natural
rendering each fixture declares) with whole-item greedy packing.

Strategies: dump, topk, weighted, gated. The staged compiler lives in
compiler/engine.py; the oracle in compiler_eval.py.
"""

from __future__ import annotations

from project_context.compiler.domain import (
    ContextCandidate,
    ContextRequest,
    DecisionTrace,
    TraceDecision,
    TraceEntry,
)
from project_context.compiler.engine import eligibility
from project_context.compiler.policy import CompilerPolicy
from project_context.domain.bundles import ContextBundle
from project_context.evaluation.compiler_eval import _render_bundle, _render_cost_of

PRIORITY_WEIGHTS = {
    "MANDATORY": 4.0,
    "REQUIRED": 3.0,
    "PREFERRED": 2.0,
    "DISCRETIONARY": 1.0,
}


def _defaults(candidates: list[ContextCandidate]) -> list[ContextCandidate]:
    defaults = [c for c in candidates if c.is_default_form]
    if defaults:
        return sorted(defaults, key=lambda c: c.candidate_id)
    # Fallback: cheapest eligible form per identity (never used by the
    # shipped fixtures, which always declare defaults).
    by_identity: dict[str, list[ContextCandidate]] = {}
    for candidate in candidates:
        by_identity.setdefault(candidate.content_identity, []).append(candidate)
    picked = [
        sorted(forms, key=lambda c: (c.token_count, c.candidate_id))[0]
        for forms in by_identity.values()
    ]
    return sorted(picked, key=lambda c: c.candidate_id)


def _trace(
    request: ContextRequest,
    policy_version: str,
    admitted: list[str],
    rest: list[str],
    by_id: dict[str, ContextCandidate],
    reason: str,
) -> DecisionTrace:
    entries: list[TraceEntry] = []
    for cid in admitted:
        candidate = by_id[cid]
        entries.append(
            TraceEntry(
                candidate_id=cid,
                content_identity=candidate.content_identity,
                representation_id=candidate.representation_id,
                decision=TraceDecision.ADMITTED,
                reason_code="admitted",
                reason_detail=reason,
                priority_band=candidate.requirement.value,
                relevance=candidate.relevance,
                marginal_cost=candidate.token_count,
                dependency_closure=(),
                budget_before=0,
                budget_after=0,
                position=None,
            )
        )
    for cid in rest:
        candidate = by_id[cid]
        entries.append(
            TraceEntry(
                candidate_id=cid,
                content_identity=candidate.content_identity,
                representation_id=candidate.representation_id,
                decision=TraceDecision.REJECTED_BUDGET,
                reason_code="not-selected",
                reason_detail=reason,
                priority_band=candidate.requirement.value,
                relevance=candidate.relevance,
                marginal_cost=candidate.token_count,
                dependency_closure=(),
                budget_before=0,
                budget_after=0,
                position=None,
            )
        )
    entries.sort(key=lambda e: e.candidate_id)
    return DecisionTrace(
        request_id=request.request_id, policy_version=policy_version, entries=tuple(entries)
    )


def _finish(
    request: ContextRequest,
    policy_version: str,
    selected: list[ContextCandidate],
    pool: list[ContextCandidate],
    reason: str,
) -> tuple[ContextBundle | None, DecisionTrace, str | None]:
    by_id = {c.candidate_id: c for c in pool}
    admitted = [c.candidate_id for c in selected]
    rest = [c.candidate_id for c in pool if c.candidate_id not in admitted]
    trace = _trace(request, policy_version, admitted, rest, by_id, reason)
    if _render_cost_of(selected, request) > request.usable_token_budget:
        return None, trace, "INSUFFICIENT_BUDGET"
    return (
        _render_bundle(request, selected),
        trace,
        None,
    )


def run_dump(
    request: ContextRequest, candidates: list[ContextCandidate], policy: CompilerPolicy
) -> tuple[ContextBundle | None, DecisionTrace, str | None]:
    """Fixed candidate_id order, render everything, drop trailing whole
    items until the budget fits. May violate every semantic; expected."""
    pool = _defaults(candidates)
    selected = list(pool)
    while selected and _render_cost_of(selected, request) > request.usable_token_budget:
        selected.pop()
    return _finish(request, policy.policy_version, selected, pool, "dump-truncate")


def run_topk(
    request: ContextRequest, candidates: list[ContextCandidate], policy: CompilerPolicy
) -> tuple[ContextBundle | None, DecisionTrace, str | None]:
    """Relevance-ranked greedy on default forms, whole items while fitting."""
    pool = _defaults(candidates)
    ordered = sorted(pool, key=lambda c: (-c.relevance, c.candidate_id))
    selected: list[ContextCandidate] = []
    for candidate in ordered:
        trial = selected + [candidate]
        if _render_cost_of(trial, request) <= request.usable_token_budget:
            selected.append(candidate)
    return _finish(request, policy.policy_version, selected, pool, "topk-greedy")


def run_weighted(
    request: ContextRequest,
    candidates: list[ContextCandidate],
    policy: CompilerPolicy,
    weights: dict[str, float],
) -> tuple[ContextBundle | None, DecisionTrace, str | None]:
    """Pre-registered fixed-weight greedy. Weights come from the experiment
    config, never from hidden truth, and are recorded in run artifacts."""
    pool = _defaults(candidates)

    def score(candidate: ContextCandidate) -> float:
        return (
            weights["relevance"] * candidate.relevance
            + weights["priority"] * PRIORITY_WEIGHTS[candidate.requirement.value]
            - weights["cost"] * (candidate.token_count / max(1, request.usable_token_budget))
        )

    ordered = sorted(pool, key=lambda c: (-score(c), c.candidate_id))
    selected: list[ContextCandidate] = []
    for candidate in ordered:
        trial = selected + [candidate]
        if _render_cost_of(trial, request) <= request.usable_token_budget:
            selected.append(candidate)
    return _finish(request, policy.policy_version, selected, pool, "weighted-greedy")


def run_gated(
    request: ContextRequest, candidates: list[ContextCandidate], policy: CompilerPolicy
) -> tuple[ContextBundle | None, DecisionTrace, str | None]:
    """Hard eligibility gates, then relevance greedy on default forms."""
    pool = _defaults(candidates)
    legal = [c for c in pool if eligibility(c)[0]]
    ordered = sorted(legal, key=lambda c: (-c.relevance, c.candidate_id))
    selected: list[ContextCandidate] = []
    for candidate in ordered:
        trial = selected + [candidate]
        if _render_cost_of(trial, request) <= request.usable_token_budget:
            selected.append(candidate)
    return _finish(request, policy.policy_version, selected, pool, "gated-greedy")


STRATEGIES = ("dump", "topk", "weighted", "gated", "staged", "oracle")
