"""contextlab CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from project_context.compiler.fixtures import (
    load_candidate_file,
    load_fixture_set,
    load_request_file,
)
from project_context.compiler.policy import CompilerPolicy
from project_context.corpus.campaign import STATUS_OPEN, CampaignManifest
from project_context.corpus.campaign_store import (
    add_spool,
    load_campaign,
    save_campaign,
    save_local_index,
)
from project_context.domain.evaluation import EvaluationLog
from project_context.domain.runs import RunManifest
from project_context.fixtures.base import render_visible_text
from project_context.fixtures.reference import FIXTURE_ID, get_fixture
from project_context.opencode.bridge import (
    BRIDGE_SCHEMA_V1,
    load_capture_dir,
    load_capture_file,
    validate_record,
)
from project_context.opencode.ingest import SequenceTracker, ingest_record
from project_context.opencode.prevalence import (
    analyse_bundles,
    assert_exportable,
    bundle_bytes,
    bundle_chars,
    churn_positions,
    composition_report,
    dist,
    duration_minutes,
    export_report,
    prefix_survival,
    repetition_report,
    session_bundles,
    session_timeline,
    session_weighted_tool_share,
    tool_result_stats,
)
from project_context.runs.artifacts import vcs_info, write_artifact

FIXTURES = {FIXTURE_ID: get_fixture}

CREATED_AT = "2026-09-23T00:00:00Z"


def cmd_fixture_list() -> int:
    for name in sorted(FIXTURES):
        fixture = FIXTURES[name]()
        print(f"{fixture.fixture_id} v{fixture.fixture_version}")
    return 0


def _report_text(fixture_id: str) -> str:
    fixture = FIXTURES[fixture_id]()
    built = fixture.build(created_at=CREATED_AT)
    bundle = built.bundle
    sources = Counter(item.source for item in bundle.items)
    kinds = Counter(item.kind for item in bundle.items)
    order_lines = [
        f"  {index:02d} {item.id} ({item.source}/{item.kind})"
        for index, item in enumerate(bundle.items)
    ]
    lines = [
        f"fixture: {built.fixture_id} v{built.fixture_version} [SYNTHETIC]",
        f"bundle: {bundle.id}",
        f"items: {len(bundle.items)}",
        "order:",
        *order_lines,
        "source counts:",
        *[f"  {source}: {count}" for source, count in sorted(sources.items())],
        "kind counts:",
        *[f"  {kind}: {count}" for kind, count in sorted(kinds.items())],
        "token counts (local approximation):",
        *[f"  {item.id}: {item.token_count} [{item.token_provenance}]" for item in bundle.items],
        f"bundle total: {bundle.rendered_token_total()}",
        f"content hash: {bundle.content_hash()}",
        f"probes (hidden, not rendered): {len(fixture.probes())}",
    ]
    return "\n".join(lines) + "\n"


def _report_json(fixture_id: str) -> str:
    fixture = FIXTURES[fixture_id]()
    built = fixture.build(created_at=CREATED_AT)
    bundle = built.bundle
    return (
        json.dumps(
            {
                "fixture_id": built.fixture_id,
                "fixture_version": built.fixture_version,
                "evidence_class": "synthetic",
                "bundle": bundle.to_dict(),
                "rendered_text": render_visible_text(bundle),
                "probe_count": len(fixture.probes()),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def cmd_fixture_inspect(fixture_id: str, output_format: str) -> int:
    if fixture_id not in FIXTURES:
        print(f"unknown fixture: {fixture_id}", file=sys.stderr)
        return 2
    if output_format == "json":
        sys.stdout.write(_report_json(fixture_id))
    else:
        sys.stdout.write(_report_text(fixture_id))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextlab", description="Context Lab instrument (Stage 0)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fixture = sub.add_parser("fixture", help="Work with deterministic fixtures.")
    fixture_sub = fixture.add_subparsers(dest="fixture_command", required=True)
    fixture_sub.add_parser("list", help="List available fixtures.")
    inspect_parser = fixture_sub.add_parser("inspect", help="Inspect a fixture bundle.")
    inspect_parser.add_argument("fixture_id", help="Fixture to inspect.")
    inspect_parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="Report format."
    )

    opencode = sub.add_parser("opencode", help="OpenCode capture records.")
    opencode_sub = opencode.add_subparsers(dest="opencode_command", required=True)
    op_inspect = opencode_sub.add_parser(
        "inspect", help="Structural summary of a capture file (no raw content)."
    )
    op_inspect.add_argument("path", help="Capture .jsonl file or spool directory.")
    op_inspect.add_argument(
        "--show-content",
        action="store_true",
        help="LOCAL ONLY: also print raw item contents. Never use in shared logs.",
    )
    op_ingest = opencode_sub.add_parser(
        "ingest", help="Ingest captures into bundles (derived records only)."
    )
    op_ingest.add_argument("path", help="Capture .jsonl file or spool directory.")

    corpus = sub.add_parser("corpus", help="Corpus-level analysis.")
    corpus_sub = corpus.add_subparsers(dest="corpus_command", required=True)
    prevalence = corpus_sub.add_parser(
        "prevalence", help="Aggregate-only prevalence over captures."
    )
    prevalence.add_argument("path", help="Spool directory of capture .jsonl files.")
    prevalence.add_argument(
        "--export", default=None, help="Write gated aggregate JSON here (checked)."
    )
    prevalence.add_argument(
        "--campaign",
        default=None,
        help="Campaign id for target/gap labelling (no raw-path filtering).",
    )
    prevalence.add_argument(
        "--run-id",
        default=None,
        help="If set, write a frozen local run under --runs-dir.",
    )
    prevalence.add_argument(
        "--runs-dir",
        default=".local/runs",
        help="Local root for frozen runs (git-ignored, never committed).",
    )

    campaign = corpus_sub.add_parser("campaign", help="Collection campaign records.")
    campaign_sub = campaign.add_subparsers(dest="campaign_command", required=True)
    campaign_create = campaign_sub.add_parser("create", help="Create a campaign.")
    campaign_create.add_argument("--id", required=True, help="Campaign identifier.")
    campaign_create.add_argument("--target", type=int, default=10, help="Target genuine sessions.")
    campaign_create.add_argument("--sampling-notes", default="")
    campaign_status = campaign_sub.add_parser("status", help="Campaign readiness.")
    campaign_status.add_argument("--id", required=True, help="Campaign identifier.")
    campaign_add = campaign_sub.add_parser(
        "add", help="Ingest a local spool directory into a campaign."
    )
    campaign_add.add_argument("path", help="Local spool directory.")
    campaign_add.add_argument("--id", required=True, help="Campaign identifier.")
    campaign_add.add_argument(
        "--source-label", required=True, help="Opaque source label (no paths)."
    )

    quality = corpus_sub.add_parser("quality", help="Capture-quality report for a campaign.")
    quality.add_argument("--id", required=True, help="Campaign identifier.")

    compiler = sub.add_parser("compiler", help="Deterministic synthetic compiler.")
    compiler_sub = compiler.add_subparsers(dest="compiler_command", required=True)
    compiler_sub.add_parser("fixtures", help="List compiler-v1 fixtures and budgets.")
    comp_inspect = compiler_sub.add_parser(
        "inspect", help="Compile one fixture and show the trace (synthetic)."
    )
    comp_inspect.add_argument("fixture", help="Fixture name under fixtures/compiler-v1.")
    comp_inspect.add_argument(
        "--strategy",
        default="staged",
        choices=("dump", "topk", "weighted", "gated", "staged", "oracle"),
        help="Assembly strategy.",
    )
    comp_inspect.add_argument(
        "--budget",
        default="tight",
        choices=("tight", "medium", "roomy"),
        help="Budget regime from the fixture manifest.",
    )
    comp_inspect.add_argument(
        "--format", choices=("text", "json"), default="text", help="Report format."
    )
    comp_run = compiler_sub.add_parser("run", help="Run the compiler-v1 suite.")
    comp_run.add_argument("experiment", choices=("compiler-v1",), help="Experiment family to run.")
    comp_run.add_argument("--run-id", default=None, help="Run identifier.")
    comp_run.add_argument("--runs-dir", default=".local/runs", help="Local root for frozen runs.")
    comp_run.add_argument(
        "--policy",
        default="compiler-policy-v1",
        help="Policy file stem under experiments/compiler-v1/policies.",
    )
    comp_run.add_argument(
        "--timestamp", default=None, help="Manifest timestamp (default: now, UTC)."
    )
    comp_validate = compiler_sub.add_parser(
        "validate-run", help="Validate a frozen compiler run directory."
    )
    comp_validate.add_argument("run_dir", help="Run directory to validate.")
    return parser


def _load_records(path_str: str) -> tuple[list[dict], dict[str, int]]:
    path = Path(path_str)
    if path.is_dir():
        return load_capture_dir(path)
    records, skipped = load_capture_file(path)
    return records, {"files": 1, "skipped_lines": skipped}


def cmd_opencode_inspect(path_str: str, show_content: bool) -> int:
    records, stats = _load_records(path_str)
    print(f"bridge schema: {BRIDGE_SCHEMA_V1}")
    print(
        f"records: {len(records)} "
        f"(files: {stats['files']}, skipped lines: {stats['skipped_lines']})"
    )
    kinds: Counter[str] = Counter()
    sessions: set[str] = set()
    for record in records:
        errors = validate_record(record)
        status = "ok" if not errors else f"INVALID: {errors[0]}"
        kinds[str(record.get("hook_kind", "?"))] += 1
        session = record.get("session_id")
        if isinstance(session, str):
            sessions.add(session)
        payload = record.get("payload", {})
        parts = 0
        if isinstance(payload, dict):
            messages = payload.get("messages")
            if isinstance(messages, list):
                parts = sum(
                    len(m.get("parts", []))
                    for m in messages
                    if isinstance(m, dict) and isinstance(m.get("parts"), list)
                )
            system = payload.get("system")
            if isinstance(system, list):
                parts = len(system)
            admission = payload.get("admission")
            if isinstance(admission, dict):
                apart = admission.get("parts")
                if isinstance(apart, list):
                    parts = len(apart)
        print(
            f"- {record.get('capture_id')} [{record.get('hook_kind')}] "
            f"session={session} parts={parts} {status}"
        )
        if show_content:
            print("  LOCAL-CONTENT-BEGIN")
            print(json.dumps(payload, indent=2, sort_keys=True)[:4000])
            print("  LOCAL-CONTENT-END")
    print(f"hook kinds: {dict(sorted(kinds.items()))}")
    print(f"sessions observed: {len(sessions)}")
    if show_content:
        print("WARNING: raw content printed locally only. Never share this output.")
    return 0


def cmd_opencode_ingest(path_str: str) -> int:
    records, stats = _load_records(path_str)
    tracker = SequenceTracker()
    bundles = []
    invocations = []
    invalid = 0
    for record in records:
        if validate_record(record):
            invalid += 1
            continue
        bundle, invocation = ingest_record(record, tracker)
        bundles.append(bundle)
        invocations.append(invocation)
    print(f"records: {len(records)} invalid: {invalid} skipped_lines: {stats['skipped_lines']}")
    print(f"bundles: {len(bundles)} invocations: {len(invocations)}")
    for bundle in bundles:
        print(
            f"- {bundle.id}: {len(bundle.items)} items, "
            f"{bundle_bytes(bundle)} bytes / {bundle_chars(bundle)} chars, "
            f"session={bundle.provenance.session_ref if bundle.provenance else None}"
        )
    return 0


COMPILER_FIXTURES_ROOT = Path("fixtures") / "compiler-v1"
COMPILER_EXPERIMENT_ROOT = Path("experiments") / "compiler-v1"
COMPILER_STRATEGIES = ("dump", "topk", "weighted", "gated", "staged", "oracle")
COMPILER_BUDGETS = ("tight", "medium", "roomy")


def _compiler_manifest() -> dict[str, Any]:
    return json.loads((COMPILER_FIXTURES_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _compiler_policy(name: str) -> CompilerPolicy:
    path = COMPILER_EXPERIMENT_ROOT / "policies" / f"{name}.json"
    return CompilerPolicy.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _compiler_weights() -> dict[str, float]:
    raw = json.loads((COMPILER_EXPERIMENT_ROOT / "weights.json").read_text(encoding="utf-8"))
    return {
        "relevance": float(raw["relevance"]),
        "priority": float(raw["priority"]),
        "cost": float(raw["cost"]),
    }


def cmd_compiler_fixtures() -> int:
    manifest = _compiler_manifest()
    print(f"fixture set: compiler-v1 v{manifest['fixture_version']} [SYNTHETIC]")
    for name in manifest["fixtures"]:
        budgets = manifest["budgets"][name]
        print(
            f"  {name}: tight={budgets['tight']} "
            f"medium={budgets['medium']} roomy={budgets['roomy']}"
        )
    return 0


def cmd_compiler_inspect(fixture: str, strategy: str, budget: str, output_format: str) -> int:
    from project_context.evaluation.compiler_eval import load_truth_file
    from project_context.evaluation.compiler_runner import build_strategies, run_one

    manifest = _compiler_manifest()
    if fixture not in manifest["fixtures"]:
        print(f"unknown fixture: {fixture}", file=sys.stderr)
        return 2
    fixture_set = load_fixture_set(COMPILER_FIXTURES_ROOT)
    candidates = load_candidate_file(fixture_set[fixture]["candidates"])
    base = load_request_file(fixture_set[fixture]["request"])
    request = type(base)(
        request_id=f"{base.request_id}-{budget}",
        task_id=base.task_id,
        usable_token_budget=manifest["budgets"][fixture][budget],
        created_at=base.created_at,
        active_scope=base.active_scope,
        required_ids=base.required_ids,
        policy_version=base.policy_version,
    )
    policy = _compiler_policy(request.policy_version)
    truth = load_truth_file(COMPILER_FIXTURES_ROOT / f"{fixture}.truth.json")
    available = build_strategies(_compiler_weights())
    bundle, trace, reason = run_one(strategy, available, request, candidates, truth, policy)
    if output_format == "json":
        print(
            json.dumps(
                {
                    "fixture": fixture,
                    "strategy": strategy,
                    "budget": budget,
                    "budget_tokens": request.usable_token_budget,
                    "success": bundle is not None,
                    "reason": reason,
                    "bundle_id": bundle.id if bundle else None,
                    "trace": trace.to_dict(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(f"[SYNTHETIC] {fixture} / {strategy} / {budget} ({request.usable_token_budget}t)")
    if bundle is None:
        print(f"COMPILE FAILURE: {reason}")
    else:
        print(f"bundle {bundle.id}: {len(bundle.items)} items")
    for entry in trace.entries:
        position = "" if entry.position is None else f" pos={entry.position}"
        print(f"  {entry.candidate_id}: {entry.decision.value} ({entry.reason_code}){position}")
    return 0


def cmd_compiler_run(
    experiment: str,
    run_id: str | None,
    runs_dir: str,
    policy_name: str,
    timestamp: str | None,
) -> int:
    from project_context.evaluation.compiler_runner import run_suite

    _ = experiment
    manifest = _compiler_manifest()
    policy = _compiler_policy(policy_name)
    weights = _compiler_weights()
    vcs = vcs_info(Path("."))
    moment = timestamp or _utcnow()
    resolved_run_id = run_id or f"compiler-v1-{moment.replace(':', '').replace('+', '')}"
    run_dir = run_suite(
        fixtures_root=COMPILER_FIXTURES_ROOT,
        strategies=list(COMPILER_STRATEGIES),
        budgets=list(COMPILER_BUDGETS),
        policy=policy,
        weights=weights,
        fixture_budgets=manifest["budgets"],
        expected_by_fixture_budget=manifest["expected"],
        fixture_version=manifest["fixture_version"],
        run_id=resolved_run_id,
        timestamp=moment,
        git_commit=str(vcs.get("commit") or "unknown"),
        vcs_dirty=bool(vcs.get("dirty")),
        out_root=Path(runs_dir),
    )
    print(f"frozen compiler run at {run_dir} [SYNTHETIC — NOT BOOK RESULT]")
    return 0


def cmd_compiler_validate_run(run_dir: str) -> int:
    from project_context.runs.artifacts import validate_artifact

    errors = validate_artifact(Path(run_dir))
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 3
    print(f"run valid: {run_dir}")
    return 0


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_campaign_or_fail(campaign_id: str) -> tuple[CampaignManifest, Path] | int:
    path = Path("corpus") / "campaigns" / f"{campaign_id}.json"
    if not path.is_file():
        print(f"unknown campaign: {campaign_id}", file=sys.stderr)
        return 2  # type: ignore[return-value]
    return load_campaign(path), path


def cmd_campaign_create(campaign_id: str, target: int, notes: str) -> int:
    manifest = CampaignManifest(
        campaign_id=campaign_id,
        target_sessions=target,
        capture_schema=BRIDGE_SCHEMA_V1,
        capture_stage="opencode.v1.pre_dispatch_partial",
        opencode_version="1.18.27",
        adapter_version="0.1.0",
        started_at=_utcnow(),
        status=STATUS_OPEN,
        sampling_notes=notes,
    )
    path = Path("corpus") / "campaigns" / f"{campaign_id}.json"
    if path.exists():
        print(f"campaign already exists: {campaign_id}", file=sys.stderr)
        return 2
    save_campaign(path, manifest)
    print(f"created campaign {campaign_id} (target {target} sessions) at {path}")
    return 0


def cmd_campaign_status(campaign_id: str) -> int:
    loaded = _load_campaign_or_fail(campaign_id)
    if isinstance(loaded, int):
        return loaded
    manifest, _path = loaded
    complete = sum(1 for s in manifest.sessions if s.complete_capture)
    print(f"campaign: {manifest.campaign_id} [{manifest.status}]")
    print(f"target sessions: {manifest.target_sessions}")
    print(f"genuine sessions: {manifest.genuine_session_count()}")
    print(f"observer-complete sessions: {complete}")
    print(f"exclusions: {len(manifest.exclusions)}")
    for exclusion in manifest.exclusions:
        print(f"  - {exclusion.scope}: {exclusion.reason} ({exclusion.detail})")
    print(f"schema: {manifest.capture_schema} / {manifest.capture_stage}")
    print(f"adapter: {manifest.adapter_version} / opencode: {manifest.opencode_version}")
    gap = manifest.target_sessions - manifest.genuine_session_count()
    if gap > 0:
        print(f"readiness: UNDER TARGET by {gap} session(s); campaign tooling ready")
    else:
        print("readiness: target met; eligible for first ecological baseline")
    return 0


def cmd_campaign_add(path_str: str, campaign_id: str, source_label: str) -> int:
    loaded = _load_campaign_or_fail(campaign_id)
    if isinstance(loaded, int):
        return loaded
    manifest, path = loaded
    updated, result, index = add_spool(manifest, Path(path_str), source_label, Path("."))
    save_campaign(path, updated)
    save_local_index(Path("."), index)
    print(f"sessions seen: {result.sessions_seen} added: {result.sessions_added}")
    print(f"skipped lines: {result.skipped_lines} invalid records: {result.invalid_records}")
    print(f"campaign now holds {updated.genuine_session_count()} genuine session(s)")
    return 0


def cmd_corpus_quality(campaign_id: str) -> int:
    loaded = _load_campaign_or_fail(campaign_id)
    if isinstance(loaded, int):
        return loaded
    manifest, _path = loaded
    print(f"campaign: {manifest.campaign_id} [{manifest.status}]")
    print(f"sessions: {manifest.genuine_session_count()}")
    print(f"complete: {sum(1 for s in manifest.sessions if s.complete_capture)}")
    versions = sorted(
        {(s.opencode_version or "?", s.adapter_version or "?") for s in manifest.sessions}
    )
    print(f"version pairs: {versions}")
    hook_union: set[str] = set()
    for session in manifest.sessions:
        hook_union.update(session.hook_kinds)
    print(f"hook families observed: {sorted(hook_union) or 'none yet'}")
    print(f"compaction observed anywhere: {any(s.compaction_observed for s in manifest.sessions)}")
    print(f"parse warnings total: {sum(s.parse_warnings for s in manifest.sessions)}")
    print(f"exclusions: {len(manifest.exclusions)}")
    for exclusion in manifest.exclusions:
        print(f"  - {exclusion.scope}: {exclusion.reason}")
    print("privacy: raw-local only; publication: not-approved (all sessions)")
    return 0


def cmd_corpus_prevalence_full(
    path_str: str,
    export: str | None,
    campaign_id: str | None,
    run_id: str | None,
    runs_dir: str,
) -> int:
    records, stats = _load_records(path_str)
    tracker = SequenceTracker()
    bundles = []
    for record in records:
        if validate_record(record):
            continue
        bundle, _invocation = ingest_record(record, tracker)
        bundles.append(bundle)

    target = gap = None
    if campaign_id is not None:
        loaded = _load_campaign_or_fail(campaign_id)
        if isinstance(loaded, int):
            return loaded
        manifest, _path = loaded
        target = manifest.target_sessions
        gap = max(0, target - manifest.genuine_session_count())

    analysis = analyse_bundles(bundles)
    analysis["composition"] = composition_report(bundles)
    analysis["load"] = {
        "records": len(records),
        "skipped_lines": stats["skipped_lines"],
        "evidence_note": "SMOKE/ECOLOGICAL OBSERVATION — NOT BOOK RESULT",
    }
    analysis["repetition"] = repetition_report(bundles)
    sessions = session_bundles(bundles)
    analysis["session_count_scoped"] = len(
        [key for key in sessions if not key.startswith("unlinked:")]
    )
    analysis["unlinked_bundles"] = sum(
        len(ordered) for key, ordered in sessions.items() if key.startswith("unlinked:")
    )

    timelines: dict[str, Any] = {}
    churn: dict[str, Any] = {}
    survival: dict[str, Any] = {}
    durations: dict[str, Any] = {}
    for key, ordered in sorted(sessions.items()):
        if key.startswith("unlinked:"):
            continue
        timelines[key] = session_timeline(key, ordered)
        churn[key] = churn_positions(ordered)
        survival[key] = {
            "horizon_2": prefix_survival(ordered, 2),
            "horizon_5": prefix_survival(ordered, 5),
        }
        durations[key] = duration_minutes(
            [{"captured_at": bundle.created_at} for bundle in ordered if bundle.created_at]
        )
    analysis["timelines"] = timelines
    analysis["churn_positions"] = churn
    analysis["prefix_survival"] = survival
    analysis["durations_minutes"] = durations
    analysis["tool_results"] = tool_result_stats(bundles)
    analysis["tool_share_weighting"] = session_weighted_tool_share(sessions)

    sizes = [bundle_bytes(bundle) for bundle in bundles]
    analysis["size_dist"] = dist([float(v) for v in sizes])
    inv_counts = [len(ordered) for ordered in sessions.values()]
    analysis["invocations_per_session_dist"] = dist([float(v) for v in inv_counts])

    analysis["evidence"] = {
        "evidence_kind": "ecological_observation",
        "capture_boundary": "opencode.v1.pre_dispatch_partial",
        "book_result": False,
        "analysis_version": "0.1.0",
        "vcs": vcs_info(Path(".")),
        "campaign_id": campaign_id,
        "target_sessions": target,
        "session_gap": gap,
        "under_target": bool(gap) if gap is not None else None,
    }
    print(json.dumps(analysis, indent=2, sort_keys=True))

    if export is not None:
        exported = export_report(analysis)
        problems = assert_exportable(exported)
        if problems:
            print(f"export refused: {problems}", file=sys.stderr)
            return 3
        Path(export).write_text(
            json.dumps(exported, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"exported gated aggregate to {export}")

    if run_id is not None:
        vcs = vcs_info(Path("."))
        manifest = RunManifest(
            run_id=run_id,
            experiment_id="ecological-prevalence-v1",
            experiment_version="1",
            git_commit=str(vcs.get("commit") or "unknown"),
            timestamp=_utcnow(),
            provider="opencode-capture",
            model="n/a",
            evidence_class="ecological-observation",
            policy_version=None,
            environment=tuple((k, str(v)) for k, v in {"vcs_dirty": vcs.get("dirty")}.items()),
        )
        readme = (
            f"# Ecological prevalence run {run_id}\n\n"
            "Evidence class: ecological-observation (NOT a book result).\n\n"
            f"Campaign: {campaign_id}; sessions in run: {len(sessions)}.\n"
        )
        run_dir = write_artifact(
            Path(runs_dir),
            manifest,
            EvaluationLog(),
            {"analysis": export_report(analysis)},
            readme_text=readme,
        )
        problems = assert_exportable(
            json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        )
        if problems:
            print(f"run artifact failed export gate: {problems}", file=sys.stderr)
            return 3
        print(f"frozen local run at {run_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fixture" and args.fixture_command == "list":
        return cmd_fixture_list()
    if args.command == "fixture" and args.fixture_command == "inspect":
        return cmd_fixture_inspect(args.fixture_id, args.format)
    if args.command == "opencode" and args.opencode_command == "inspect":
        return cmd_opencode_inspect(args.path, args.show_content)
    if args.command == "opencode" and args.opencode_command == "ingest":
        return cmd_opencode_ingest(args.path)
    if args.command == "corpus" and args.corpus_command == "prevalence":
        return cmd_corpus_prevalence_full(
            args.path,
            args.export,
            campaign_id=args.campaign,
            run_id=args.run_id,
            runs_dir=args.runs_dir,
        )
    if args.command == "corpus" and args.corpus_command == "campaign":
        if args.campaign_command == "create":
            return cmd_campaign_create(args.id, args.target, args.sampling_notes)
        if args.campaign_command == "status":
            return cmd_campaign_status(args.id)
        if args.campaign_command == "add":
            return cmd_campaign_add(args.path, args.id, args.source_label)
    if args.command == "corpus" and args.corpus_command == "quality":
        return cmd_corpus_quality(args.id)
    if args.command == "compiler" and args.compiler_command == "fixtures":
        return cmd_compiler_fixtures()
    if args.command == "compiler" and args.compiler_command == "inspect":
        return cmd_compiler_inspect(args.fixture, args.strategy, args.budget, args.format)
    if args.command == "compiler" and args.compiler_command == "run":
        return cmd_compiler_run(
            args.experiment, args.run_id, args.runs_dir, args.policy, args.timestamp
        )
    if args.command == "compiler" and args.compiler_command == "validate-run":
        return cmd_compiler_validate_run(args.run_dir)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
