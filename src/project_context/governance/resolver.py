"""Derive eligibility from candidate metadata and a declared policy.

Deterministic. It decides four things, from metadata alone:

    scope       does the item belong to the active world
    authority   may the item direct behaviour, and who wins when directives collide
    freshness   is this the version the question is about
    provenance  when sources disagree, does policy name a winner

Missing metadata yields UNKNOWN, never a default: an item with no recorded scope is
not global, an item with no version is not current, an item from an unvetted
revision is not delegated. Where policy is silent about a factual conflict, the
conflict is preserved and marked UNRESOLVED; the resolver never invents a winner.

It has no access to, and no knowledge of, any task's hidden truth.
"""

from __future__ import annotations

from collections import defaultdict

from project_context.governance.model import (
    CandidateMetadata,
    Conflict,
    ConflictStatus,
    Policy,
    Resolution,
    Role,
    Status,
    Verdict,
)

# Channels that can never direct behaviour, whatever they say about themselves.
NON_AUTHORITATIVE = frozenset({"tool_output", "quoted", "declared", "web", "document"})


def _rank(policy: Policy, channel: str) -> int | None:
    # A vetted delegation carries the authority of whoever delegated it: the user.
    if channel == "delegated":
        channel = "user"
    try:
        return len(policy.authority_order) - policy.authority_order.index(channel)
    except ValueError:
        return None


def resolve(candidates: list[CandidateMetadata], policy: Policy) -> Resolution:
    verdicts: dict[str, Verdict] = {}
    conflicts: list[Conflict] = []

    def set_verdict(item: CandidateMetadata, status: Status, role: Role, reason: str, group=None):
        verdicts[item.item_id] = Verdict(item.item_id, status, role, reason, group)

    # 1. Scope. Missing scope is unknown; another world is ineligible.
    in_scope: list[CandidateMetadata] = []
    for item in candidates:
        if item.scope is None:
            set_verdict(item, Status.UNKNOWN, Role.EXCLUDED, "scope_missing")
        elif item.scope != policy.active_scope and item.scope not in policy.shared_scopes:
            set_verdict(item, Status.INELIGIBLE, Role.EXCLUDED, "scope_mismatch")
        else:
            in_scope.append(item)

    # 2. Authority channel. Decide who may direct, before anything else about directives.
    vetted = dict(policy.vetted_revisions)
    live: list[CandidateMetadata] = []
    for item in in_scope:
        if item.channel == "delegated":
            expected = vetted.get(item.source_id)
            if expected is None or item.revision is None:
                set_verdict(item, Status.UNKNOWN, Role.EXCLUDED, "delegation_unverifiable")
            elif item.revision != expected:
                set_verdict(item, Status.INELIGIBLE, Role.EXCLUDED, "delegation_revision_changed")
            else:
                live.append(item)
        else:
            live.append(item)

    # 3. Freshness. Per claim key, the version the question is about.
    by_claim: dict[str, list[CandidateMetadata]] = defaultdict(list)
    for item in live:
        if item.claim_key is not None:
            by_claim[item.claim_key].append(item)
    superseded: set[str] = set()
    for items in by_claim.values():
        versioned = [i for i in items if i.version is not None]
        for item in items:
            if item.version is None and len(items) > 1:
                set_verdict(item, Status.UNKNOWN, Role.EXCLUDED, "version_missing")
                superseded.add(item.item_id)
        eligible_versions = [
            i.version
            for i in versioned
            if policy.as_of_version is None or i.version <= policy.as_of_version
        ]
        target = max(eligible_versions) if eligible_versions else None
        for item in versioned:
            if target is None or item.version != target:
                reason = (
                    "superseded"
                    if (target is not None and item.version < target)
                    else "after_standpoint"
                )
                set_verdict(item, Status.INELIGIBLE, Role.EXCLUDED, reason)
                superseded.add(item.item_id)
    live = [i for i in live if i.item_id not in superseded]

    # 4. Provenance: factual conflicts among what is still live.
    conflict_no = 0
    by_claim = defaultdict(list)
    for item in live:
        if item.claim_key is not None and item.claim_value is not None:
            by_claim[item.claim_key].append(item)
    canonical = dict(policy.canonical_sources)
    for key, items in sorted(by_claim.items()):
        if len({i.claim_value for i in items}) < 2:
            continue
        conflict_no += 1
        group = f"factual-{conflict_no}"
        source = canonical.get(key)
        winners = [i for i in items if i.source_id == source] if source else []
        if winners:
            for item in items:
                if item in winners:
                    set_verdict(item, Status.ELIGIBLE, Role.DATA, "canonical_source", group)
                else:
                    set_verdict(item, Status.INELIGIBLE, Role.EXCLUDED, "not_canonical", group)
            conflicts.append(
                Conflict(
                    group,
                    "factual",
                    tuple(i.item_id for i in items),
                    ConflictStatus.RESOLVED,
                    winners[0].item_id,
                )
            )
        else:
            for item in items:
                set_verdict(item, Status.ELIGIBLE, Role.DATA, "conflict_unresolved", group)
            conflicts.append(
                Conflict(
                    group, "factual", tuple(i.item_id for i in items), ConflictStatus.UNRESOLVED
                )
            )

    # 5. Directives: authority decides; equal authority is unresolved.
    directives = [i for i in live if i.directs is not None and i.item_id not in verdicts]
    for item in directives:
        rank = _rank(policy, item.channel)
        if rank is None:
            # Tool output, quoted text, a payload calling itself "system": data only.
            set_verdict(item, Status.ELIGIBLE, Role.DATA, "no_instruction_authority")
    by_action: dict[str, list[CandidateMetadata]] = defaultdict(list)
    for item in directives:
        if item.item_id not in verdicts:
            by_action[item.directs[1]].append(item)
    for action, items in sorted(by_action.items()):
        modes = {i.directs[0] for i in items}
        if len(modes) < 2:
            for item in items:
                set_verdict(item, Status.ELIGIBLE, Role.CONTROL, "authorised_directive")
            continue
        conflict_no += 1
        group = f"instruction-{conflict_no}"
        top = max(_rank(policy, i.channel) for i in items)
        leaders = [i for i in items if _rank(policy, i.channel) == top]
        leader_modes = {i.directs[0] for i in leaders}
        if len(leader_modes) == 1:
            for item in items:
                if item in leaders:
                    set_verdict(item, Status.ELIGIBLE, Role.CONTROL, "highest_authority", group)
                else:
                    set_verdict(
                        item, Status.INELIGIBLE, Role.EXCLUDED, "overridden_by_authority", group
                    )
            conflicts.append(
                Conflict(
                    group,
                    "instruction",
                    tuple(i.item_id for i in items),
                    ConflictStatus.RESOLVED,
                    leaders[0].item_id,
                )
            )
        else:
            for item in items:
                set_verdict(item, Status.ELIGIBLE, Role.CONTROL, "equal_authority_conflict", group)
            conflicts.append(
                Conflict(
                    group, "instruction", tuple(i.item_id for i in items), ConflictStatus.UNRESOLVED
                )
            )

    # 6. Everything still undecided is ordinary evidence, and eligible as data.
    for item in candidates:
        if item.item_id not in verdicts:
            role = (
                Role.CONTROL
                if (item.channel in policy.authority_order and item.directs)
                else Role.DATA
            )
            set_verdict(item, Status.ELIGIBLE, role, "in_scope_current")

    ordered = tuple(verdicts[i.item_id] for i in candidates)
    return Resolution(ordered, tuple(conflicts))


def derive_flags(candidates: list[CandidateMetadata], policy: Policy) -> dict[str, dict[str, bool]]:
    """Adapt a resolution to the boolean flags the existing compiler consumes.

    The compiler keeps its interface (`scope_eligible`, `freshness_eligible`,
    `authority_eligible`); the values are now derived instead of supplied. UNKNOWN
    is not eligible.
    """
    resolution = resolve(candidates, policy)
    flags: dict[str, dict[str, bool]] = {}
    for verdict in resolution.verdicts:
        reason = verdict.reason
        ok = verdict.status is Status.ELIGIBLE
        flags[verdict.item_id] = {
            "scope_eligible": ok or reason not in ("scope_missing", "scope_mismatch"),
            "freshness_eligible": ok
            or reason not in ("superseded", "after_standpoint", "version_missing"),
            "authority_eligible": ok
            or reason
            not in (
                "delegation_unverifiable",
                "delegation_revision_changed",
                "overridden_by_authority",
                "not_canonical",
            ),
        }
    return flags
