"""Plausible-but-wrong eligibility shortcuts, used as the naive baselines.

These are what a hurried implementation does: treat the newest timestamp as
authoritative, decide scope from a path prefix, let a payload's own rhetoric raise
its rank, take the first value seen. They exist so the governance experiments have
a fair naive comparison, and so a generated fixture can be checked for whether it
actually exposes the mechanism (a fixture on which the shortcuts do fine teaches
nothing).

Nothing here is a recommendation.
"""

from __future__ import annotations

from project_context.governance.model import (
    CandidateMetadata,
    Policy,
    Resolution,
    Role,
    Status,
    Verdict,
)


def heuristic_resolve(candidates: list[CandidateMetadata], policy: Policy) -> Resolution:
    """Admit almost everything; resolve conflicts by shortcuts."""
    verdicts: list[Verdict] = []
    latest_capture: dict[str, int] = {}
    for item in candidates:
        if item.claim_key is not None and item.observed_at is not None:
            key = item.claim_key
            latest_capture[key] = max(latest_capture.get(key, item.observed_at), item.observed_at)
    for item in candidates:
        # Shortcut 1: "the most recently captured copy is current". Ignores the version
        # and the question's standpoint.
        if (
            item.claim_key in latest_capture
            and item.observed_at is not None
            and item.observed_at < latest_capture[item.claim_key]
        ):
            verdicts.append(
                Verdict(item.item_id, Status.INELIGIBLE, Role.EXCLUDED, "older_capture")
            )
            continue
        # Shortcut 2: scope by naming prefix only when the source id shares the scope label;
        # anything else is admitted.
        # Shortcut 3: any item that directs, from any channel, is control.
        role = Role.CONTROL if item.directs else Role.DATA
        verdicts.append(Verdict(item.item_id, Status.ELIGIBLE, role, "admitted"))
    return Resolution(tuple(verdicts))
