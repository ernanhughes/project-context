"""Adapt ACTIVE ledger items into ordinary compiler candidates.

Mapping (every choice documented; nothing here is a relevance judgement):

- input: one `LedgerState`, one `ActivationResult`, one adapter policy id.
  Only ACTIVE decisions yield candidates. Activation is consumed, never
  recomputed: dormant, ineligible and unknown items yield receipts with
  `candidate_id = None`.
- `candidate_id = ledger-<item_id>-<digest12>`, where the digest covers
  item id, lifecycle status, verification, statement digest, activation
  policy id and sorted reason codes. Identical input reproduces it;
  any meaningful state change alters it. No statement content enters
  the identifier (privacy: live statements may be private).
- `content_identity = ledger-item-<item_id>`: one semantic item, so
  alternative-form exclusion can never merge two ledger items.
- `content`: the canonical statement verbatim, except that unverified
  epistemic state the render pipeline would otherwise flatten is kept
  visible with a deterministic status tag (`[Unverified assumption]`,
  `[Pending verification]`). The render joins contents only, so this
  tag is what preserves "matters now" without claiming "established
  truth". No LLM rewriting, no polished rendering.
- `kind`: the ledger item kind (obligation, assumption, ...). The
  engine reads kind only for render decoration, so this preserves
  meaning with zero admission effect.
- `source_kind = "ledger"`, `source_ref = <item_id>`: lineage, not
  privilege. Standing never keys off these fields (pinned by tests).
- `requirement`: PREFERRED for user/system/project authority,
  DISCRETIONARY otherwise. Authority-derived standing, exactly as
  ordinary pools treat user instructions versus tool evidence. Never
  MANDATORY/REQUIRED: adapted state must earn admission and must be
  allowed to lose or be omitted by budget.
- `relevance`: one fixed adapter default for every adapted candidate.
  No per-item scoring, hence no adapter ranking; ties break by
  candidate_id in the engine, neutrally.
- `order_role`: instruction for constraints/decisions, task for
  obligations, state for unresolved failures, evidence for the rest.
  Render order only.
- eligibility flags: True with reasons recording the preserved facts
  (scope dimensions, verification state, authority origin). The adapter
  is the pool-builder for ledger items, as fixtures are for ordinary
  ones; activation already applied the validity gate for this
  computation. Adapting output for any other computation is a harness
  error, documented here.
- `token_count`: the repository's existing word-based approximation
  over the final content, `token_source = "approximation"`. No fake
  precision, no zero costs.
- single canonical form: `representation_id = "ledger-full"`,
  `form_rank = 3`, `min_rank = 0`, `is_default_form = True`.
- `depends_on`: ledger dependencies remapped to co-adapted candidate
  ids; dependencies outside the ACTIVE batch are omitted and named in
  the receipt (activation-time facts, not compiler graph snapshots).
- `coverage_keys`, `group_id`: empty/None. Adapted candidates earn
  admission through the ordinary earn rule.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from project_context.activation.model import ActivationResult, ActivationState
from project_context.compiler.domain import ContextCandidate, RequirementClass
from project_context.domain.items import estimate_tokens
from project_context.ledger.projection import LedgerState, ProjectedItem
from project_context.ledger.records import Authority, ItemKind

ADAPTER_POLICY_ID = "ledger-adapter-v1"
ADAPTER_RECEIPT_SCHEMA = "project_context.ledger_adapter_receipt.v1"
ADAPTER_RELEVANCE = 0.5

_PREFERRED_AUTHORITIES = frozenset({Authority.USER, Authority.SYSTEM, Authority.PROJECT})

_ORDER_ROLE = {
    ItemKind.CONSTRAINT: "instruction",
    ItemKind.DECISION: "instruction",
    ItemKind.OBLIGATION: "task",
    ItemKind.UNRESOLVED_FAILURE: "state",
    ItemKind.ASSUMPTION: "evidence",
    ItemKind.PENDING_VERIFICATION: "evidence",
    ItemKind.RESULT: "evidence",
    ItemKind.DEPENDENCY: "evidence",
}

_EPISTEMIC_TAG = {
    ItemKind.ASSUMPTION: "[Unverified assumption]",
    ItemKind.PENDING_VERIFICATION: "[Pending verification]",
}

_AUTHORITY_REASON = {
    Authority.USER: "user-derived directive standing",
    Authority.SYSTEM: "system standing",
    Authority.PROJECT: "project standing",
    Authority.TOOL: "tool evidence: data, never directive",
    Authority.AGENT: "agent-authored: data, never user/project authority",
    Authority.DERIVED: "derived state",
}


def _candidate_digest(item: ProjectedItem, reason_codes: tuple[str, ...], policy_id: str) -> str:
    basis = "|".join(
        [
            item.item.item_id,
            item.status.value,
            item.verification.value,
            item.statement_digest,
            policy_id,
            ",".join(reason_codes),
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def _content(item: ProjectedItem, epistemic: str | None) -> str:
    statement = item.item.statement
    if epistemic == "unverified":
        tag = _EPISTEMIC_TAG.get(item.item.kind)
        if tag is not None:
            return f"{tag} {statement}"
    return statement


@dataclass(frozen=True)
class LedgerAdapterReceipt:
    """Deterministic trace of one adaptation decision: which ledger item,
    whether it became a candidate, what metadata was preserved, and why."""

    item_id: str
    activation_state: str
    candidate_id: str | None
    mapped_authority: str
    mapped_requirement: str | None
    epistemic: str | None
    scope: dict[str, Any]
    dropped_dependencies: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ADAPTER_RECEIPT_SCHEMA,
            "item_id": self.item_id,
            "activation_state": self.activation_state,
            "candidate_id": self.candidate_id,
            "mapped_authority": self.mapped_authority,
            "mapped_requirement": self.mapped_requirement,
            "epistemic": self.epistemic,
            "scope": dict(self.scope),
            "dropped_dependencies": list(self.dropped_dependencies),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LedgerAdapterReceipt":
        version = data.get("schema_version", ADAPTER_RECEIPT_SCHEMA)
        if version != ADAPTER_RECEIPT_SCHEMA:
            raise ValueError(f"unsupported LedgerAdapterReceipt schema: {version!r}")
        return cls(
            item_id=data["item_id"],
            activation_state=data["activation_state"],
            candidate_id=data.get("candidate_id"),
            mapped_authority=data["mapped_authority"],
            mapped_requirement=data.get("mapped_requirement"),
            epistemic=data.get("epistemic"),
            scope=dict(data.get("scope", {})),
            dropped_dependencies=tuple(data.get("dropped_dependencies", [])),
            reason=data.get("reason", ""),
        )


def adapt(
    state: LedgerState,
    activation: ActivationResult,
    *,
    policy_id: str = ADAPTER_POLICY_ID,
) -> tuple[tuple[ContextCandidate, ...], tuple[LedgerAdapterReceipt, ...]]:
    """Adapt every ACTIVE decision into an ordinary candidate plus a
    receipt per decision. Deterministic; sorted by item id."""
    by_item = {entry.item.item_id: entry for entry in state.items}
    active_ids = {d.item_id for d in activation.decisions if d.state is ActivationState.ACTIVE}
    # Candidate ids first, so depends_on can remap within the batch.
    planned: dict[str, str] = {}
    for decision in sorted(activation.decisions, key=lambda d: d.item_id):
        if decision.item_id not in active_ids or decision.item_id not in by_item:
            continue
        entry = by_item[decision.item_id]
        digest = _candidate_digest(entry, tuple(sorted(decision.reason_codes)), policy_id)
        planned[decision.item_id] = f"ledger-{decision.item_id}-{digest}"

    candidates: list[ContextCandidate] = []
    receipts: list[LedgerAdapterReceipt] = []
    for decision in sorted(activation.decisions, key=lambda d: d.item_id):
        entry = by_item.get(decision.item_id)
        if entry is None or decision.state is not ActivationState.ACTIVE:
            receipts.append(
                LedgerAdapterReceipt(
                    item_id=decision.item_id,
                    activation_state=decision.state.value,
                    candidate_id=None,
                    mapped_authority=entry.item.authority.value if entry else "unknown",
                    mapped_requirement=None,
                    epistemic=None,
                    scope=entry.item.scope.to_dict() if entry else {},
                    dropped_dependencies=(),
                    reason="not active: no candidate produced",
                )
            )
            continue
        candidate_id = planned[decision.item_id]
        preferred = entry.item.authority in _PREFERRED_AUTHORITIES
        requirement = RequirementClass.PREFERRED if preferred else RequirementClass.DISCRETIONARY
        content = _content(entry, decision.epistemic)
        token_count, token_source = estimate_tokens(content)
        depends_on = tuple(sorted(planned[dep] for dep in entry.depends_on if dep in planned))
        dropped = tuple(sorted(dep for dep in entry.depends_on if dep not in planned))
        scope = entry.item.scope
        scope_bits = []
        if scope.repo is not None:
            scope_bits.append(f"repo={scope.repo}")
        if scope.component is not None:
            scope_bits.append(f"component={scope.component}")
        if scope.paths:
            scope_bits.append(f"paths={','.join(scope.paths)}")
        if scope.task is not None:
            scope_bits.append(f"task={scope.task}")
        candidates.append(
            ContextCandidate(
                candidate_id=candidate_id,
                content_identity=f"ledger-item-{entry.item.item_id}",
                representation_id="ledger-full",
                form_rank=3,
                min_rank=0,
                source_kind="ledger",
                source_ref=entry.item.item_id,
                kind=entry.item.kind.value,
                content=content,
                token_count=token_count,
                token_source=token_source,
                requirement=requirement,
                order_role=_ORDER_ROLE[entry.item.kind],
                scope_eligible=True,
                scope_reason=(
                    "activation-established scope: " + (";".join(scope_bits) or "unscoped")
                ),
                freshness_eligible=True,
                freshness_reason=(
                    f"ledger verification={entry.verification.value}; "
                    "epistemic state preserved, not promoted"
                ),
                authority_eligible=True,
                authority_reason=_AUTHORITY_REASON[entry.item.authority],
                depends_on=depends_on,
                group_id=None,
                group_required=False,
                coverage_keys=(),
                relevance=ADAPTER_RELEVANCE,
                is_default_form=True,
            )
        )
        receipts.append(
            LedgerAdapterReceipt(
                item_id=decision.item_id,
                activation_state=decision.state.value,
                candidate_id=candidate_id,
                mapped_authority=entry.item.authority.value,
                mapped_requirement=requirement.value,
                epistemic=decision.epistemic,
                scope=scope.to_dict(),
                dropped_dependencies=dropped,
                reason=";".join(sorted(decision.reason_codes)),
            )
        )
    return tuple(candidates), tuple(receipts)


def adapt_case(
    state: LedgerState,
    activation: ActivationResult,
    ordinary: list[ContextCandidate],
    *,
    policy_id: str = ADAPTER_POLICY_ID,
) -> tuple[tuple[ContextCandidate, ...], tuple[LedgerAdapterReceipt, ...]]:
    """Adapted ledger candidates plus an ordinary pool, sorted by
    candidate id. The adapter never reorders by importance."""
    adapted, receipts = adapt(state, activation, policy_id=policy_id)
    pool = tuple(sorted([*ordinary, *adapted], key=lambda c: c.candidate_id))
    return pool, receipts
