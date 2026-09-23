"""Deterministic staged compiler. Pure function over explicit inputs.

Pipeline (book Chapter 22):

```text
validate inputs
  -> explicit required-source check
  -> hard eligibility gates (scope/freshness/authority/floor)
  -> mandatory admission (cheapest legal form, groups atomic)
  -> required admission (bands in order, groups atomic)
  -> preferred/discretionary greedy admission (earn rule + coverage)
  -> alternative-form closeout
  -> deterministic ordering
  -> render + exact budget validation + repair
  -> trace + bundle-or-failure
```

Purity: no file IO, no clock, no randomness, no network, no models.
Inputs are never mutated. Identical inputs yield identical outputs.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from project_context.compiler.domain import (
    CompilationResult,
    CompileFailure,
    ContextCandidate,
    ContextRequest,
    DecisionTrace,
    FailureReason,
    RequirementClass,
    TraceDecision,
    TraceEntry,
)
from project_context.compiler.policy import CompilerPolicy
from project_context.domain.bundles import ContextBundle, build_bundle
from project_context.domain.items import estimate_tokens, make_item

SEPARATOR = "\n---\n"
_SEPARATOR_TOKENS = estimate_tokens(SEPARATOR)[0]


def header_tokens(request: ContextRequest) -> int:
    """Deterministic bundle-header cost: request/task/policy identity block
    rendered with every bundle. Admission prices per-item estimates only,
    so the header is what can push an exactly-fitting admission over budget
    at render time (the rendered-overflow case)."""
    return estimate_tokens(f"{request.request_id} {request.task_id} {request.policy_version}")[0]


BAND_ORDER = (
    RequirementClass.MANDATORY,
    RequirementClass.REQUIRED,
    RequirementClass.PREFERRED,
    RequirementClass.DISCRETIONARY,
)


@dataclass
class CompileOutput:
    """Engine return: the bundle (success only) plus the serialisable result."""

    bundle: ContextBundle | None
    result: CompilationResult


def _decoration_tokens(candidate: ContextCandidate) -> int:
    """Deterministic render overhead per item: source/kind decoration."""
    return estimate_tokens(f"{candidate.source_kind} {candidate.kind}")[0]


def _item_render_cost(candidate: ContextCandidate) -> int:
    return candidate.token_count + _decoration_tokens(candidate)


@dataclass
class _Gate:
    eligible: bool
    reason_code: str
    reason_detail: str


def _hard_gate(candidate: ContextCandidate) -> _Gate:
    if not candidate.scope_eligible:
        return _Gate(False, "scope_ineligible", candidate.scope_reason)
    if not candidate.freshness_eligible:
        return _Gate(False, "freshness_ineligible", candidate.freshness_reason)
    if not candidate.authority_eligible:
        return _Gate(False, "authority_ineligible", candidate.authority_reason)
    if candidate.form_rank < candidate.min_rank:
        return _Gate(
            False,
            "illegal_representation",
            f"form_rank {candidate.form_rank} below floor {candidate.min_rank}",
        )
    return _Gate(True, "eligible", "passed scope/freshness/authority/floor gates")


def eligibility(candidate: ContextCandidate) -> tuple[bool, str, str]:
    """Public hard-gate check for evaluators and baselines. Returns
    (eligible, reason_code, reason_detail). Never consults hidden truth."""
    gate = _hard_gate(candidate)
    return gate.eligible, gate.reason_code, gate.reason_detail


def _closure_ids(record_id: str, by_id: dict[str, ContextCandidate]) -> list[str]:
    """Dependency closure in deterministic DFS order. Cycles terminate:
    visited IDs are emitted once and never revisited."""
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(node: str) -> None:
        if node in seen:
            return
        seen.add(node)
        ordered.append(node)
        for dep in by_id[node].depends_on:
            visit(dep)

    visit(record_id)
    return ordered


def compile_context(
    request: ContextRequest,
    candidates: list[ContextCandidate],
    policy: CompilerPolicy,
) -> CompileOutput:
    """Deterministic compile. See module docstring for the stage order."""
    problems = _validate_inputs(request, candidates)
    if problems:
        raise ValueError(f"invalid compiler inputs: {problems}")
    if request.policy_version != policy.policy_version:
        raise ValueError(
            f"request policy {request.policy_version!r} != "
            f"compiler policy {policy.policy_version!r}"
        )

    state = _CompileState(request, candidates, policy)

    # Stage 1: explicit requirements must exist. No substitution, ever.
    missing = sorted(set(request.required_ids) - set(state.by_id))
    if missing:
        return state.fail(
            FailureReason.REQUIRED_SOURCE_UNAVAILABLE,
            missing,
            f"explicitly required candidates absent: {', '.join(missing)}",
        )

    # Stage 2: hard gates for every record. Illegal relevance never survives.
    for candidate in candidates:
        gate = state.gates[candidate.candidate_id]
        if not gate.eligible:
            state.record(
                candidate,
                TraceDecision.REJECTED_HARD,
                gate.reason_code,
                gate.reason_detail,
                0,
                [],
                None,
            )

    # Stages 3-4: mandatory then required, groups atomic.
    for band in (RequirementClass.MANDATORY, RequirementClass.REQUIRED):
        outcome = state.admit_band(band, mandatory=(band == RequirementClass.MANDATORY))
        if outcome is not None:
            return outcome
    state.close_out_alternatives(RequirementClass.MANDATORY)

    # Stage 5: preferred/discretionary greedy with earn rule + coverage.
    for band in (RequirementClass.PREFERRED, RequirementClass.DISCRETIONARY):
        state.admit_greedy(band)

    # Stage 6: close out every unrecorded form.
    state.close_out_remaining()

    # Stage 7: deterministic ordering.
    role_rank = {role: index for index, role in enumerate(policy.order_roles)}
    live = sorted(
        state.admitted.values(),
        key=lambda c: (role_rank.get(c.order_role, len(role_rank)), c.candidate_id),
    )

    # Stage 8: render with exact cost, repair, validate.
    bundle = state.render(live)
    rendered = state.rendered_cost(live)
    if rendered > request.usable_token_budget:
        repaired = state.repair(live, rendered)
        if repaired is None:
            return state.fail(
                FailureReason.INSUFFICIENT_BUDGET,
                [c.candidate_id for c in live],
                f"rendered {rendered} exceeds budget {request.usable_token_budget} "
                "with no legal repair",
            )
        live, bundle, rendered = repaired

    problems = state.validate_bundle(bundle, live)
    if problems:
        return state.fail(
            FailureReason.INSUFFICIENT_BUDGET,
            [c.candidate_id for c in live],
            f"post-compile validation failed: {'; '.join(problems)}",
        )

    # Final positions are render positions.
    for index, candidate in enumerate(live):
        old = state.entries[candidate.candidate_id]
        state.entries[candidate.candidate_id] = dataclasses.replace(old, position=index)

    trace = DecisionTrace(
        request_id=request.request_id,
        policy_version=policy.policy_version,
        entries=tuple(state.entries[cid] for cid in sorted(state.entries)),
    )
    result = CompilationResult(
        request_id=request.request_id,
        policy_version=policy.policy_version,
        success=True,
        bundle_id=bundle.id,
        bundle_tokens=rendered,
        bundle_hash=bundle.content_hash(),
        trace=trace,
        failure=None,
    )
    return CompileOutput(bundle=bundle, result=result)


def _validate_inputs(request: ContextRequest, candidates: list[ContextCandidate]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.candidate_id in seen:
            errors.append(f"duplicate candidate_id: {candidate.candidate_id}")
        seen.add(candidate.candidate_id)
        if candidate.token_count < 0:
            errors.append(f"negative token_count: {candidate.candidate_id}")
    for candidate in candidates:
        for dep in candidate.depends_on:
            if dep not in seen:
                errors.append(f"unknown dependency {dep!r} from {candidate.candidate_id}")
    groups: dict[str, set[str]] = {}
    for candidate in candidates:
        if candidate.group_id and candidate.group_required:
            groups.setdefault(candidate.group_id, set()).add(candidate.requirement.value)
    for group_id, bands in groups.items():
        if len(bands) > 1:
            errors.append(f"required group {group_id} spans bands: {sorted(bands)}")
    _ = request
    return errors


class _CompileState:
    """Mutable working state for one compile. Never escapes the engine."""

    def __init__(
        self,
        request: ContextRequest,
        candidates: list[ContextCandidate],
        policy: CompilerPolicy,
    ) -> None:
        self.request = request
        self.policy = policy
        self.by_id = {c.candidate_id: c for c in candidates}
        self.ordered = sorted(candidates, key=lambda c: c.candidate_id)
        self.gates = {c.candidate_id: _hard_gate(c) for c in candidates}
        self.budget_total = request.usable_token_budget
        self.remaining = request.usable_token_budget
        self.covered: set[str] = set()
        self.admitted: dict[str, ContextCandidate] = {}
        self.admitted_content: set[str] = set()
        self.entries: dict[str, TraceEntry] = {}
        self.required_ids = set(request.required_ids)

    def effective_band(self, candidate: ContextCandidate) -> RequirementClass:
        if candidate.candidate_id in self.required_ids:
            if candidate.requirement == RequirementClass.MANDATORY:
                return RequirementClass.MANDATORY
            return RequirementClass.REQUIRED
        return candidate.requirement

    def record(
        self,
        candidate: ContextCandidate,
        decision: TraceDecision,
        reason_code: str,
        reason_detail: str,
        marginal: int,
        closure: list[str],
        position: int | None,
    ) -> None:
        self.entries[candidate.candidate_id] = TraceEntry(
            candidate_id=candidate.candidate_id,
            content_identity=candidate.content_identity,
            representation_id=candidate.representation_id,
            decision=decision,
            reason_code=reason_code,
            reason_detail=reason_detail,
            priority_band=self.effective_band(candidate).value,
            relevance=candidate.relevance,
            marginal_cost=marginal,
            dependency_closure=tuple(closure),
            budget_before=self.remaining,
            budget_after=self.remaining,
            position=position,
        )

    def fail(self, reason: FailureReason, blocking: list[str], diagnostic: str) -> CompileOutput:
        trace = DecisionTrace(
            request_id=self.request.request_id,
            policy_version=self.policy.policy_version,
            entries=tuple(self.entries[cid] for cid in sorted(self.entries)),
        )
        failure = CompileFailure(
            request_id=self.request.request_id,
            policy_version=self.policy.policy_version,
            reason=reason,
            blocking_ids=tuple(sorted(set(blocking))),
            budget_used=self.budget_total - self.remaining,
            budget_total=self.budget_total,
            diagnostic=diagnostic,
        )
        result = CompilationResult(
            request_id=self.request.request_id,
            policy_version=self.policy.policy_version,
            success=False,
            bundle_id=None,
            bundle_tokens=None,
            bundle_hash=None,
            trace=trace,
            failure=failure,
        )
        return CompileOutput(bundle=None, result=result)

    def marginal_for(self, record_ids: list[str]) -> tuple[int, list[str]]:
        """Marginal estimate of admitting these records: new token counts
        only (decorations, separators, and the bundle header are render
        costs, validated exactly at render time)."""
        closure: list[str] = []
        for rid in record_ids:
            for node in _closure_ids(rid, self.by_id):
                if node not in self.admitted and node not in closure:
                    closure.append(node)
        cost = sum(self.by_id[node].token_count for node in closure)
        return cost, closure

    def commit(self, wanted: list[str], cost: int, reason_detail: str) -> None:
        """Commit a closure: every listed record admitted with its own
        standalone token estimate recorded as marginal cost."""
        for node in sorted(wanted):
            candidate = self.by_id[node]
            self.admitted[node] = candidate
            self.admitted_content.add(candidate.content_identity)
            self.covered.update(candidate.coverage_keys)
            self.record(
                candidate,
                TraceDecision.ADMITTED,
                "admitted",
                reason_detail,
                candidate.token_count,
                [],
                None,
            )

    def forms_of(self, content_identity: str) -> list[ContextCandidate]:
        return sorted(
            (c for c in self.by_id.values() if c.content_identity == content_identity),
            key=lambda c: (c.token_count, c.candidate_id),
        )

    def group_members(self, group_id: str) -> list[ContextCandidate]:
        return sorted(
            (c for c in self.by_id.values() if c.group_id == group_id and c.group_required),
            key=lambda c: c.candidate_id,
        )

    def admit_band(self, band: RequirementClass, *, mandatory: bool) -> CompileOutput | None:
        """Admit every MANDATORY/REQUIRED unit or fail. Groups atomic;
        alternative forms mutually exclusive (cheapest fitting wins)."""
        # Mandatory identities: cheapest fitting legal form first.
        if mandatory:
            identities = sorted(
                {
                    c.content_identity
                    for c in self.by_id.values()
                    if self.effective_band(c) == RequirementClass.MANDATORY
                }
            )
            for identity in identities:
                if identity in self.admitted_content:
                    continue
                forms = [
                    c
                    for c in self.forms_of(identity)
                    if self.effective_band(c) == RequirementClass.MANDATORY
                ]
                eligible = [c for c in forms if self.gates[c.candidate_id].eligible]
                if not eligible:
                    floor_only = bool(forms) and all(
                        self.gates[c.candidate_id].reason_code == "illegal_representation"
                        for c in forms
                    )
                    if floor_only:
                        return self.fail(
                            FailureReason.NO_LEGAL_REPRESENTATION,
                            [identity],
                            f"mandatory {identity}: all forms violate floor",
                        )
                    return self.fail(
                        FailureReason.REQUIRED_INELIGIBLE,
                        [identity],
                        f"mandatory {identity}: no hard-eligible form",
                    )
                placed = False
                for form in sorted(
                    eligible,
                    key=lambda c: (self.marginal_for([c.candidate_id])[0], c.candidate_id),
                ):
                    group = (
                        self.group_members(form.group_id)
                        if form.group_id and form.group_required
                        else [form]
                    )
                    cost, closure = self.marginal_for([m.candidate_id for m in group])
                    if cost > self.remaining:
                        continue
                    blocked = self._blocked_nodes(group)
                    if blocked:
                        return self.fail(
                            FailureReason.UNSATISFIED_DEPENDENCY,
                            [identity],
                            f"mandatory {identity} blocked: {blocked}",
                        )
                    self.commit(closure, cost, "mandatory")
                    self.remaining -= cost
                    placed = True
                    break
                if not placed:
                    return self.fail(
                        FailureReason.INSUFFICIENT_BUDGET,
                        [identity],
                        f"mandatory {identity} closure exceeds remaining budget",
                    )
        # Required units (request-required upgrades included).
        if band == RequirementClass.REQUIRED:
            units = self._band_units(band)
            group_units: list[list[ContextCandidate]] = []
            single_forms: dict[str, list[ContextCandidate]] = {}
            for unit in units:
                if len(unit) > 1 or (unit[0].group_id and unit[0].group_required):
                    group_units.append(unit)
                else:
                    single_forms.setdefault(unit[0].content_identity, []).append(unit[0])
            for unit in group_units:
                cost, closure = self.marginal_for([m.candidate_id for m in unit])
                blocked = self._blocked_nodes(unit)
                members = sorted(m.candidate_id for m in unit)
                if blocked:
                    return self.fail(
                        FailureReason.UNRESOLVED_REQUIRED_GROUP,
                        members,
                        f"required group cannot be satisfied: {blocked}",
                    )
                if cost > self.remaining:
                    return self.fail(
                        FailureReason.UNRESOLVED_REQUIRED_GROUP,
                        members,
                        f"required group exceeds remaining budget: {', '.join(members)}",
                    )
                self.commit(closure, cost, "required")
                self.remaining -= cost
            for identity in sorted(single_forms):
                if identity in self.admitted_content:
                    continue
                forms = sorted(
                    single_forms[identity],
                    key=lambda c: (self.marginal_for([c.candidate_id])[0], c.candidate_id),
                )
                placed = False
                for form in forms:
                    cost, closure = self.marginal_for([form.candidate_id])
                    if cost > self.remaining:
                        continue
                    blocked = self._blocked_nodes([form])
                    if blocked:
                        return self.fail(
                            FailureReason.UNSATISFIED_DEPENDENCY,
                            [form.candidate_id],
                            f"required form blocked: {blocked}",
                        )
                    self.commit(closure, cost, "required")
                    self.remaining -= cost
                    placed = True
                    for other in forms:
                        if other.candidate_id != form.candidate_id:
                            self.record(
                                other,
                                TraceDecision.REJECTED_ALTERNATIVE,
                                "alternative_selected",
                                "another form of this content admitted",
                                0,
                                [],
                                None,
                            )
                    break
                if not placed:
                    return self.fail(
                        FailureReason.INSUFFICIENT_BUDGET,
                        [identity],
                        f"required {identity}: no fitting legal form",
                    )
        return None

    def _blocked_nodes(self, unit: list[ContextCandidate]) -> str:
        """First blocking problem for a unit, or '' if committable."""
        wanted: list[str] = []
        for member in unit:
            for node in _closure_ids(member.candidate_id, self.by_id):
                if node not in self.admitted and node not in wanted:
                    wanted.append(node)
        for node in wanted:
            gate = self.gates[node]
            if not gate.eligible:
                return f"dependency-ineligible:{node}({gate.reason_code})"
            other = self.by_id[node]
            if other.content_identity in self.admitted_content and node not in [
                m.candidate_id for m in unit
            ]:
                return f"alternative-collision:{node}"
        return ""

    def _band_units(self, band: RequirementClass) -> list[list[ContextCandidate]]:
        units: list[list[ContextCandidate]] = []
        seen_groups: set[str] = set()
        for candidate in self.ordered:
            if candidate.candidate_id in self.entries:
                continue
            if self.effective_band(candidate) != band:
                continue
            if not self.gates[candidate.candidate_id].eligible:
                continue
            if candidate.content_identity in self.admitted_content:
                continue
            if candidate.group_id and candidate.group_required:
                if candidate.group_id in seen_groups:
                    continue
                seen_groups.add(candidate.group_id)
                members = [
                    m
                    for m in self.group_members(candidate.group_id)
                    if m.candidate_id not in self.entries
                    and self.gates[m.candidate_id].eligible
                    and m.content_identity not in self.admitted_content
                    and self.effective_band(m) == band
                ]
                if members:
                    units.append(members)
                continue
            units.append([candidate])
        return units

    def admit_greedy(self, band: RequirementClass) -> None:
        """Greedy best-first within one band. Fit and earn are monotonic
        (budget shrinks, coverage grows), so a unit failing either now can
        never pass later: terminal rejections are sound."""
        while True:
            options = self._band_units(band)
            ranked: list[tuple[Any, list[ContextCandidate]]] = []
            for unit in options:
                cost, _ = self.marginal_for([m.candidate_id for m in unit])
                if self._blocked_nodes(unit):
                    for member in unit:
                        if member.candidate_id not in self.entries:
                            self.record(
                                member,
                                TraceDecision.REJECTED_DEPENDENCY,
                                "dependency-blocked",
                                "dependency ineligible or collides",
                                cost,
                                [],
                                None,
                            )
                    continue
                new_cov = len(set().union(*(m.coverage_keys for m in unit)) - self.covered)
                best_rel = max(m.relevance for m in unit)
                if cost > self.remaining:
                    for member in unit:
                        if member.candidate_id not in self.entries:
                            self.record(
                                member,
                                TraceDecision.REJECTED_BUDGET,
                                "budget",
                                "unit exceeds remaining budget",
                                cost,
                                [],
                                None,
                            )
                    continue
                if best_rel < self.policy.min_discretionary_relevance and new_cov == 0:
                    for member in unit:
                        if member.candidate_id not in self.entries:
                            self.record(
                                member,
                                TraceDecision.REJECTED_REDUNDANT,
                                "no-earn",
                                "below relevance threshold with no new coverage",
                                cost,
                                [],
                                None,
                            )
                    continue
                ranked.append(
                    (
                        (-best_rel, -new_cov, cost, unit[0].candidate_id),
                        unit,
                    )
                )
            if not ranked:
                break
            ranked.sort(key=lambda row: row[0])
            best_unit = ranked[0][1]
            cost, closure = self.marginal_for([m.candidate_id for m in best_unit])
            self.commit(closure, cost, f"{band.value.lower()}-greedy")
            self.remaining -= cost

    def close_out_alternatives(self, band: RequirementClass) -> None:
        for candidate in self.ordered:
            if candidate.candidate_id in self.entries:
                continue
            if (
                self.effective_band(candidate) == band
                and candidate.content_identity in self.admitted_content
            ):
                self.record(
                    candidate,
                    TraceDecision.REJECTED_ALTERNATIVE,
                    "alternative_selected",
                    "another form of this content admitted",
                    0,
                    [],
                    None,
                )

    def close_out_remaining(self) -> None:
        for candidate in self.ordered:
            if candidate.candidate_id in self.entries:
                continue
            if candidate.content_identity in self.admitted_content:
                self.record(
                    candidate,
                    TraceDecision.REJECTED_ALTERNATIVE,
                    "alternative_selected",
                    "another form of this content admitted",
                    0,
                    [],
                    None,
                )
            else:
                cost, _ = self.marginal_for([candidate.candidate_id])
                self.record(
                    candidate,
                    TraceDecision.REJECTED_BUDGET,
                    "budget",
                    "no remaining budget path admits this record",
                    cost,
                    [],
                    None,
                )

    def rendered_cost(self, live: list[ContextCandidate]) -> int:
        total = sum(_item_render_cost(c) for c in live)
        total += max(0, len(live) - 1) * _SEPARATOR_TOKENS
        total += header_tokens(self.request)
        return total

    def render(self, live: list[ContextCandidate]) -> ContextBundle:
        made = [
            make_item(
                id=c.candidate_id,
                source=c.source_kind,
                kind=c.kind,
                content=c.content,
            )
            for c in live
        ]
        exacted = [
            dataclasses.replace(item, token_count=_item_render_cost(by_id_item))
            for item, by_id_item in zip(made, [self.by_id[item.id] for item in made])
        ]
        return build_bundle(
            exacted,
            bundle_id=f"{self.request.request_id}-bundle",
            created_at=self.request.created_at,
            evidence_class="synthetic",
        )

    def repair(
        self, live: list[ContextCandidate], rendered: int
    ) -> tuple[list[ContextCandidate], ContextBundle, int] | None:
        """Drop last-admitted discretionary units (whole groups), recompute,
        rerender. Mandatory/required/dependencies/floors never move."""
        live = list(live)
        while rendered > self.request.usable_token_budget:
            if self.policy.repair != "drop-last-discretionary":
                return None
            droppable = [
                c
                for c in reversed(live)
                if self.effective_band(c) == RequirementClass.DISCRETIONARY
                and not _depends_on_id(c.candidate_id, live)
            ]
            if not droppable:
                return None
            victim = droppable[0]
            victims = {victim.candidate_id}
            if victim.group_id and victim.group_required:
                victims.update(c.candidate_id for c in live if c.group_id == victim.group_id)
            live = [c for c in live if c.candidate_id not in victims]
            for vid in sorted(victims):
                if vid in self.admitted:
                    del self.admitted[vid]
            self.admitted_content = {self.by_id[vid].content_identity for vid in self.admitted}
            for vid in sorted(victims):
                old = self.entries[vid]
                self.entries[vid] = dataclasses.replace(
                    old,
                    decision=TraceDecision.REJECTED_BUDGET,
                    reason_code="repair-drop",
                    reason_detail="removed by render-overrun repair",
                    position=None,
                )
            bundle = self.render(live)
            rendered = self.rendered_cost(live)
        self.remaining = self.request.usable_token_budget - rendered
        return live, bundle, rendered

    def validate_bundle(self, bundle: ContextBundle, live: list[ContextCandidate]) -> list[str]:
        problems: list[str] = []
        if self.rendered_cost(live) > self.request.usable_token_budget:
            problems.append("rendered cost exceeds budget")
        if [item.id for item in bundle.items] != list(bundle.layout_trace):
            problems.append("layout trace mismatch")
        live_ids = {c.candidate_id for c in live}
        for item in bundle.items:
            if item.id not in live_ids:
                problems.append(f"bundle item not admitted: {item.id}")
        return problems


def _depends_on_id(candidate_id: str, live: list[ContextCandidate]) -> bool:
    by_id = {c.candidate_id: c for c in live}
    seen: set[str] = set()
    stack = [c.candidate_id for c in live if c.candidate_id != candidate_id]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        for dep in by_id[node].depends_on:
            if dep == candidate_id:
                return True
            stack.append(dep)
    return False
