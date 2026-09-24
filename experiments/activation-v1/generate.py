"""Deterministic held-out activation case generator.

Builds novel ledger/request combinations from construction rules with an
oracle computed BY CONSTRUCTION from an independent implementation of
the documented activation semantics. The generator imports the settled
Stage 6A projection machinery but never the activation engine: held-out
cases test the engine's generality (no id memorisation), not its
correctness (the authored core cases do that).

Committed output under fixtures/activation-v1/heldout/ is canonical;
regenerate only with a new seed recorded in the fixture manifest.

Usage:
    uv run python experiments/activation-v1/generate.py --seed 7 --cases 8
    uv run python experiments/activation-v1/generate.py --seed 7 --cases 8 --check
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from project_context.ledger.events import LedgerEvent
from project_context.ledger.projection import ProjectedItem, project

ROOT = Path(__file__).resolve().parent.parent.parent
HELDOUT = ROOT / "fixtures" / "activation-v1" / "heldout"
MANIFEST = ROOT / "fixtures" / "activation-v1" / "manifest.json"

ITEM_SCHEMA = "project_context.ledger_item.v1"
EVENT_SCHEMA = "project_context.ledger_event.v1"

COMPONENTS = ["billing", "search", "notify", "export", "auth", "cache"]
REPOS = ["ledger-lab", "ledger-lab-2"]
TASKS = ["task-rotate", "task-audit", "task-cleanup"]
OPERATIONS = ["modify", "test", "document", "release"]
KINDS = [
    "obligation",
    "constraint",
    "decision",
    "assumption",
    "unresolved_failure",
    "pending_verification",
    "result",
]
AUTHORITIES = ["user", "project", "tool", "agent"]


def _paths_overlap(left: str, right: str) -> bool:
    a, b = left.rstrip("/"), right.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _oracle(state_items, relationships, request):
    """Independent oracle: state + reason codes per item id.

    Operates on plain dicts built from the projected state. Any
    disagreement with the engine is a real semantic mismatch to resolve
    by editing one side deliberately, never by special-casing ids.
    """
    by_id = {i["item_id"]: i for i in state_items}
    active = set()
    first = {}
    for item_id in sorted(by_id):
        item = by_id[item_id]
        status, verification = item["status"], item["verification"]
        scope = item["scope"]
        if status in (
            "satisfied",
            "failed",
            "cancelled",
            "expired",
            "superseded",
            "contradicted",
        ):
            code = {"superseded": "superseded", "contradicted": "contradicted"}.get(
                status, f"terminal_{status}"
            )
            first[item_id] = ("ineligible", [code])
            continue
        if verification == "contradicted":
            first[item_id] = ("ineligible", ["verification_contradicted"])
            continue
        if scope["repo"] and request.get("repo") and scope["repo"] != request["repo"]:
            first[item_id] = ("ineligible", ["scope_repo_mismatch"])
            continue
        reasons = []
        matched_paths = sorted(
            {p for p in scope["paths"] for q in request["paths"] if _paths_overlap(p, q)}
        )
        if matched_paths:
            reasons.append("scope_path_match")
        if scope["component"] and scope["component"] in request["components"]:
            reasons.append("scope_component_match")
        if scope["task"] and request.get("task") and scope["task"] == request["task"]:
            reasons.append("scope_task_match")
        component_hit = scope["component"] and scope["component"] in request["components"]
        if (
            item["kind"] == "constraint"
            and request.get("operation")
            and (matched_paths or component_hit)
        ):
            reasons.append("operation_in_governed_scope")
        evidence_hits = sorted(
            {e["ref"] for e in item["evidence"] if e["ref"] in request["evidence_refs"]}
        )
        if evidence_hits:
            reasons.append("evidence_match")
        deps = [
            r["target_id"]
            for r in relationships
            if r["type"] == "depends_on" and r["source_id"] == item_id
        ]
        unmet = [
            d
            for d in deps
            if not (
                by_id[d]["status"] == "satisfied" or by_id[d]["verification"] == "verified"
            )
        ]
        if item["kind"] == "obligation" and deps and not unmet and reasons:
            reasons.append("dependency_ready")
        if item["kind"] == "obligation" and unmet:
            dep_scope_hit = [
                d
                for d in unmet
                if _dep_scope_overlap(by_id[d], request)
            ]
            if dep_scope_hit:
                first[item_id] = (
                    "active",
                    sorted(reasons + ["blocking_condition_relevant"]),
                )
                active.add(item_id)
            else:
                first[item_id] = ("dormant", ["blocked_dependency_unmet"])
            continue
        if reasons:
            first[item_id] = ("active", sorted(reasons))
            active.add(item_id)
            continue
        if not _request_usable(request):
            first[item_id] = ("unknown", ["request_features_absent"])
            continue
        if not _item_has_scope(scope) and not evidence_hits:
            first[item_id] = ("unknown", ["insufficient_scope_to_decide"])
            continue
        first[item_id] = ("dormant", ["no_activation_reason"])
    # One bounded propagation pass over the snapshot.
    final = dict(first)
    for item_id in sorted(by_id):
        state, reasons = first[item_id]
        if state in ("active", "ineligible"):
            continue
        deps = [
            r["target_id"]
            for r in relationships
            if r["type"] == "depends_on" and r["source_id"] == item_id
        ]
        triggering = sorted(d for d in deps if d in active)
        if triggering:
            final[item_id] = ("active", sorted(set(reasons) | {"dependency_active"}))
    return final


def _dep_scope_overlap(target, request):
    scope = target["scope"]
    if any(_paths_overlap(p, q) for p in scope["paths"] for q in request["paths"]):
        return True
    return bool(scope["component"] and scope["component"] in request["components"])


def _request_usable(request):
    return bool(
        request.get("repo")
        or request.get("paths")
        or request.get("components")
        or request.get("task")
        or request.get("operation")
        or request.get("evidence_refs")
    )


def _item_has_scope(scope):
    return bool(scope["repo"] or scope["paths"] or scope["component"] or scope["task"])


def _make_case(rng, index):
    n_items = rng.randint(2, 5)
    kinds = [rng.choice(KINDS) for _ in range(n_items)]
    ids = [f"h{index:02d}-{n:02d}" for n in range(n_items)]
    events = []
    clock = [0]

    def stamp():
        clock[0] += 1
        return f"2026-10-{index + 1:02d}T10:{clock[0]:02d}:00Z"

    items = {}
    for item_id, kind in zip(ids, kinds):
        repo = rng.choice(REPOS + [None, None])
        component = rng.choice(COMPONENTS + [None])
        paths = (
            [f"src/ledger_lab/{component}/mod{rng.randint(1, 3)}"]
            if component and rng.random() < 0.7
            else []
        )
        task = rng.choice(TASKS + [None, None]) if rng.random() < 0.3 else None
        # Sometimes a fully scopeless item to exercise abstention.
        if rng.random() < 0.15:
            repo, component, paths, task = None, None, [], None
        items[item_id] = {"kind": kind, "repo": repo, "component": component}
        events.append(
            {
                "schema_version": EVENT_SCHEMA,
                "event_id": f"evt-{item_id}-create",
                "event": "item_created",
                "item_id": item_id,
                "recorded_at": stamp(),
                "item": {
                    "schema_version": ITEM_SCHEMA,
                    "item_id": item_id,
                    "kind": kind,
                    "statement": f"generated {kind} {item_id}",
                    "authority": rng.choice(AUTHORITIES),
                    "scope": {
                        "repo": repo,
                        "workspace": None,
                        "branch": None,
                        "paths": paths,
                        "component": component,
                        "task": task,
                        "session": None,
                        "agent": None,
                    },
                    "source": {"session": None, "invocation": None, "note": "generated"},
                },
            }
        )
    relationships = []
    order = rng.sample(ids, len(ids))
    # A supersede pair, a contradict pair, and a short depends_on chain.
    if len(order) >= 2 and rng.random() < 0.6:
        src, tgt = order[0], order[1]
        relationships.append({"type": "supersedes", "source_id": src, "target_id": tgt})
    if len(order) >= 4 and rng.random() < 0.6:
        src, tgt = order[2], order[3]
        relationships.append({"type": "contradicts", "source_id": src, "target_id": tgt})
    if len(order) >= 2 and rng.random() < 0.7:
        src, tgt = order[-1], order[-2]
        relationships.append({"type": "depends_on", "source_id": src, "target_id": tgt})
    for n, rel in enumerate(relationships):
        events.append(
            {
                "schema_version": EVENT_SCHEMA,
                "event_id": f"evt-h{index:02d}-rel-{n}",
                "event": "relationship_added",
                "item_id": rel["source_id"],
                "recorded_at": stamp(),
                "relationship": rel,
            }
        )
    # Verifications: some pass, some fail. A failed outcome on a
    # superseded/contradicted target would be an illegal transition, so
    # only verify items that are still active or blocked.
    from project_context.ledger.projection import project as _project

    trial = [LedgerEvent.from_dict(e) for e in events]
    live = [
        i.item.item_id
        for i in _project(trial).items
        if i.status.value in ("active", "blocked")
    ]
    for item_id in live:
        roll = rng.random()
        if roll < 0.35:
            outcome = "passed"
        elif roll < 0.5:
            outcome = "failed"
        else:
            continue
        ref = (
            f"pytest tests/test_{items[item_id]['component'] or 'misc'}.py"
            if rng.random() < 0.7
            else f"bench/h{index:02d}.json"
        )
        events.append(
            {
                "schema_version": EVENT_SCHEMA,
                "event_id": f"evt-{item_id}-verify",
                "event": "verified",
                "item_id": item_id,
                "recorded_at": stamp(),
                "outcome": outcome,
                "evidence": {"kind": "test_run", "ref": ref, "detail": "generated"},
            }
        )
    # Requests: one or two, sometimes bare, sometimes cross-repo.
    requests = []
    n_requests = rng.randint(1, 2)
    for r in range(n_requests):
        bare = rng.random() < 0.2
        anchor = rng.choice(ids)
        acomp = items[anchor]["component"]
        request = {
            "schema_version": "project_context.activation_request.v1",
            "request_id": f"req-h{index:02d}-{r}",
            "task_id": f"task-h{index:02d}",
            "created_at": "2026-10-09T11:00:00Z",
            "repo": None if bare else rng.choice(REPOS),
            "workspace": None,
            "branch": None,
            "paths": []
            if bare
            else ([f"src/ledger_lab/{acomp}"] if acomp and rng.random() < 0.6 else []),
            "components": [] if bare else ([acomp] if acomp and rng.random() < 0.6 else []),
            "task": None,
            "operation": None if bare else rng.choice(OPERATIONS + [None]),
            "evidence_refs": [],
        }
        if rng.random() < 0.4 and not bare:
            request["evidence_refs"] = [f"pytest tests/test_{rng.choice(COMPONENTS)}.py"]
        requests.append(request)
    return f"held-{index:02d}", events, requests


def _state_dicts(events):
    parsed = [LedgerEvent.from_dict(e) for e in events]
    state = project(parsed)
    items = []
    for entry in state.items:
        assert isinstance(entry, ProjectedItem)
        items.append(
            {
                "item_id": entry.item.item_id,
                "kind": entry.item.kind.value,
                "status": entry.status.value,
                "verification": entry.verification.value,
                "scope": {
                    "repo": entry.item.scope.repo,
                    "paths": list(entry.item.scope.paths),
                    "component": entry.item.scope.component,
                    "task": entry.item.scope.task,
                },
                "evidence": [
                    {"ref": e.get("ref")} for e in entry.evidence if e.get("ref")
                ],
            }
        )
    rels = [
        {"type": r.type.value, "source_id": r.source_id, "target_id": r.target_id}
        for r in state.relationships
    ]
    return items, rels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--cases", type=int, required=True)
    parser.add_argument("--check", action="store_true", help="regenerate and compare only")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    generated = {}
    for index in range(args.cases):
        case_id, events, requests = _make_case(rng, index)
        items, rels = _state_dicts(events)  # raises on any illegal stream
        truth = {
            req["request_id"]: {
                item_id: {"state": s, "reasons": r}
                for item_id, (s, r) in _oracle(items, rels, req).items()
            }
            for req in requests
        }
        generated[case_id] = (events, requests, truth)
    if args.check:
        failures = []
        for case_id, (events, requests, truth) in generated.items():
            case_dir = HELDOUT / case_id
            disk_events = (case_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if [json.dumps(e, sort_keys=True) for e in events] != [
                json.dumps(json.loads(line), sort_keys=True) for line in disk_events if line.strip()
            ]:
                failures.append(f"{case_id}/events.jsonl differs")
            disk_truth = json.loads((case_dir / "truth.json").read_text())
            if disk_truth["requests"] != truth:
                failures.append(f"{case_id}/truth.json differs")
        if failures:
            for failure in failures:
                print(f"HELD-OUT MISMATCH: {failure}")
            return 1
        print(f"held-out clean: {len(generated)} cases match seed {args.seed}")
        return 0
    for case_id, (events, requests, truth) in generated.items():
        case_dir = HELDOUT / case_id
        req_dir = case_dir / "requests"
        req_dir.mkdir(parents=True, exist_ok=True)
        with (case_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
        for req in requests:
            (req_dir / f"{req['request_id']}.json").write_text(
                json.dumps(req, sort_keys=True) + "\n", encoding="utf-8"
            )
        (case_dir / "truth.json").write_text(
            json.dumps({"requests": truth}, sort_keys=True) + "\n", encoding="utf-8"
        )
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["heldout"] = {
        "cases": sorted(generated),
        "generator": "experiments/activation-v1/generate.py",
        "seed": args.seed,
    }
    MANIFEST.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(generated)} held-out cases (seed {args.seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
