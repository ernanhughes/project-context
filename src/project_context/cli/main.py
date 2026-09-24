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
    BRIDGE_SCHEMA_V2,
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
    tool_definition_stats,
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

    behavior = sub.add_parser("behavior", help="Matched behavioural evaluation.")
    behavior_sub = behavior.add_subparsers(dest="behavior_command", required=True)
    behavior_sub.add_parser("fixtures", help="List behavior fixtures and budgets.")
    beh_inspect = behavior_sub.add_parser(
        "inspect", help="Show one case setup without calling a model."
    )
    beh_inspect.add_argument("fixture", help="Behavior fixture name.")
    beh_inspect.add_argument(
        "--condition",
        default="B5",
        choices=(
            "B0",
            "B1",
            "B2",
            "B3",
            "B4",
            "B5",
            "BO",
            "MA",
            "MR",
            "MT",
            "MW",
        ),
        help="Condition to inspect.",
    )
    beh_inspect.add_argument(
        "--format", choices=("text", "json"), default="text", help="Report format."
    )
    behavior_sub.add_parser("plan", help="Print the frozen case schedule.")
    beh_dry = behavior_sub.add_parser("dry-run", help="Validate everything without network access.")
    beh_dry.add_argument(
        "--reader",
        default="fake",
        choices=("fake", "primary", "transfer"),
        help="Reader to resolve (no calls are made).",
    )
    beh_run = behavior_sub.add_parser("run", help="Run the behavior suite.")
    beh_run.add_argument("experiment", choices=("compiler-behavior-v1",), help="Experiment to run.")
    beh_run.add_argument(
        "--reader",
        default="fake",
        choices=("fake", "primary", "transfer"),
        help="Reader adapter to use.",
    )
    beh_run.add_argument("--run-id", default=None, help="Run identifier.")
    beh_run.add_argument("--runs-dir", default=".local/runs", help="Local root for frozen runs.")
    beh_run.add_argument("--max-calls", type=int, required=True, help="Hard cap on model calls.")
    beh_run.add_argument(
        "--timestamp", default=None, help="Manifest timestamp (default: now, UTC)."
    )
    beh_run.add_argument("--resume", action="store_true", help="Resume an interrupted run.")
    beh_run.add_argument(
        "--allow-moving-model-alias",
        action="store_true",
        help="Permit a reader model with no tag or ':latest'. The run is recorded as "
        "non-reproducible from the model name.",
    )
    beh_run.add_argument(
        "--transfer",
        action="store_true",
        help="Run the pre-registered transfer wave instead of the primary schedule.",
    )
    beh_validate = behavior_sub.add_parser(
        "validate-run", help="Validate a frozen behavior run directory."
    )
    beh_validate.add_argument("run_dir", help="Run directory to validate.")
    beh_canary = behavior_sub.add_parser(
        "canary", help="Connectivity canary (not experiment data)."
    )
    beh_canary.add_argument(
        "--reader",
        default="primary",
        choices=("primary", "transfer"),
        help="Live reader to probe.",
    )

    debug = sub.add_parser("debug", help="Local read-only OpenCode context observability.")
    debug_sub = debug.add_subparsers(dest="debug_command", required=True)

    def _add_spool(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "spool",
            nargs="?",
            default=None,
            help="Capture .jsonl file or spool directory (default: $PROJECT_CONTEXT_SPOOL_DIR).",
        )
        parser.add_argument(
            "--session",
            default=None,
            help="Session ordinal (1-based). Defaults to the most recent session.",
        )
        parser.add_argument(
            "--format", choices=("text", "json"), default="text", help="Report format."
        )
        parser.add_argument(
            "--include-auxiliary",
            action="store_true",
            help="Include auxiliary requests (compaction/generate) alongside primary ones.",
        )

    latest_parser = debug_sub.add_parser("latest", help="Latest primary invocation report.")
    _add_spool(latest_parser)

    inspect_parser = debug_sub.add_parser("inspect", help="Item inventory for one invocation.")
    _add_spool(inspect_parser)
    inspect_parser.add_argument("invocation", help="Invocation sequence number within the session.")
    inspect_parser.add_argument(
        "--show-content",
        action="store_true",
        help="LOCAL ONLY: also print raw item contents. Never use in shared logs.",
    )

    timeline_parser = debug_sub.add_parser("timeline", help="Structural timeline for a session.")
    _add_spool(timeline_parser)

    compare_parser = debug_sub.add_parser("compare", help="Compare two invocations.")
    _add_spool(compare_parser)
    compare_parser.add_argument("invocation_a", help="First invocation sequence number.")
    compare_parser.add_argument("invocation_b", help="Second invocation sequence number.")

    explain_parser = debug_sub.add_parser("explain", help="Origin and history for one item.")
    _add_spool(explain_parser)
    explain_parser.add_argument("item", help="Item id (use inspect to list item ids).")

    query_parser = debug_sub.add_parser("query", help="Structural query over a session.")
    _add_spool(query_parser)
    query_parser.add_argument("--kind", default=None, help="Filter by ingester kind.")
    query_parser.add_argument(
        "--category",
        default=None,
        choices=(
            "system",
            "user",
            "assistant",
            "tool_definition",
            "tool_call",
            "tool_result",
            "other",
        ),
        help="Filter by debugger category.",
    )
    query_parser.add_argument("--min-bytes", type=int, default=None)
    query_parser.add_argument("--min-tokens", type=int, default=None)
    query_parser.add_argument(
        "--repeated", action="store_true", help="Only byte-identical recurring items."
    )
    query_parser.add_argument("--introduced-after", type=int, default=None)
    query_parser.add_argument("--changed", action="store_true")
    query_parser.add_argument("--contains", default=None, help="LOCAL ONLY substring search.")
    query_parser.add_argument(
        "--allow-content-search",
        action="store_true",
        help="LOCAL ONLY: permit --contains inspection of raw content.",
    )

    doctor_parser = debug_sub.add_parser("doctor", help="Context observations (no fixes).")
    _add_spool(doctor_parser)
    doctor_parser.add_argument(
        "--invocation", default=None, help="Restrict to one invocation sequence number."
    )
    return parser


def _load_records(path_str: str) -> tuple[list[dict], dict[str, int]]:
    path = Path(path_str)
    if path.is_dir():
        return load_capture_dir(path)
    records, skipped = load_capture_file(path)
    return records, {"files": 1, "skipped_lines": skipped}


def cmd_opencode_inspect(path_str: str, show_content: bool) -> int:
    records, stats = _load_records(path_str)
    print(f"bridge schema: {BRIDGE_SCHEMA_V2}")
    print(
        f"records: {len(records)} "
        f"(files: {stats['files']}, skipped lines: {stats['skipped_lines']})"
    )
    kinds: Counter[str] = Counter()
    sessions: set[str] = set()
    for record in records:
        errors = validate_record(record)
        status = "ok" if not errors else f"INVALID: {errors[0]}"
        kinds[str(record.get("request_kind", "?"))] += 1
        session = record.get("session_id")
        if isinstance(session, str):
            sessions.add(session)
        system = record.get("system")
        messages = record.get("messages")
        tools = record.get("tools")
        parts = 0
        if isinstance(system, list):
            parts += len(system)
        if isinstance(messages, list):
            parts += len(messages)
        tool_count = len(tools) if isinstance(tools, dict) else 0
        print(
            f"- {record.get('capture_id')} [{record.get('request_kind')}] "
            f"session={session} seq={record.get('invocation_sequence')} "
            f"blocks={parts} tools={tool_count} {status}"
        )
        if show_content:
            print("  LOCAL-CONTENT-BEGIN")
            print(
                json.dumps(
                    {k: record.get(k) for k in ("system", "messages", "tools", "options")},
                    indent=2,
                    sort_keys=True,
                )[:4000]
            )
            print("  LOCAL-CONTENT-END")
    print(f"request kinds: {dict(sorted(kinds.items()))}")
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


BEHAVIOR_ROOT = Path("fixtures") / "compiler-behavior-v1"
BEHAVIOR_EXPERIMENT_ROOT = Path("experiments") / "compiler-behavior-v1"
BEHAVIOR_CONDITIONS = (
    "B0",
    "B1",
    "B2",
    "B3",
    "B4",
    "B5",
    "BO",
    "MA",
    "MR",
    "MT",
    "MW",
)


def _behavior_manifest() -> dict[str, Any]:
    from project_context.behavior.fixtures import load_manifest

    return load_manifest(BEHAVIOR_ROOT / "manifest.json")


def _resolve_reader(name: str):
    """Resolve a reader adapter by name. Live adapters read endpoint and
    model from environment/spec; values are never printed."""
    import os

    if name == "fake":
        from project_context.readers.fake import FakeReader

        return FakeReader()
    if name in ("primary", "transfer"):
        from project_context.readers.openai_chat import OpenAIChatAdapter, OpenAIChatConfig

        manifest = _behavior_manifest()
        model = manifest["readers"][name]["model"]
        base_url = os.environ.get("CONTEXTLAB_READER_BASE_URL", "http://localhost:11434/v1")
        return OpenAIChatAdapter(
            OpenAIChatConfig(
                base_url=base_url,
                model=model,
                api_key=os.environ.get("CONTEXTLAB_READER_API_KEY"),
            )
        )
    raise ValueError(f"unknown reader: {name}")


def _reader_display(name: str) -> str:
    if name == "fake":
        return "fake (offline scripted reader)"
    manifest = _behavior_manifest()
    return f"{name} model={manifest['readers'][name]['model']} (endpoint hidden)"


def cmd_behavior_fixtures() -> int:
    from project_context.behavior.fixtures import load_behavior_set

    manifest = _behavior_manifest()
    print(f"behavior set: compiler-behavior-v1 v{manifest['behavior_version']} [SYNTHETIC]")
    print(f"primary budget: {manifest['primary_budget']}")
    for name in sorted(load_behavior_set(BEHAVIOR_ROOT)):
        print(f"  {name}")
    return 0


def cmd_behavior_inspect(fixture: str, condition: str, output_format: str) -> int:
    from project_context.behavior.bundles import render_visible
    from project_context.behavior.fixtures import load_behavior_set, load_task

    behavior_set = load_behavior_set(BEHAVIOR_ROOT)
    if fixture not in behavior_set:
        print(f"unknown fixture: {fixture}", file=sys.stderr)
        return 2
    task = load_task(behavior_set[fixture]["task"])
    manifest = _behavior_manifest()
    info = {
        "fixture": fixture,
        "condition": condition,
        "family": task["family"],
        "actions": task["actions"],
        "primary_budget": manifest["primary_budget"],
        "task_prompt_chars": len(task["prompt"]),
    }
    if output_format == "json":
        print(json.dumps(info, indent=2, sort_keys=True))
        return 0
    print(f"[SYNTHETIC] {fixture} / {condition} (family {task['family']})")
    print(f"prompt: {task['prompt']}")
    print(f"actions: {', '.join(task['actions'])}")
    _ = render_visible
    return 0


def cmd_behavior_plan() -> int:
    from project_context.behavior.runner import build_schedule, transfer_schedule

    manifest = _behavior_manifest()
    schedule = build_schedule(manifest, manifest["schedule_seed"], reader="primary")
    transfer = transfer_schedule(manifest, reader="transfer")
    print(f"primary schedule: {len(schedule)} cases (seed {manifest['schedule_seed']})")
    for case in schedule:
        print(f"  {case['sequence']:3d} {case['case_id']}")
    print(f"transfer wave: {len(transfer)} cases")
    for case in transfer:
        print(f"  t{case['sequence']:02d} {case['case_id']}")
    print(f"total live calls planned: {len(schedule) + len(transfer)} + 1 canary")
    return 0


def cmd_behavior_dry_run(reader: str) -> int:
    from project_context.behavior.fixtures import load_behavior_set, load_task
    from project_context.behavior.runner import (
        BundleSource,
        build_derived,
        build_schedule,
        transfer_schedule,
    )
    from project_context.compiler.fixtures import load_candidate_file
    from project_context.evaluation.compiler_runner import load_fixture_file_set

    manifest = _behavior_manifest()
    behavior_set = load_behavior_set(BEHAVIOR_ROOT)
    source = BundleSource(
        Path(".local/runs/compiler-v1/run-001"),
        Path("fixtures/compiler-v1"),
    )
    problems: list[str] = []
    # 1. every primary case resolves a digest-verified bundle (or empty B0).
    schedule = build_schedule(manifest, manifest["schedule_seed"], reader="primary")
    transfer = transfer_schedule(manifest, reader="transfer")
    compiler_set = load_fixture_file_set(Path("fixtures/compiler-v1"))
    for case in schedule + transfer:
        fixture, budget, condition = case["fixture"], case["budget"], case["condition"]
        try:
            task = load_task(behavior_set[fixture]["task"])
            _ = task
            if condition == "B0":
                continue
            if condition in ("B1", "B2", "B3", "B4", "B5", "BO"):
                from project_context.behavior.runner import STRATEGY_OF

                borrowed = load_task(behavior_set[fixture]["task"]).get("borrowed_bundles")
                src_fix = borrowed["fixture"] if borrowed else fixture
                src_bud = borrowed["budget"] if borrowed else budget
                source.bundle_for(src_fix, src_bud, STRATEGY_OF[condition])
            else:
                from project_context.behavior.fixtures import load_interventions

                borrowed = load_task(behavior_set[fixture]["task"]).get("borrowed_bundles")
                src_fix = borrowed["fixture"] if borrowed else fixture
                src_bud = borrowed["budget"] if borrowed else budget
                staged, _ = source.bundle_for(src_fix, src_bud, "staged")
                interventions = load_interventions(behavior_set[fixture]["interventions"])
                build_derived(
                    staged_bundle=staged,
                    interventions=interventions,
                    intervention_id=condition,
                )
        except Exception as exc:  # noqa: BLE001 - dry-run reports, never raises
            problems.append(f"{case['case_id']}: {exc}")
    # 2. compiler fixtures load (strict keys pin truth separation).
    _ = load_candidate_file(compiler_set["qualification-trap"]["candidates"])
    _ = load_fixture_set(Path("fixtures/compiler-v1"))
    calls = len(schedule) + len(transfer)
    print(f"cases: primary={len(schedule)} transfer={len(transfer)} total={calls}")
    print(f"max-calls guard required: >= {calls}")
    if problems:
        for problem in problems:
            print(f"DRY-RUN PROBLEM: {problem}", file=sys.stderr)
        return 3
    print(f"dry run clean [{reader} resolved, no calls made]")
    return 0


def cmd_behavior_run(
    experiment: str,
    reader: str,
    run_id: str | None,
    runs_dir: str,
    max_calls: int,
    timestamp: str | None,
    resume: bool,
    transfer: bool,
    allow_moving_model_alias: bool = False,
) -> int:
    from project_context.behavior.fixtures import load_behavior_set
    from project_context.behavior.runner import (
        BundleSource,
        build_schedule,
        run_suite,
        transfer_schedule,
    )
    from project_context.runs.artifacts import vcs_info

    _ = experiment
    manifest = _behavior_manifest()
    behavior_set = load_behavior_set(BEHAVIOR_ROOT)
    _ = behavior_set
    adapter = _resolve_reader(reader)
    if transfer and reader != "transfer":
        print("--transfer requires --reader transfer", file=sys.stderr)
        return 2
    schedule = (
        transfer_schedule(manifest, reader)
        if transfer
        else build_schedule(manifest, manifest["schedule_seed"], reader=reader)
    )
    moment = timestamp or _utcnow()
    resolved_run_id = run_id or f"behavior-{moment.replace(':', '').replace('+', '')}"
    source = BundleSource(
        Path(".local/runs/compiler-v1/run-001"),
        Path("fixtures/compiler-v1"),
    )
    vcs = vcs_info(Path("."))
    decoding = manifest["decoding"]
    try:
        run_dir = run_suite(
            behavior_root=BEHAVIOR_ROOT,
            source=source,
            adapter=adapter,
            reader_name=reader,
            temperature=float(decoding["temperature"]),
            seed=int(decoding["seed"]),
            max_tokens=int(decoding["max_tokens"]),
            schedule=schedule,
            max_calls=max_calls,
            run_id=resolved_run_id,
            timestamp=moment,
            git_commit=str(vcs.get("commit") or "unknown"),
            vcs_dirty=bool(vcs.get("dirty")),
            out_root=Path(runs_dir),
            resume=resume,
            allow_moving_model_alias=allow_moving_model_alias,
        )
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"frozen behavior run at {run_dir} [SYNTHETIC FIXTURES + LIVE READER]")
    return 0


def cmd_behavior_validate_run(run_dir: str) -> int:
    from project_context.runs.artifacts import validate_artifact

    root = Path(run_dir)
    errors = validate_artifact(root)
    for name in ("behavior.jsonl", "invocations.jsonl"):
        path = root / name
        if not path.is_file():
            errors.append(f"missing required behavior file: {name}")
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{name} unreadable: {exc}")
    schedule_path = root / "case_schedule.json"
    if not schedule_path.is_file():
        errors.append("missing required behavior file: case_schedule.json")
    else:
        try:
            schedule_doc = json.loads(schedule_path.read_text(encoding="utf-8"))
            if not isinstance(schedule_doc, list):
                errors.append("case_schedule.json is not a case list")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"case_schedule.json unreadable: {exc}")
            schedule_doc = []
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 3
    # Cross-check: every scheduled case has behaviour + invocation records.
    schedule = schedule_doc
    behavior_ids = {
        json.loads(line)["record"]["experiment_case_id"]
        for line in (root / "behavior.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    missing = [c["case_id"] for c in schedule if c["case_id"] not in behavior_ids]
    if missing:
        print(f"INVALID: {len(missing)} scheduled cases without records", file=sys.stderr)
        return 3
    print(f"behavior run valid: {run_dir} ({len(schedule)} cases)")
    return 0


def cmd_behavior_canary(reader: str) -> int:
    import datetime

    from project_context.readers.domain import ReaderRequest

    adapter = _resolve_reader(reader)
    request = ReaderRequest(
        case_id="canary-connectivity",
        system_text="Reply with exactly the given JSON and nothing else.",
        task_text='{"ping": true}',
        context_text="",
        schema_text='{"ping": boolean}',
        temperature=0.0,
        seed=1,
        max_tokens=64,
    )
    try:
        response = adapter.invoke(request)
    except Exception as exc:  # noqa: BLE001 - canary reports, never raises
        print(f"canary FAILED: {type(exc).__name__}", file=sys.stderr)
        return 3
    summary = {
        "note": "CONNECTIVITY CANARY — NOT EXPERIMENT DATA",
        "adapter": adapter.describe(),
        "model": response.model,
        "latency_ms": response.latency_ms,
        "input_tokens": response.input_tokens.to_dict(),
        "output_tokens": response.output_tokens.to_dict(),
        "raw_preview": response.raw_text[:120],
    }
    out_dir = Path(".local")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out_dir / f"canary-{reader}-{stamp}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
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
        capture_schema=BRIDGE_SCHEMA_V2,
        capture_stage="opencode.v2.model_context",
        opencode_version="2.0.16",
        adapter_version="0.2.0",
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
    print(f"request kinds observed: {sorted(hook_union) or 'none yet'}")
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
    analysis["tool_definitions"] = tool_definition_stats(bundles)
    analysis["tool_share_weighting"] = session_weighted_tool_share(sessions)

    sizes = [bundle_bytes(bundle) for bundle in bundles]
    analysis["size_dist"] = dist([float(v) for v in sizes])
    inv_counts = [len(ordered) for ordered in sessions.values()]
    analysis["invocations_per_session_dist"] = dist([float(v) for v in inv_counts])

    analysis["evidence"] = {
        "evidence_kind": "ecological_observation",
        "capture_boundary": "opencode.v2.model_context",
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


def _default_spool(explicit: str | None) -> str:
    import os

    if explicit:
        return explicit
    env = os.environ.get("PROJECT_CONTEXT_SPOOL_DIR")
    if env:
        return env
    return str(Path.home() / ".local" / "share" / "project-context" / "captures")


def _resolve_debug_session(store, selector: str | None) -> tuple[str, int, list]:
    if not store.session_order:
        raise ValueError("no sessions in spool")
    if selector is None:
        key = store.session_order[-1]
        return key, len(store.session_order), store.sessions[key]
    try:
        ordinal = int(selector)
    except ValueError:
        if selector in store.sessions:
            key = selector
            return key, store.session_order.index(key) + 1, store.sessions[key]
        raise ValueError(f"unknown session selector: {selector!r}")
    if not 1 <= ordinal <= len(store.session_order):
        raise ValueError(f"session ordinal out of range: {ordinal}")
    key = store.session_order[ordinal - 1]
    return key, ordinal, store.sessions[key]


def _emit(output_format: str, text: str, doc: dict) -> int:
    if output_format == "json":
        print(json.dumps(doc, indent=2, sort_keys=True))
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def cmd_debug_latest(
    spool: str | None, session: str | None, output_format: str, primary_only: bool
) -> int:
    from project_context.debugger.analyse import load_spool
    from project_context.debugger.report import report_latest

    store = load_spool(_default_spool(spool), primary_only=primary_only)
    try:
        key, ordinal, ordered = _resolve_debug_session(store, session)
    except ValueError as exc:
        print(f"debug: {exc}", file=sys.stderr)
        return 2
    text, doc = report_latest(key, ordinal, ordered)
    return _emit(output_format, text, doc)


def cmd_debug_inspect(
    spool: str | None,
    session: str | None,
    output_format: str,
    invocation: str,
    show_content: bool,
    primary_only: bool,
) -> int:
    from project_context.debugger.analyse import load_spool
    from project_context.debugger.report import report_inspect

    store = load_spool(_default_spool(spool), primary_only=primary_only)
    try:
        key, ordinal, ordered = _resolve_debug_session(store, session)
        text, doc = report_inspect(
            key, ordinal, ordered, int(invocation), show_content=show_content
        )
    except ValueError as exc:
        print(f"debug: {exc}", file=sys.stderr)
        return 2
    return _emit(output_format, text, doc)


def cmd_debug_timeline(
    spool: str | None, session: str | None, output_format: str, primary_only: bool
) -> int:
    from project_context.debugger.analyse import load_spool
    from project_context.debugger.report import report_timeline

    store = load_spool(_default_spool(spool), primary_only=primary_only)
    try:
        key, ordinal, ordered = _resolve_debug_session(store, session)
    except ValueError as exc:
        print(f"debug: {exc}", file=sys.stderr)
        return 2
    text, doc = report_timeline(key, ordinal, ordered)
    return _emit(output_format, text, doc)


def cmd_debug_compare(
    spool: str | None,
    session: str | None,
    output_format: str,
    invocation_a: str,
    invocation_b: str,
    primary_only: bool,
) -> int:
    from project_context.debugger.analyse import load_spool
    from project_context.debugger.report import report_compare

    store = load_spool(_default_spool(spool), primary_only=primary_only)
    try:
        _key, ordinal, ordered = _resolve_debug_session(store, session)
        text, doc = report_compare(ordinal, ordered, int(invocation_a), int(invocation_b))
    except ValueError as exc:
        print(f"debug: {exc}", file=sys.stderr)
        return 2
    return _emit(output_format, text, doc)


def cmd_debug_explain(
    spool: str | None, session: str | None, output_format: str, item: str, primary_only: bool
) -> int:
    from project_context.debugger.analyse import load_spool
    from project_context.debugger.report import report_explain

    store = load_spool(_default_spool(spool), primary_only=primary_only)
    try:
        key, ordinal, ordered = _resolve_debug_session(store, session)
        text, doc = report_explain(key, ordinal, ordered, item)
    except ValueError as exc:
        print(f"debug: {exc}", file=sys.stderr)
        return 2
    return _emit(output_format, text, doc)


def cmd_debug_query(args) -> int:
    from project_context.debugger.analyse import load_spool
    from project_context.debugger.query import ContentSearchNotAllowedError, query_items
    from project_context.debugger.report import report_query

    store = load_spool(_default_spool(args.spool), primary_only=not args.include_auxiliary)
    try:
        _key, ordinal, ordered = _resolve_debug_session(store, args.session)
        results = query_items(
            ordered,
            kind=args.kind,
            category=args.category,
            min_bytes=args.min_bytes,
            min_tokens=args.min_tokens,
            repeated=args.repeated,
            introduced_after=args.introduced_after,
            changed=args.changed,
            contains=args.contains,
            allow_content_search=args.allow_content_search,
        )
    except ContentSearchNotAllowedError as exc:
        print(f"debug: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"debug: {exc}", file=sys.stderr)
        return 2
    describe_parts = []
    for flag in ("kind", "category", "min_bytes", "min_tokens", "introduced_after", "contains"):
        value = getattr(args, flag)
        if value is not None:
            describe_parts.append(f"{flag}={value}")
    for flag in ("repeated", "changed"):
        if getattr(args, flag):
            describe_parts.append(flag)
    describe = ", ".join(describe_parts) or "all items"
    text, doc = report_query(ordinal, results, {}, describe)
    return _emit(args.format, text, doc)


def cmd_debug_doctor(
    spool: str | None,
    session: str | None,
    output_format: str,
    invocation: str | None,
    primary_only: bool,
) -> int:
    from project_context.debugger.analyse import load_spool
    from project_context.debugger.report import report_doctor

    store = load_spool(_default_spool(spool), primary_only=primary_only)
    try:
        _key, ordinal, ordered = _resolve_debug_session(store, session)
        sequence = int(invocation) if invocation is not None else None
        text, doc = report_doctor(ordinal, ordered, sequence=sequence)
    except ValueError as exc:
        print(f"debug: {exc}", file=sys.stderr)
        return 2
    return _emit(output_format, text, doc)


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
    if args.command == "behavior" and args.behavior_command == "fixtures":
        return cmd_behavior_fixtures()
    if args.command == "behavior" and args.behavior_command == "inspect":
        return cmd_behavior_inspect(args.fixture, args.condition, args.format)
    if args.command == "behavior" and args.behavior_command == "plan":
        return cmd_behavior_plan()
    if args.command == "behavior" and args.behavior_command == "dry-run":
        return cmd_behavior_dry_run(args.reader)
    if args.command == "behavior" and args.behavior_command == "run":
        return cmd_behavior_run(
            args.experiment,
            args.reader,
            args.run_id,
            args.runs_dir,
            args.max_calls,
            args.timestamp,
            args.resume,
            args.transfer,
            args.allow_moving_model_alias,
        )
    if args.command == "behavior" and args.behavior_command == "validate-run":
        return cmd_behavior_validate_run(args.run_dir)
    if args.command == "behavior" and args.behavior_command == "canary":
        return cmd_behavior_canary(args.reader)
    if args.command == "debug":
        primary_only = not args.include_auxiliary
        if args.debug_command == "latest":
            return cmd_debug_latest(args.spool, args.session, args.format, primary_only)
        if args.debug_command == "inspect":
            return cmd_debug_inspect(
                args.spool,
                args.session,
                args.format,
                args.invocation,
                args.show_content,
                primary_only,
            )
        if args.debug_command == "timeline":
            return cmd_debug_timeline(args.spool, args.session, args.format, primary_only)
        if args.debug_command == "compare":
            return cmd_debug_compare(
                args.spool,
                args.session,
                args.format,
                args.invocation_a,
                args.invocation_b,
                primary_only,
            )
        if args.debug_command == "explain":
            return cmd_debug_explain(args.spool, args.session, args.format, args.item, primary_only)
        if args.debug_command == "query":
            return cmd_debug_query(args)
        if args.debug_command == "doctor":
            return cmd_debug_doctor(
                args.spool, args.session, args.format, args.invocation, primary_only
            )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
