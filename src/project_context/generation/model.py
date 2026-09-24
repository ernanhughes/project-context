"""Generated task types: what is visible, and what is hidden truth.

A generated task has two halves that never mix:

    visible   the prompt, the allowed actions, the candidate items (text plus
              governance metadata) and the declared policy
    truth     which items are critical, which are traps and what action each trap
              would induce, what each item's eligibility really is, which actions
              are valid or forbidden

Only the checker reads truth. The resolver, the assemblers and the readers see the
visible half. `visible_view` is the single function that produces it, so the boundary
is one thing to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from project_context.governance.model import CandidateMetadata, Policy

# An action is (name, value). value None means "any value" when used as a forbidden or
# implied action, and "no value" when it is the reader's action.
Action = tuple[str, str | None]


@dataclass(frozen=True)
class GeneratedItem:
    item_id: str  # derived from content and metadata, never hand-written
    kind: str  # "instruction", "fact", "tool_output", "quoted", "document"
    content: str  # what the reader sees
    tokens: int  # approximate, labelled as such elsewhere
    meta: CandidateMetadata


@dataclass(frozen=True)
class TrapInfo:
    item_id: str
    trap_kind: str  # stale, wrong_scope, conflicting, injection, near_miss, unverified
    implied_action: Action  # what a reader that followed this item would do


@dataclass(frozen=True)
class ItemTruth:
    item_id: str
    status: str  # "ELIGIBLE", "INELIGIBLE", "UNKNOWN"
    role: str  # "control", "data", "excluded"
    reason_class: str  # scope, authority, freshness, provenance, delegation, ordinary, unknown


@dataclass(frozen=True)
class HiddenTruth:
    critical_evidence: tuple[str, ...]  # item ids that must be admitted for success
    decisive_value: str | None  # the value a correct action must contain, if any
    valid_actions: tuple[Action, ...]
    forbidden_actions: tuple[Action, ...]
    traps: tuple[TrapInfo, ...]
    item_truth: tuple[ItemTruth, ...]
    expected_conflict: str  # "none", "resolved", "unresolved"
    constraints: tuple[str, ...] = ()  # names of declared constraints the action must respect


@dataclass(frozen=True)
class GeneratedTask:
    task_id: str  # derived from the whole task, not hand-written
    family: str
    seed: int
    options: tuple[tuple[str, str], ...]
    prompt: str
    actions: tuple[str, ...]  # the closed set of action names a reader may choose
    policy: Policy
    items: tuple[GeneratedItem, ...]
    truth: HiddenTruth = field(repr=False)

    def visible(self) -> "VisibleTask":
        return visible_view(self)


@dataclass(frozen=True)
class VisibleTask:
    task_id: str
    prompt: str
    actions: tuple[str, ...]
    policy: Policy
    items: tuple[GeneratedItem, ...]

    def candidates(self) -> list[CandidateMetadata]:
        return [item.meta for item in self.items]


def visible_view(task: GeneratedTask) -> VisibleTask:
    """The only projection of a task that a reader or assembler may receive."""
    return VisibleTask(task.task_id, task.prompt, task.actions, task.policy, task.items)


def truth_as_dict(truth: HiddenTruth) -> dict[str, Any]:
    """Plain form used for content-derived ids. Sorted, no ordering ambiguity."""
    return {
        "critical": sorted(truth.critical_evidence),
        "value": truth.decisive_value,
        "valid": sorted(map(list, truth.valid_actions), key=str),
        "forbidden": sorted(map(list, truth.forbidden_actions), key=str),
        "traps": sorted(
            ([t.item_id, t.trap_kind, list(t.implied_action)] for t in truth.traps), key=str
        ),
        "items": sorted(
            ([i.item_id, i.status, i.role, i.reason_class] for i in truth.item_truth), key=str
        ),
        "conflict": truth.expected_conflict,
        "constraints": sorted(truth.constraints),
    }
