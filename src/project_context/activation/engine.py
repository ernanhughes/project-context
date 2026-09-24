"""The activation engine: eligibility first, relevance second, then one bounded pass.

Pure function of its inputs. No filesystem, model, network, clock,
randomness, or mutable global state.

Eligibility (validity) gate, in order:

1. terminal lifecycle status → INELIGIBLE (per-status code);
2. contradicted verification → INELIGIBLE;
3. recorded repo on both sides that disagrees → INELIGIBLE
   (the world boundary; mirrors the compiler scope gate).

Relevance (typed reasons, never similarity):

- scope_path_match / scope_component_match / scope_task_match: exact
  structural overlap (paths also match on either-direction prefix);
- operation_in_governed_scope: a constraint whose governed area the
  request enters while performing a recorded operation;
- evidence_match: a recorded evidence ref of the item is present now;
- dependency_ready: an obligation whose every dependency is satisfied
  or verified (a modifier, never sufficient alone);
- blocking_condition_relevant: a blocked obligation whose blocking
  dependency the request is about.

A blocked obligation with scope overlap but an unmet, unrelated blocker
stays DORMANT (blocked_dependency_unmet): related is not actionable.

Abstention: a featured request against a scopeless item, or any request
with no usable features at all, yields UNKNOWN, never a guess.

Relationship propagation is one pass over a snapshot: an eligible
non-active item whose `depends_on` target is ACTIVE becomes ACTIVE via
`dependency_active`. Propagated items do not propagate further. No
other relationship type propagates in Stage 6B.

Repo equality alone never activates: sharing a repository is the normal
case, not a reason to wake up.
"""

from __future__ import annotations

import hashlib
import json

from project_context.activation.model import (
    REPO_MISMATCH,
    TERMINAL_CODES,
    ActivationDecision,
    ActivationMode,
    ActivationPolicy,
    ActivationRequest,
    ActivationResult,
    ActivationState,
)
from project_context.ledger.projection import LedgerState, ProjectedItem
from project_context.ledger.records import TERMINAL_STATUSES, ItemKind, VerificationState


def _paths_overlap(left: str, right: str) -> bool:
    a, b = left.rstrip("/"), right.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _scope_overlap(item: ProjectedItem, request: ActivationRequest) -> dict:
    """Structural overlap between item scope and request features."""
    scope = item.item.scope
    matched: dict = {}
    path_hits = sorted({p for p in scope.paths for q in request.paths if _paths_overlap(p, q)})
    if path_hits:
        matched["paths"] = path_hits
    if scope.component is not None and scope.component in request.components:
        matched["components"] = [scope.component]
    if scope.task is not None and request.task is not None and scope.task == request.task:
        matched["task"] = scope.task
    return matched


def _item_has_scope(item: ProjectedItem) -> bool:
    scope = item.item.scope
    return bool(
        scope.repo is not None
        or scope.paths
        or scope.component is not None
        or scope.task is not None
    )


def _dependencies_met(state: LedgerState, item: ProjectedItem) -> bool:
    if not item.depends_on:
        return True
    by_id = {entry.item.item_id: entry for entry in state.items}
    for dep_id in item.depends_on:
        target = by_id.get(dep_id)
        if target is None:
            return False
        if target.status.value != "satisfied" and (
            target.verification is not VerificationState.VERIFIED
        ):
            return False
    return True


def _dependency_scope_overlap(
    state: LedgerState, item: ProjectedItem, request: ActivationRequest
) -> tuple[str, ...]:
    """Dependencies whose own scope the request touches."""
    by_id = {entry.item.item_id: entry for entry in state.items}
    hits = []
    for dep_id in item.depends_on:
        target = by_id.get(dep_id)
        if target is not None and _scope_overlap(target, request):
            hits.append(dep_id)
    return tuple(sorted(hits))


def _evidence_match(item: ProjectedItem, request: ActivationRequest) -> tuple[str, ...]:
    if not request.evidence_refs:
        return ()
    refs = {ref for ref in request.evidence_refs}
    return tuple(sorted({e.get("ref") for e in item.evidence if e.get("ref") in refs}))


def _epistemic(item: ProjectedItem) -> str | None:
    if item.item.kind.value in ("assumption", "pending_verification"):
        return item.verification.value
    return None


def _features_used(
    item: ProjectedItem,
    request: ActivationRequest,
    matched: dict,
    consulted_operation: bool,
    consulted_evidence: bool,
) -> tuple[str, ...]:
    used = set()
    if item.item.scope.repo is not None and request.repo is not None:
        used.add("repo")
    if item.item.scope.paths and request.paths:
        used.add("paths")
    if item.item.scope.component is not None and request.components:
        used.add("components")
    if item.item.scope.task is not None and request.task is not None:
        used.add("task")
    if consulted_operation:
        used.add("operation")
    if consulted_evidence:
        used.add("evidence_refs")
    _ = matched
    return tuple(sorted(used))


def _decide_typed(
    state: LedgerState, item: ProjectedItem, request: ActivationRequest, policy: ActivationPolicy
) -> ActivationDecision:
    status = item.status.value
    if item.status in TERMINAL_STATUSES:
        return ActivationDecision(
            item_id=item.item.item_id,
            state=ActivationState.INELIGIBLE,
            reason_codes=(TERMINAL_CODES[status],),
            matched_scope={},
            matched_dependencies=(),
            request_features_used=(),
            epistemic=None,
            policy_id=policy.policy_id,
        )
    if item.verification is VerificationState.CONTRADICTED:
        return ActivationDecision(
            item_id=item.item.item_id,
            state=ActivationState.INELIGIBLE,
            reason_codes=("verification_contradicted",),
            matched_scope={},
            matched_dependencies=(),
            request_features_used=(),
            epistemic=None,
            policy_id=policy.policy_id,
        )
    if (
        item.item.scope.repo is not None
        and request.repo is not None
        and item.item.scope.repo != request.repo
    ):
        return ActivationDecision(
            item_id=item.item.item_id,
            state=ActivationState.INELIGIBLE,
            reason_codes=(REPO_MISMATCH,),
            matched_scope={},
            matched_dependencies=(),
            request_features_used=("repo",),
            epistemic=None,
            policy_id=policy.policy_id,
        )

    matched = _scope_overlap(item, request)
    evidence_hits = _evidence_match(item, request)
    consulted_evidence = bool(item.evidence)
    consulted_operation = item.item.kind is ItemKind.CONSTRAINT and request.operation is not None
    features = _features_used(item, request, matched, consulted_operation, consulted_evidence)

    reasons: list[str] = []
    if "paths" in matched:
        reasons.append("scope_path_match")
    if "components" in matched:
        reasons.append("scope_component_match")
    if "task" in matched:
        reasons.append("scope_task_match")
    if consulted_operation and ("paths" in matched or "components" in matched):
        reasons.append("operation_in_governed_scope")
    if evidence_hits:
        reasons.append("evidence_match")

    is_obligation = item.item.kind is ItemKind.OBLIGATION
    deps_ready = _dependencies_met(state, item)
    if is_obligation and item.depends_on and deps_ready and reasons:
        reasons.append("dependency_ready")
    matched_deps = _dependency_scope_overlap(state, item, request) if is_obligation else ()

    if is_obligation and item.depends_on and not deps_ready:
        if matched_deps:
            reasons.append("blocking_condition_relevant")
            return ActivationDecision(
                item_id=item.item.item_id,
                state=ActivationState.ACTIVE,
                reason_codes=tuple(sorted(reasons)),
                matched_scope=matched,
                matched_dependencies=matched_deps,
                request_features_used=features,
                epistemic=_epistemic(item),
                policy_id=policy.policy_id,
            )
        return ActivationDecision(
            item_id=item.item.item_id,
            state=ActivationState.DORMANT,
            reason_codes=("blocked_dependency_unmet",),
            matched_scope=matched,
            matched_dependencies=(),
            request_features_used=features,
            epistemic=_epistemic(item),
            policy_id=policy.policy_id,
        )

    if reasons:
        return ActivationDecision(
            item_id=item.item.item_id,
            state=ActivationState.ACTIVE,
            reason_codes=tuple(sorted(reasons)),
            matched_scope=matched,
            matched_dependencies=matched_deps,
            request_features_used=features,
            epistemic=_epistemic(item),
            policy_id=policy.policy_id,
        )
    if not request.usable_features():
        code = "request_features_absent"
        return ActivationDecision(
            item_id=item.item.item_id,
            state=ActivationState.UNKNOWN,
            reason_codes=(code,),
            matched_scope={},
            matched_dependencies=(),
            request_features_used=(),
            epistemic=_epistemic(item),
            policy_id=policy.policy_id,
        )
    if not _item_has_scope(item) and not evidence_hits:
        return ActivationDecision(
            item_id=item.item.item_id,
            state=ActivationState.UNKNOWN,
            reason_codes=("insufficient_scope_to_decide",),
            matched_scope={},
            matched_dependencies=(),
            request_features_used=features,
            epistemic=_epistemic(item),
            policy_id=policy.policy_id,
        )
    return ActivationDecision(
        item_id=item.item.item_id,
        state=ActivationState.DORMANT,
        reason_codes=("no_activation_reason",),
        matched_scope={},
        matched_dependencies=(),
        request_features_used=features,
        epistemic=_epistemic(item),
        policy_id=policy.policy_id,
    )


def _decide_baseline(
    state: LedgerState, item: ProjectedItem, request: ActivationRequest, policy: ActivationPolicy
) -> ActivationDecision:
    _ = state
    item_id = item.item.item_id
    if policy.mode is ActivationMode.ALL_UNRESOLVED:
        if item.status.value in ("active", "blocked"):
            return ActivationDecision(
                item_id,
                ActivationState.ACTIVE,
                ("all_unresolved",),
                {},
                (),
                (),
                None,
                policy.policy_id,
            )
        return ActivationDecision(
            item_id,
            ActivationState.INELIGIBLE,
            (TERMINAL_CODES[item.status.value],),
            {},
            (),
            (),
            None,
            policy.policy_id,
        )
    if policy.mode is ActivationMode.SCOPE_ONLY:
        matched = _scope_overlap(item, request)
        if matched:
            return ActivationDecision(
                item_id,
                ActivationState.ACTIVE,
                ("scope_overlap",),
                matched,
                (),
                (),
                None,
                policy.policy_id,
            )
        return ActivationDecision(
            item_id,
            ActivationState.DORMANT,
            ("no_scope_match",),
            {},
            (),
            (),
            None,
            policy.policy_id,
        )
    if policy.mode is ActivationMode.NEWEST:
        if item.status in TERMINAL_STATUSES:
            return ActivationDecision(
                item_id,
                ActivationState.INELIGIBLE,
                (TERMINAL_CODES[item.status.value],),
                {},
                (),
                (),
                None,
                policy.policy_id,
            )
        return ActivationDecision(
            item_id,
            ActivationState.DORMANT,
            ("not_newest",),
            {},
            (),
            (),
            None,
            policy.policy_id,
        )
    raise ValueError(f"unknown activation mode: {policy.mode!r}")


def activate(
    state: LedgerState, request: ActivationRequest, policy: ActivationPolicy
) -> ActivationResult:
    """Decide activation for every item in the ledger state."""
    ordered = sorted(state.items, key=lambda entry: entry.item.item_id)
    if policy.mode is ActivationMode.TYPED:
        decisions = [_decide_typed(state, item, request, policy) for item in ordered]
        decisions = _propagate(state, decisions, policy)
    elif policy.mode is ActivationMode.NEWEST:
        decisions = [_decide_baseline(state, item, request, policy) for item in ordered]
        decisions = _apply_newest(state, decisions, policy)
    else:
        decisions = [_decide_baseline(state, item, request, policy) for item in ordered]
    decisions = sorted(decisions, key=lambda d: d.item_id)
    return ActivationResult(
        request_id=request.request_id, policy_id=policy.policy_id, decisions=tuple(decisions)
    )


def _propagate(
    state: LedgerState, decisions: list[ActivationDecision], policy: ActivationPolicy
) -> list[ActivationDecision]:
    """One bounded pass: an eligible non-active item whose dependency is
    ACTIVE becomes ACTIVE. A snapshot drives the pass, so propagated
    items never propagate further."""
    by_id = {entry.item.item_id: entry for entry in state.items}
    active = {d.item_id for d in decisions if d.state is ActivationState.ACTIVE}
    out = []
    for decision in decisions:
        if decision.state is ActivationState.ACTIVE:
            out.append(decision)
            continue
        if decision.state is ActivationState.INELIGIBLE:
            out.append(decision)
            continue
        entry = by_id[decision.item_id]
        triggering = tuple(sorted(d for d in entry.depends_on if d in active))
        if triggering:
            out.append(
                ActivationDecision(
                    item_id=decision.item_id,
                    state=ActivationState.ACTIVE,
                    reason_codes=tuple(sorted(set(decision.reason_codes) | {"dependency_active"})),
                    matched_scope=decision.matched_scope,
                    matched_dependencies=triggering,
                    request_features_used=decision.request_features_used,
                    epistemic=decision.epistemic,
                    policy_id=policy.policy_id,
                )
            )
        else:
            out.append(decision)
    return out


def _apply_newest(
    state: LedgerState, decisions: list[ActivationDecision], policy: ActivationPolicy
) -> list[ActivationDecision]:
    """Naive recency baseline: the N most recently created non-terminal
    items wake, regardless of the request. Ranked by (created_at,
    item_id); the request is ignored."""
    _ = state
    eligible = [d for d in decisions if d.state is not ActivationState.INELIGIBLE]
    created = {entry.item.item_id: entry.created_at for entry in state.items}
    ranked = sorted((d.item_id for d in eligible), key=lambda i: (created[i], i), reverse=True)
    winners = set(ranked[: max(0, policy.newest_keep)])
    out = []
    for decision in decisions:
        if decision.item_id in winners:
            out.append(
                ActivationDecision(
                    decision.item_id,
                    ActivationState.ACTIVE,
                    ("newest",),
                    {},
                    (),
                    (),
                    None,
                    policy.policy_id,
                )
            )
        else:
            out.append(decision)
    return out


def result_digest(result: ActivationResult) -> str:
    canonical = json.dumps(result.to_dict(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
