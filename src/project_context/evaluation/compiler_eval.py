"""Hidden assembly truth, oracle assembler, and bundle-quality evaluator.

EVALUATOR-ONLY TERRITORY. Production compiler code (compiler/) must never
import this module; a test pins the import direction. Truth files live
beside fixture files as `*.truth.json` and are loaded only here.

Truth file shape::

    {
      "identity_truth": {
        "<content_identity>": {
          "eval_class": "must|should|optional|distractor|harmful",
          "min_representation": "<representation_id>"
        }
      },
      "expected": {"success": true} | {"success": false, "reason": "<code>"}
    }
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from project_context.compiler.domain import (
    ContextCandidate,
    ContextRequest,
    DecisionTrace,
    RequirementClass,
    TraceDecision,
    TraceEntry,
)
from project_context.compiler.engine import (
    _SEPARATOR_TOKENS,
    _closure_ids,
    _decoration_tokens,
    compile_context,
    eligibility,
    header_tokens,
)
from project_context.compiler.policy import CompilerPolicy
from project_context.domain.bundles import ContextBundle, build_bundle
from project_context.domain.items import make_item

EVALUATOR_ID = "project_context.evaluation.compiler_v1"
EVAL_CLASSES = ("must", "should", "optional", "distractor", "harmful")


@dataclasses.dataclass(frozen=True)
class AssemblyTruth:
    identity_truth: dict[str, dict[str, str]]
    expected_success: bool
    expected_reason: str | None

    def eval_class(self, content_identity: str) -> str:
        return self.identity_truth.get(content_identity, {}).get("eval_class", "optional")

    def min_representation(self, content_identity: str) -> str | None:
        return self.identity_truth.get(content_identity, {}).get("min_representation")


def load_truth_file(path: Path) -> AssemblyTruth:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"bad truth file (need object): {path}")
    identity_truth = raw.get("identity_truth", {})
    for identity, spec in identity_truth.items():
        if spec.get("eval_class") not in EVAL_CLASSES:
            raise ValueError(f"bad eval_class for {identity} in {path}")
    expected = raw.get("expected", {"success": True})
    return AssemblyTruth(
        identity_truth={k: dict(v) for k, v in identity_truth.items()},
        expected_success=bool(expected.get("success", True)),
        expected_reason=expected.get("reason"),
    )


def _render_cost_of(records: list[ContextCandidate], request: ContextRequest | None = None) -> int:
    total = sum(r.token_count + _decoration_tokens(r) for r in records)
    total += max(0, len(records) - 1) * _SEPARATOR_TOKENS
    if request is not None:
        total += header_tokens(request)
    return total


def _render_bundle(request: ContextRequest, selected: list[ContextCandidate]) -> ContextBundle:
    role_rank = {
        "instruction": 0,
        "task": 1,
        "state": 2,
        "evidence": 3,
        "support": 4,
        "tool": 5,
    }
    ordered = sorted(selected, key=lambda c: (role_rank.get(c.order_role, 99), c.candidate_id))
    made = [
        make_item(id=c.candidate_id, source=c.source_kind, kind=c.kind, content=c.content)
        for c in ordered
    ]
    exacted = [
        dataclasses.replace(item, token_count=c.token_count + _decoration_tokens(c))
        for item, c in zip(made, ordered)
    ]
    return build_bundle(
        exacted,
        bundle_id=f"{request.request_id}-bundle",
        created_at=request.created_at,
        evidence_class="synthetic",
    )


def _trace_for(
    request: ContextRequest,
    policy_version: str,
    admitted: list[str],
    rejected: list[tuple[str, str]],
    by_id: dict[str, ContextCandidate],
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
                reason_detail="baseline admission",
                priority_band=candidate.requirement.value,
                relevance=candidate.relevance,
                marginal_cost=candidate.token_count,
                dependency_closure=(),
                budget_before=0,
                budget_after=0,
                position=None,
            )
        )
    for cid, reason in rejected:
        candidate = by_id.get(cid)
        entries.append(
            TraceEntry(
                candidate_id=cid,
                content_identity=candidate.content_identity if candidate else cid,
                representation_id=candidate.representation_id if candidate else "?",
                decision=TraceDecision.REJECTED_BUDGET,
                reason_code=reason,
                reason_detail="baseline rejection",
                priority_band=candidate.requirement.value if candidate else "",
                relevance=candidate.relevance if candidate else 0.0,
                marginal_cost=candidate.token_count if candidate else 0,
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


def oracle_assemble(
    request: ContextRequest,
    candidates: list[ContextCandidate],
    truth: AssemblyTruth,
    policy: CompilerPolicy,
) -> tuple[ContextBundle | None, DecisionTrace, str | None]:
    """Perfect-knowledge ceiling. Obeys the same hard gates; chooses
    minimum sufficient legal bundles from hidden truth. Returns
    (bundle_or_none, trace, failure_reason_or_none)."""
    by_id = {c.candidate_id: c for c in candidates}
    missing = sorted(set(request.required_ids) - set(by_id))
    if missing:
        trace = _trace_for(
            request, policy.policy_version, [], [(m, "missing") for m in missing], by_id
        )
        return None, trace, "REQUIRED_SOURCE_UNAVAILABLE"

    forms: dict[str, list[ContextCandidate]] = {}
    for candidate in candidates:
        eligible, _, _ = eligibility(candidate)
        if eligible:
            forms.setdefault(candidate.content_identity, []).append(candidate)

    # Mandatory identities must all be satisfiable.
    for identity in sorted(
        {c.content_identity for c in candidates if c.requirement == RequirementClass.MANDATORY}
    ):
        if not forms.get(identity):
            trace = _trace_for(request, policy.policy_version, [], [], by_id)
            return None, trace, "NO_LEGAL_REPRESENTATION"

    selected: list[ContextCandidate] = []
    selected_identities: set[str] = set()

    def take(identity: str, representation_id: str | None) -> bool:
        options = forms.get(identity, [])
        if not options:
            return False
        if representation_id is not None:
            narrowed = [c for c in options if c.representation_id == representation_id]
            if narrowed:
                options = narrowed
        option = sorted(options, key=lambda c: (c.token_count, c.candidate_id))[0]
        starters = [option.candidate_id]
        if option.group_id and option.group_required:
            starters = sorted(
                c.candidate_id
                for c in candidates
                if c.group_id == option.group_id and c.group_required
            )
        wanted: list[str] = []
        seen: set[str] = set()
        for start in starters:
            for node in _closure_ids(start, by_id):
                if node not in seen and node not in [c.candidate_id for c in selected]:
                    seen.add(node)
                    wanted.append(node)
        trial = selected + [by_id[n] for n in wanted]
        if _render_cost_of(trial, request) <= request.usable_token_budget:
            selected.extend([by_id[n] for n in wanted])
            selected_identities.update(by_id[n].content_identity for n in wanted)
            return True
        return False

    # MUST identities at minimum sufficient representation.
    for identity in sorted(truth.identity_truth):
        if truth.eval_class(identity) != "must":
            continue
        if identity in selected_identities:
            continue
        if not take(identity, truth.min_representation(identity)):
            trace = _trace_for(
                request,
                policy.policy_version,
                [c.candidate_id for c in selected],
                [],
                by_id,
            )
            return None, trace, "INSUFFICIENT_BUDGET"
    # SHOULD identities where affordable.
    for identity in sorted(truth.identity_truth):
        if truth.eval_class(identity) != "should":
            continue
        if identity in selected_identities:
            continue
        take(identity, truth.min_representation(identity))

    bundle = _render_bundle(request, selected)
    if _render_cost_of(selected, request) > request.usable_token_budget:
        trace = _trace_for(
            request, policy.policy_version, [c.candidate_id for c in selected], [], by_id
        )
        return None, trace, "INSUFFICIENT_BUDGET"
    admitted = [c.candidate_id for c in selected]
    rejected = [
        (c.candidate_id, "not-selected") for c in candidates if c.candidate_id not in admitted
    ]
    return bundle, _trace_for(request, policy.policy_version, admitted, rejected, by_id), None


def evaluate_bundle(
    *,
    bundle: ContextBundle | None,
    trace: DecisionTrace,
    candidates: list[ContextCandidate],
    request: ContextRequest,
    truth: AssemblyTruth,
    failure_reason: str | None,
    expected_success: bool,
    expected_reason: str | None,
) -> dict[str, Any]:
    """Deterministic bundle-quality scoring with exact denominators. No
    global score; every dimension reported separately."""
    by_id = {c.candidate_id: c for c in candidates}
    admitted_ids = [item.id for item in bundle.items] if bundle is not None else []
    admitted_identities = [by_id[cid].content_identity for cid in admitted_ids if cid in by_id]

    def identities_of(eval_class: str) -> list[str]:
        return sorted(
            identity
            for identity, spec in truth.identity_truth.items()
            if spec.get("eval_class") == eval_class
        )

    must = identities_of("must")
    should = identities_of("should")
    must_hit = [i for i in must if i in admitted_identities]
    should_hit = [i for i in should if i in admitted_identities]
    distractor_hit = sum(1 for i in admitted_identities if truth.eval_class(i) == "distractor")
    harmful_hit = sum(1 for i in admitted_identities if truth.eval_class(i) == "harmful")
    good = len(must_hit) + len(should_hit)

    illegal = 0
    scope_violations = 0
    freshness_violations = 0
    authority_violations = 0
    floor_violations = 0
    for cid in admitted_ids:
        candidate = by_id.get(cid)
        if candidate is None:
            illegal += 1
            continue
        eligible, code, _ = eligibility(candidate)
        if not eligible:
            illegal += 1
            if code == "scope_ineligible":
                scope_violations += 1
            elif code == "freshness_ineligible":
                freshness_violations += 1
            elif code == "authority_ineligible":
                authority_violations += 1
            elif code == "illegal_representation":
                floor_violations += 1

    # Dependency + group integrity from the trace's admitted set.
    dependency_violations = 0
    admitted_set = set(admitted_ids)
    for cid in admitted_ids:
        candidate = by_id.get(cid)
        if candidate is None:
            continue
        for dep in candidate.depends_on:
            if dep not in admitted_set:
                dependency_violations += 1
    group_violations = 0
    groups: dict[str, list[str]] = {}
    for candidate in candidates:
        if candidate.group_id and candidate.group_required:
            groups.setdefault(candidate.group_id, []).append(candidate.candidate_id)
    for members in groups.values():
        inside = [m for m in members if m in admitted_set]
        if inside and len(inside) != len(members):
            group_violations += 1

    rendered = (
        _render_cost_of([by_id[cid] for cid in admitted_ids if cid in by_id], request)
        if bundle is not None
        else 0
    )
    budget_compliant = rendered <= request.usable_token_budget
    if expected_success:
        status_correct = bundle is not None and failure_reason is None
    else:
        status_correct = bundle is None and (
            failure_reason == expected_reason or expected_reason is None
        )

    total_admitted_identities = len(set(admitted_identities))
    precision = (good / total_admitted_identities) if total_admitted_identities else 1.0

    return {
        "budget_compliant": budget_compliant,
        "status_correct": status_correct,
        "must_recall": _ratio(len(must_hit), len(must)),
        "should_recall": _ratio(len(should_hit), len(should)),
        "must_total": len(must),
        "should_total": len(should),
        "precision": precision,
        "distractor_admission": distractor_hit,
        "harmful_admission": harmful_hit,
        "illegal_admission": illegal,
        "scope_violations": scope_violations,
        "freshness_violations": freshness_violations,
        "authority_violations": authority_violations,
        "floor_violations": floor_violations,
        "dependency_violations": dependency_violations,
        "group_violations": group_violations,
        "rendered_tokens": rendered,
        "budget_slack": request.usable_token_budget - rendered if bundle is not None else None,
        "under_admission": (len(must) - len(must_hit)) + (len(should) - len(should_hit)),
        "over_admission": total_admitted_identities - good,
    }


def _ratio(hit: int, total: int) -> float | None:
    if total == 0:
        return None
    return hit / total


def run_staged(
    request: ContextRequest,
    candidates: list[ContextCandidate],
    policy: CompilerPolicy,
) -> tuple[ContextBundle | None, DecisionTrace, str | None]:
    """Thin adapter so the runner treats staged like any strategy."""
    output = compile_context(request, candidates, policy)
    reason = output.result.failure.reason.value if output.result.failure else None
    return output.bundle, output.result.trace, reason
