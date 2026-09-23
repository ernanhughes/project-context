"""Build compiler-v1 fixture JSON deterministically. SYNTHETIC ONLY.

Run once: python3 build_fixtures.py  (from this directory)
Emits fixtures/compiler-v1/*.candidates.json, *.request.json,
*.truth.json, and manifest.json with sorted keys.

Token counts are STIPULATED fixture inputs (token_source
"fixture-declared"), not measurements of the short synthetic strings:
they encode the cost regime each fixture is designed to test. Budgets
are pre-registered constants chosen from fixture structure before any
strategy runs; they are never tuned to strategy outcomes.

All content uses synthetic names. No private data. Nothing here is book
evidence: see the manifest evidence label.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent.parent / "fixtures" / "compiler-v1"

CREATED_AT = "2026-09-23T00:00:00Z"
ACTIVE_SCOPE = "synthetic-project-a"
POLICY_VERSION = "compiler-policy-v1"
FIXTURE_VERSION = "1"


def cand(
    cid: str,
    identity: str,
    rep: str,
    content: str,
    tokens: int,
    requirement: str,
    role: str,
    relevance: float,
    *,
    form_rank: int = 3,
    min_rank: int = 0,
    source_kind: str = "synthetic-fixture",
    source_ref: str = "compiler-v1",
    kind: str = "evidence",
    order_role: str | None = None,
    eligible: bool = True,
    ineligibility: str = "",
    depends_on: tuple[str, ...] = (),
    group_id: str | None = None,
    group_required: bool = False,
    coverage: tuple[str, ...] = (),
    default_form: bool = False,
) -> dict:
    scope_ok, fresh_ok, auth_ok = True, True, True
    scope_reason, fresh_reason, auth_reason = "in scope", "validated current", "data"
    if not eligible:
        if ineligibility.startswith("scope"):
            scope_ok, scope_reason = False, ineligibility
        elif ineligibility.startswith("fresh"):
            fresh_ok, fresh_reason = False, ineligibility
        else:
            auth_ok, auth_reason = False, ineligibility or "not authorised"
    return {
        "candidate_id": cid,
        "content_identity": identity,
        "representation_id": rep,
        "form_rank": form_rank,
        "min_rank": min_rank,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "kind": kind,
        "content": content,
        "token_count": tokens,
        "token_source": "fixture-declared",
        "requirement": requirement,
        "order_role": order_role or role,
        "scope_eligible": scope_ok,
        "scope_reason": scope_reason,
        "freshness_eligible": fresh_ok,
        "freshness_reason": fresh_reason,
        "authority_eligible": auth_ok,
        "authority_reason": auth_reason,
        "depends_on": list(depends_on),
        "group_id": group_id,
        "group_required": group_required,
        "coverage_keys": list(coverage),
        "relevance": relevance,
        "is_default_form": default_form,
    }


def base_pair() -> list[dict]:
    return [
        cand(
            "instr-1",
            "instr",
            "full",
            "Application constraint (synthetic): never modify generated files.",
            60,
            "MANDATORY",
            "instruction",
            1.0,
            coverage=("constraint",),
            default_form=True,
        ),
        cand(
            "taskreq-1",
            "taskreq",
            "full",
            "Investigate the migration failure (synthetic).",
            40,
            "MANDATORY",
            "task",
            1.0,
            default_form=True,
        ),
    ]


def truth(classes: dict[str, tuple[str, str | None]], success=True, reason=None) -> dict:
    return {
        "identity_truth": {
            identity: {"eval_class": cls, "min_representation": rep}
            for identity, (cls, rep) in classes.items()
        },
        "expected": {"success": success, "reason": reason},
    }


def request(name: str, budget: int, required: tuple[str, ...] = ()) -> dict:
    return {
        "request_id": f"{name}-req",
        "task_id": f"{name}-task",
        "usable_token_budget": budget,
        "created_at": CREATED_AT,
        "active_scope": ACTIVE_SCOPE,
        "required_ids": list(required),
        "policy_version": POLICY_VERSION,
    }


FIXTURES: dict[str, dict] = {}


def add(
    name: str,
    candidates: list[dict],
    budgets: dict[str, int],
    classes: dict,
    required: tuple[str, ...] = (),
    success: bool | dict = True,
) -> None:
    if isinstance(success, dict):
        ok, reason = success["success"], success.get("reason")
    else:
        ok, reason = bool(success), None
    FIXTURES[name] = {
        "candidates": candidates,
        "request": request(name, budgets["medium"], required),
        "budgets": budgets,
        "truth": truth(classes, ok, reason),
    }


# --- base pairs reused across fixtures -------------------------------------
BASE = base_pair()
BASE_TRUTH = {"instr": ("must", "full"), "taskreq": ("must", "full")}

# 1. dependency trap: cheap reference needs an expensive resolver.
add(
    "dependency-trap",
    BASE
    + [
        cand(
            "ref-cheap",
            "incident",
            "reference",
            "Incident syn-17 resolved (synthetic reference).",
            20,
            "DISCRETIONARY",
            "evidence",
            0.9,
            form_rank=0,
            depends_on=("resolver-tool",),
            default_form=True,
        ),
        cand(
            "full-alt",
            "incident",
            "full",
            "Full incident syn-17 record (synthetic): lock-order inversion, fixed.",
            400,
            "DISCRETIONARY",
            "evidence",
            0.7,
            form_rank=3,
        ),
        cand(
            "resolver-tool",
            "resolver",
            "full",
            "Artifact resolver capability (synthetic): reads external artifacts.",
            650,
            "PREFERRED",
            "tool",
            0.2,
            default_form=True,
        ),
        cand(
            "distract-big",
            "distract-big",
            "full",
            "Unrelated subsystem notes (synthetic).",
            300,
            "DISCRETIONARY",
            "support",
            0.6,
            default_form=True,
        ),
    ],
    {"tight": 900, "medium": 1400, "roomy": 2200},
    {
        **BASE_TRUTH,
        "incident": ("should", "reference"),
        "resolver": ("should", "full"),
        "distract-big": ("distractor", "full"),
    },
)

# 2. qualification trap: claim + exception travel together.
# The exception carries lower relevance than the distractor so that
# relevance-greedy baselines admit the claim without its qualifier in the
# tight regime while the staged compiler preserves the group.
add(
    "qualification-trap",
    BASE
    + [
        cand(
            "claim-positive",
            "claim-positive",
            "full",
            "Migration completed successfully (synthetic).",
            120,
            "REQUIRED",
            "evidence",
            0.8,
            group_id="mig-result",
            group_required=True,
            default_form=True,
        ),
        cand(
            "exception-tenant",
            "exception-tenant",
            "full",
            "Except tenant 042 remains pending (synthetic).",
            80,
            "REQUIRED",
            "evidence",
            0.35,
            group_id="mig-result",
            group_required=True,
            default_form=True,
        ),
        cand(
            "distract-2",
            "distract-2",
            "full",
            "Old roadmap notes (synthetic).",
            200,
            "DISCRETIONARY",
            "support",
            0.55,
            default_form=True,
        ),
    ],
    {"tight": 480, "medium": 800, "roomy": 1500},
    # NOTE (pre-registration record): tight is calibrated so relevance-greedy
    # baselines admit the claim plus the higher-relevance distractor but not
    # the lower-relevance qualifier (group violation), while staged preserves
    # the required group and drops the distractor instead. Verified
    # structurally at 460/480/500 before any frozen run; the value tests the
    # mechanism, not a tuned outcome.
    {
        **BASE_TRUTH,
        "claim-positive": ("must", "full"),
        "exception-tenant": ("must", "full"),
        "distract-2": ("distractor", "full"),
    },
)

# 3. conflict trap: two claims plus marker stay grouped.
add(
    "conflict-trap",
    BASE
    + [
        cand(
            "claim-a",
            "claim-a",
            "full",
            "Database is PostgreSQL (synthetic decision record).",
            60,
            "REQUIRED",
            "evidence",
            0.8,
            group_id="conflict-db",
            group_required=True,
            default_form=True,
        ),
        cand(
            "claim-b",
            "claim-b",
            "full",
            "Database is SQLite (synthetic readme).",
            60,
            "REQUIRED",
            "evidence",
            0.8,
            group_id="conflict-db",
            group_required=True,
            default_form=True,
        ),
        cand(
            "conflict-marker",
            "conflict-marker",
            "full",
            "Conflict preserved: sources disagree (synthetic).",
            40,
            "REQUIRED",
            "evidence",
            0.7,
            group_id="conflict-db",
            group_required=True,
            default_form=True,
        ),
    ],
    {"tight": 450, "medium": 800, "roomy": 1500},
    {
        **BASE_TRUTH,
        "claim-a": ("must", "full"),
        "claim-b": ("must", "full"),
        "conflict-marker": ("must", "full"),
    },
)

# 4. stale-cheap trap: cheap form ineligible, fresh form costly.
add(
    "stale-cheap",
    BASE
    + [
        cand(
            "stale-compact",
            "obs-state",
            "compact",
            "Compact branch state (synthetic, superseded).",
            100,
            "DISCRETIONARY",
            "evidence",
            0.9,
            form_rank=2,
            eligible=False,
            ineligibility="freshness: superseded by newer observation",
            default_form=True,
        ),
        cand(
            "fresh-full",
            "obs-state",
            "full",
            "Current branch state (synthetic, validated).",
            600,
            "DISCRETIONARY",
            "evidence",
            0.75,
            form_rank=3,
        ),
    ],
    {"tight": 800, "medium": 1200, "roomy": 2000},
    {**BASE_TRUTH, "obs-state": ("must", "full")},
)

# 5. wrong-scope trap: top relevance, wrong world.
add(
    "wrong-scope",
    BASE
    + [
        cand(
            "scope-out",
            "scope-out",
            "full",
            "Project B config (synthetic, other world).",
            50,
            "DISCRETIONARY",
            "evidence",
            0.99,
            eligible=False,
            ineligibility="scope: project-b, active synthetic-project-a",
            default_form=True,
        ),
        cand(
            "good-evidence",
            "good-evidence",
            "full",
            "Project A migration log excerpt (synthetic).",
            150,
            "PREFERRED",
            "evidence",
            0.7,
            coverage=("migration",),
            default_form=True,
        ),
    ],
    {"tight": 500, "medium": 900, "roomy": 1800},
    {**BASE_TRUTH, "good-evidence": ("should", "full"), "scope-out": ("distractor", "full")},
)

# 6. mandatory overflow: legal minimum exceeds every budget.
add(
    "mandatory-overflow",
    [
        cand(
            "mand-a",
            "mand-a",
            "full",
            "First mandatory constraint block (synthetic).",
            2000,
            "MANDATORY",
            "instruction",
            1.0,
            default_form=True,
        ),
        cand(
            "mand-b",
            "mand-b",
            "full",
            "Second mandatory constraint block (synthetic).",
            2500,
            "MANDATORY",
            "task",
            1.0,
            default_form=True,
        ),
        cand(
            "small-disc",
            "small-disc",
            "full",
            "Small optional note (synthetic).",
            50,
            "DISCRETIONARY",
            "support",
            0.5,
            default_form=True,
        ),
    ],
    {"tight": 4000, "medium": 4400, "roomy": 5000},
    {"mand-a": ("must", "full"), "mand-b": ("must", "full"), "small-disc": ("optional", "full")},
    success={"success": False, "reason": "INSUFFICIENT_BUDGET"},
)
# NOTE: roomy 5000 fits the 4500 mandatory sum; expected outcome for roomy
# is success. Per-regime expectations differ, so expected is recorded per
# budget in the manifest override below.

# 7. budget slack: roomy budget must stay mostly empty.
add(
    "budget-slack",
    BASE
    + [
        cand(
            "useful-disc",
            "useful-disc",
            "full",
            "Useful migration note (synthetic).",
            150,
            "DISCRETIONARY",
            "evidence",
            0.8,
            coverage=("migration",),
            default_form=True,
        ),
        cand(
            "distract-d1",
            "distract-d1",
            "full",
            "Unrelated archive notes, part one (synthetic).",
            400,
            "DISCRETIONARY",
            "support",
            0.15,
            default_form=True,
        ),
        cand(
            "distract-d2",
            "distract-d2",
            "full",
            "Unrelated archive notes, part two (synthetic).",
            500,
            "DISCRETIONARY",
            "support",
            0.2,
            default_form=True,
        ),
    ],
    {"tight": 300, "medium": 600, "roomy": 3000},
    {
        **BASE_TRUTH,
        "useful-disc": ("should", "full"),
        "distract-d1": ("distractor", "full"),
        "distract-d2": ("distractor", "full"),
    },
)

# 8. representation alternatives: one identity, four legal forms.
add(
    "representation-alternatives",
    BASE
    + [
        cand(
            "inc-full",
            "incident",
            "full",
            "Full incident syn-17 record (synthetic).",
            900,
            "REQUIRED",
            "evidence",
            0.7,
            form_rank=3,
        ),
        cand(
            "inc-compact",
            "incident",
            "compact",
            "Compact incident syn-17 record (synthetic).",
            300,
            "REQUIRED",
            "evidence",
            0.75,
            form_rank=2,
        ),
        cand(
            "inc-anchor",
            "incident",
            "anchor",
            "Incident syn-17 anchor (synthetic).",
            90,
            "REQUIRED",
            "evidence",
            0.8,
            form_rank=1,
            default_form=True,
        ),
        cand(
            "inc-ref",
            "incident",
            "reference",
            "Incident syn-17 reference (synthetic).",
            20,
            "REQUIRED",
            "evidence",
            0.85,
            form_rank=0,
            depends_on=("alt-resolver",),
        ),
        cand(
            "alt-resolver",
            "alt-resolver",
            "full",
            "Artifact resolver capability (synthetic).",
            150,
            "PREFERRED",
            "tool",
            0.2,
            default_form=True,
        ),
    ],
    {"tight": 550, "medium": 700, "roomy": 2000},
    {**BASE_TRUTH, "incident": ("must", "compact"), "alt-resolver": ("optional", "full")},
)

# NOTE (pre-registration record): tight was 400 in the first builder draft,
# which made the oracle's minimum-sufficient compact form infeasible while
# staged succeeded with the anchor. That confounds ceiling with policy, so
# tight moved to 550 (fits mandatory + compact + overhead) before any frozen
# run. No strategy outcome was consulted; the change makes the oracle
# feasible in every regime by construction.

# 9. shared dependency: two references, one resolver, paid once.
add(
    "shared-dependency",
    BASE
    + [
        cand(
            "tool-def",
            "tool-def",
            "full",
            "Shared artifact-read capability (synthetic).",
            300,
            "PREFERRED",
            "tool",
            0.3,
            default_form=True,
        ),
        cand(
            "ref-a",
            "ref-a",
            "reference",
            "First artifact reference (synthetic).",
            20,
            "PREFERRED",
            "evidence",
            0.7,
            form_rank=0,
            depends_on=("tool-def",),
            default_form=True,
        ),
        cand(
            "ref-b",
            "ref-b",
            "reference",
            "Second artifact reference (synthetic).",
            25,
            "PREFERRED",
            "evidence",
            0.65,
            form_rank=0,
            depends_on=("tool-def",),
            default_form=True,
        ),
    ],
    {"tight": 600, "medium": 900, "roomy": 1800},
    {
        **BASE_TRUTH,
        "tool-def": ("should", "full"),
        "ref-a": ("should", "reference"),
        "ref-b": ("should", "reference"),
    },
)

# 10. required source unavailable: request names a ghost.
add(
    "required-unavailable",
    BASE,
    {"tight": 500, "medium": 900, "roomy": 1800},
    dict(BASE_TRUTH),
    required=("ghost-1",),
    success={"success": False, "reason": "REQUIRED_SOURCE_UNAVAILABLE"},
)

# 11. no legal representation: mandatory form violates its floor.
add(
    "no-legal-representation",
    BASE
    + [
        cand(
            "mand-low",
            "mand-low",
            "compact",
            "Mandatory summary below its exactness floor (synthetic).",
            120,
            "MANDATORY",
            "evidence",
            0.9,
            form_rank=2,
            min_rank=3,
            default_form=True,
        ),
    ],
    {"tight": 800, "medium": 1200, "roomy": 2000},
    {**BASE_TRUTH, "mand-low": ("must", "full")},
    success={"success": False, "reason": "NO_LEGAL_REPRESENTATION"},
)

# 12. dependency cycle: finite, affordable, must terminate.
add(
    "dependency-cycle",
    BASE
    + [
        cand(
            "cyc-a",
            "cyc-a",
            "full",
            "First cyclic note (synthetic).",
            100,
            "PREFERRED",
            "evidence",
            0.6,
            depends_on=("cyc-b",),
            default_form=True,
        ),
        cand(
            "cyc-b",
            "cyc-b",
            "full",
            "Second cyclic note (synthetic).",
            120,
            "PREFERRED",
            "evidence",
            0.6,
            depends_on=("cyc-a",),
            default_form=True,
        ),
    ],
    {"tight": 500, "medium": 900, "roomy": 1800},
    {**BASE_TRUTH, "cyc-a": ("should", "full"), "cyc-b": ("should", "full")},
)

# 13. rendered overflow: estimates fit, render overhead does not.
add(
    "rendered-overflow",
    BASE
    + [
        cand(
            "disc-a",
            "disc-a",
            "full",
            "Discretionary note sized to the edge (synthetic).",
            150,
            "DISCRETIONARY",
            "evidence",
            0.8,
            default_form=True,
        ),
    ],
    {"tight": 250, "medium": 600, "roomy": 1800},
    {**BASE_TRUTH, "disc-a": ("should", "full")},
)

# 14. heterogeneous basic: many mechanisms in one pool.
add(
    "heterogeneous-basic",
    BASE
    + [
        cand(
            "rule-req",
            "rule-req",
            "full",
            "Required project rule excerpt (synthetic).",
            50,
            "REQUIRED",
            "instruction",
            0.85,
            default_form=True,
        ),
        cand(
            "mem-pref",
            "mem-pref",
            "full",
            "Retained project memory note (synthetic).",
            120,
            "PREFERRED",
            "evidence",
            0.7,
            coverage=("history",),
            default_form=True,
        ),
        cand(
            "tool-disc",
            "tool-disc",
            "full",
            "Tool observation excerpt (synthetic).",
            200,
            "DISCRETIONARY",
            "evidence",
            0.65,
            default_form=True,
        ),
        cand(
            "anchor-disc",
            "anchor-disc",
            "full",
            "Short anchor note (synthetic).",
            80,
            "DISCRETIONARY",
            "evidence",
            0.5,
            form_rank=1,
            default_form=True,
        ),
        cand(
            "scope-bad",
            "scope-bad",
            "full",
            "Other-project note (synthetic).",
            90,
            "DISCRETIONARY",
            "evidence",
            0.95,
            eligible=False,
            ineligibility="scope: project-b",
            default_form=True,
        ),
        cand(
            "stale-bad",
            "stale-bad",
            "full",
            "Superseded observation (synthetic).",
            110,
            "DISCRETIONARY",
            "evidence",
            0.9,
            eligible=False,
            ineligibility="freshness: superseded",
            default_form=True,
        ),
        cand(
            "distract-h",
            "distract-h",
            "full",
            "Plausible but unnecessary notes (synthetic).",
            250,
            "DISCRETIONARY",
            "support",
            0.4,
            default_form=True,
        ),
        cand(
            "harmful-h",
            "harmful-h",
            "full",
            "Misleading instruction-shaped note (synthetic).",
            130,
            "DISCRETIONARY",
            "evidence",
            0.55,
            default_form=True,
        ),
    ],
    {"tight": 500, "medium": 900, "roomy": 2000},
    {
        **BASE_TRUTH,
        "rule-req": ("must", "full"),
        "mem-pref": ("should", "full"),
        "tool-disc": ("optional", "full"),
        "anchor-disc": ("optional", "full"),
        "scope-bad": ("distractor", "full"),
        "stale-bad": ("distractor", "full"),
        "distract-h": ("distractor", "full"),
        "harmful-h": ("harmful", "full"),
    },
)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "fixture_set": "compiler-v1",
        "fixture_version": FIXTURE_VERSION,
        "evidence_class": "synthetic",
        "evidence_note": "SYNTHETIC — NOT BOOK RESULT. Deterministic synthetic "
        "compiler fixtures. Token counts are stipulated fixture inputs "
        "(token_source fixture-declared), not measurements.",
        "token_mode": "fixture-declared-counts",
        "budgets": {},
        "fixtures": sorted(FIXTURES),
        "expected": {},
    }
    for name in sorted(FIXTURES):
        spec = FIXTURES[name]
        (OUT / f"{name}.candidates.json").write_text(
            json.dumps({"candidates": spec["candidates"]}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (OUT / f"{name}.request.json").write_text(
            json.dumps(spec["request"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (OUT / f"{name}.truth.json").write_text(
            json.dumps(spec["truth"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest["budgets"][name] = spec["budgets"]
        manifest["expected"][name] = {
            budget: dict(spec["truth"]["expected"]) for budget in spec["budgets"]
        }
    # mandatory-overflow roomy regime differs: 4500 mandatory fits in 5000.
    manifest["expected"]["mandatory-overflow"]["roomy"] = {
        "success": True,
        "reason": None,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(FIXTURES)} fixtures to {OUT}")


if __name__ == "__main__":
    main()
