"""Matched behavioural runner. Consumes frozen compiler bundles
immutably, invokes one fixed reader per isolated case, parses structured
actions, grades deterministically, and freezes the result. No models in
tests (FakeReader); live runs need explicit --max-calls."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

from project_context.behavior.bundles import (
    derive_bundle,
    digest_text,
    render_from_trace,
    render_visible,
)
from project_context.behavior.domain import BehaviorRecord
from project_context.behavior.fixtures import (
    load_behavior_set,
    load_interventions,
    load_manifest,
    load_task,
    load_truth,
)
from project_context.behavior.parse import PARSER_VERSION, parse_action
from project_context.behavior.prompt import (
    EMPTY_CONTEXT_MARKER,
    PROMPT_VERSION,
    SYSTEM_TEXT,
    action_schema_text,
)
from project_context.behavior.tasks import grade
from project_context.compiler.domain import ContextRequest
from project_context.compiler.fixtures import load_candidate_file, load_request_file
from project_context.domain.bundles import ContextBundle
from project_context.domain.evaluation import EvaluationObservation, Verdict
from project_context.domain.invocations import ModelInvocation
from project_context.domain.runs import RunManifest
from project_context.readers.domain import (
    ReaderAdapter,
    ReaderRequest,
    ReaderResponse,
    ReaderTransportError,
)
from project_context.runs.artifacts import validate_artifact

EXPERIMENT_ID = "compiler-behavior-v1"
EXPERIMENT_VERSION = "1"

CONDITIONS = ("B0", "B1", "B2", "B3", "B4", "B5", "BO", "MA", "MR", "MT", "MW")
STRATEGY_OF = {
    "B1": "dump",
    "B2": "topk",
    "B3": "weighted",
    "B4": "gated",
    "B5": "staged",
    "BO": "oracle",
}

RETRY_BACKOFF_SECONDS = (2.0, 5.0)


def _case_id(fixture: str, budget: str, condition: str, reader: str, repeat: int) -> str:
    return f"{fixture}__{budget}__{condition}__{reader}__r{repeat}"


def build_schedule(manifest: dict, seed: int, reader: str) -> list[dict[str, Any]]:
    """Deterministic case schedule: fixture-major order (interleaved by
    fixture, never batched by condition), seeded condition shuffle within
    each fixture, diagnostic repeats appended."""
    rng = random.Random(seed)
    primary = manifest["primary_budget"]
    cases: list[dict[str, Any]] = []
    for fixture in sorted(manifest["eligible_fixtures"]):
        conditions = ["B0", "B1", "B2", "B3", "B4", "B5", "BO"]
        if fixture == "qualification-trap":
            conditions += ["MA", "MR", "MT", "MW"]
        order = sorted(conditions)
        rng.shuffle(order)
        for condition in order:
            cases.append(
                {
                    "fixture": fixture,
                    "budget": primary,
                    "condition": condition,
                    "reader": reader,
                    "repeat": 0,
                }
            )
    for diagnostic in manifest["repeats"]["diagnostic"]:
        name, _budget, condition, _reader = diagnostic.split("__")
        for repeat in range(1, manifest["repeats"]["diagnostic_extra"] + 1):
            cases.append(
                {
                    "fixture": name,
                    "budget": primary,
                    "condition": condition,
                    "reader": reader,
                    "repeat": repeat,
                }
            )
    for index, case in enumerate(cases):
        case["case_id"] = _case_id(
            case["fixture"],
            case["budget"],
            case["condition"],
            case["reader"],
            case["repeat"],
        )
        case["sequence"] = index
    return cases


def transfer_schedule(manifest: dict, reader: str) -> list[dict[str, Any]]:
    """Small pre-registered transfer wave: heterogeneous-basic at medium
    across the ladder, single observations."""
    cases = []
    for condition in ("B0", "B1", "B2", "B3", "B4", "B5", "BO"):
        cases.append(
            {
                "fixture": "heterogeneous-basic",
                "budget": "medium",
                "condition": condition,
                "reader": reader,
                "repeat": 0,
            }
        )
    for index, case in enumerate(cases):
        case["case_id"] = _case_id(
            case["fixture"],
            case["budget"],
            case["condition"],
            case["reader"],
            case["repeat"],
        )
        case["sequence"] = index
    return cases


class BundleSource:
    """Immutable view over a frozen compiler run plus committed fixtures."""

    def __init__(self, source_run: Path, compiler_fixtures: Path) -> None:
        self.source_run = source_run
        self.compiler_fixtures = compiler_fixtures
        self._compilation = {
            (c["fixture"], c["budget"], c["strategy"]): c
            for c in (
                json.loads(line)
                for line in (source_run / "compilation.jsonl")
                .read_text(encoding="utf-8")
                .strip()
                .split("\n")
            )
        }
        compiler_manifest = json.loads(
            (compiler_fixtures / "manifest.json").read_text(encoding="utf-8")
        )
        self._budgets = compiler_manifest["budgets"]

    def bundle_for(
        self, fixture: str, budget: str, strategy: str
    ) -> tuple[ContextBundle, dict[str, Any]]:
        """Re-render from the frozen trace and digest-verify against the
        frozen record. Raises on any mismatch: a changed bundle stops the
        condition instead of silently substituting."""
        record = self._compilation[(fixture, budget, strategy)]
        if not record["success"]:
            raise ValueError(f"no bundle for failed {fixture}/{budget}/{strategy}")
        candidates = load_candidate_file(self.compiler_fixtures / f"{fixture}.candidates.json")
        base = load_request_file(self.compiler_fixtures / f"{fixture}.request.json")
        request = ContextRequest(
            request_id=base.request_id + f"-{budget}",
            task_id=base.task_id,
            usable_token_budget=self._budgets[fixture][budget],
            created_at=base.created_at,
            active_scope=base.active_scope,
            required_ids=base.required_ids,
            policy_version=base.policy_version,
        )
        admitted = [
            e["candidate_id"] for e in record["trace"]["entries"] if e["decision"] == "ADMITTED"
        ]
        bundle = render_from_trace(admitted, candidates, request)
        if bundle.id != record["bundle_id"]:
            raise ValueError(f"bundle id mismatch for {fixture}/{budget}/{strategy}")
        if bundle.content_hash() != record["bundle_hash"]:
            raise ValueError(
                f"bundle digest mismatch for {fixture}/{budget}/{strategy}: frozen bytes changed"
            )
        return bundle, record


def build_reader_request(
    *,
    case_id: str,
    task: dict,
    context_text: str,
    temperature: float,
    seed: int,
    max_tokens: int,
) -> ReaderRequest:
    return ReaderRequest(
        case_id=case_id,
        system_text=SYSTEM_TEXT,
        task_text=task["prompt"],
        context_text=context_text if context_text else EMPTY_CONTEXT_MARKER,
        schema_text=action_schema_text(task["actions"]),
        temperature=temperature,
        seed=seed,
        max_tokens=max_tokens,
    )


def invoke_with_retry(
    adapter: ReaderAdapter,
    request: ReaderRequest,
    backoff: tuple[float, ...] = RETRY_BACKOFF_SECONDS,
) -> tuple[ReaderResponse, int]:
    """Invoke with transport-error retries only. Returns (response,
    attempts). Valid model behaviour is never retried."""
    attempts = 0
    while True:
        attempts += 1
        try:
            return adapter.invoke(request), attempts
        except ReaderTransportError:
            if attempts > len(backoff):
                raise
            time.sleep(backoff[attempts - 1])


def build_derived(
    *,
    staged_bundle: ContextBundle,
    interventions: dict,
    intervention_id: str,
) -> tuple[ContextBundle, list[str], list[str]]:
    """Bundle surgery for MA/MR/MT/MW. MR (empty diff) rebuilds the parent
    byte-identically; anything else gets a derived identity recording
    parent, intervention, removed and added IDs."""
    spec = next(
        entry
        for entry in interventions["interventions"]
        if entry["intervention_id"] == intervention_id
    )
    derived_id = f"{staged_bundle.id}::{intervention_id}"
    bundle, removed, added = derive_bundle(
        parent=staged_bundle,
        remove_ids=list(spec.get("remove_ids", [])),
        add_records=list(spec.get("add_records", [])),
        bundle_id=derived_id,
    )
    return bundle, removed, added


def run_case(
    *,
    case: dict[str, Any],
    manifest: dict,
    behavior_set: dict[str, dict[str, Path]],
    source: BundleSource,
    adapter: ReaderAdapter,
    temperature: float,
    seed: int,
    max_tokens: int,
    timestamp: str,
) -> tuple[BehaviorRecord, ModelInvocation, list[str], str]:
    """Execute one isolated case. Returns (record, invocation,
    observation lines, raw_text)."""
    fixture = case["fixture"]
    condition = case["condition"]
    task = load_task(behavior_set[fixture]["task"])
    truth = load_truth(behavior_set[fixture]["truth"])
    borrowed = task.get("borrowed_bundles")
    source_fixture = borrowed["fixture"] if borrowed else fixture
    source_budget = borrowed["budget"] if borrowed else case["budget"]

    bundle: ContextBundle | None = None
    parent_bundle_id: str | None = None
    intervention_id: str | None = None
    removed: list[str] = []
    added: list[str] = []
    if condition == "B0":
        context_text = ""
        bundle_id = "empty-context"
        bundle_digest = digest_text("")
    elif condition in STRATEGY_OF:
        bundle, _record = source.bundle_for(source_fixture, source_budget, STRATEGY_OF[condition])
        context_text = render_visible(bundle)
        bundle_id = bundle.id
        bundle_digest = bundle.content_hash()
    else:
        staged, _record = source.bundle_for(source_fixture, source_budget, "staged")
        interventions = load_interventions(behavior_set[fixture]["interventions"])
        bundle, removed, added = build_derived(
            staged_bundle=staged,
            interventions=interventions,
            intervention_id=condition,
        )
        parent_bundle_id = staged.id
        intervention_id = condition
        context_text = render_visible(bundle)
        bundle_id = bundle.id
        bundle_digest = bundle.content_hash()

    reader_request = build_reader_request(
        case_id=case["case_id"],
        task=task,
        context_text=context_text,
        temperature=temperature,
        seed=seed,
        max_tokens=max_tokens,
    )
    response, _attempts = invoke_with_retry(adapter, reader_request)
    action, parse_status = parse_action(response.raw_text, task["actions"])
    if parse_status == "ok":
        score, harmful, dimensions = grade(task["family"], action, truth)
    else:
        score, harmful, dimensions = 0.0, False, {}

    invocation_id = f"{case['case_id']}::inv"
    invocation = ModelInvocation(
        id=invocation_id,
        bundle_id=bundle_id,
        provider=response.provider,
        model=response.model,
        model_version=response.model_version,
        started_at=timestamp,
        completed_at=timestamp,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        reasoning_tokens=response.reasoning_tokens,
        cached_read_tokens=response.cached_read_tokens,
        cached_write_tokens=response.cached_write_tokens,
        latency_ms=response.latency_ms,
        cost_usd=None,
        cost_schedule_id=None,
        observation_only=False,
    )
    record = BehaviorRecord(
        id=f"{case['case_id']}::beh",
        experiment_case_id=case["case_id"],
        fixture_id=fixture,
        condition_id=condition,
        repeat_index=case["repeat"],
        source_bundle_id=bundle_id,
        source_bundle_digest=bundle_digest,
        parent_bundle_id=parent_bundle_id,
        intervention_id=intervention_id,
        removed_ids=tuple(removed),
        added_ids=tuple(added),
        invocation_id=invocation_id,
        parse_status=parse_status,
        parsed_action=action.to_dict() if action else None,
        raw_response_digest=digest_text(response.raw_text),
        prompt_version=PROMPT_VERSION,
        parser_version=PARSER_VERSION,
        grader_version=task["grader_version"],
    )

    obs_lines: list[str] = []
    seq = 0

    def observe(metric: str, value: str, verdict: Verdict, evidence: str) -> None:
        nonlocal seq
        seq += 1
        obs_lines.append(
            json.dumps(
                EvaluationObservation(
                    id=f"{case['case_id']}::obs{seq}",
                    target_type="behavior-case",
                    target_id=case["case_id"],
                    metric=metric,
                    value=value,
                    verdict=verdict,
                    evidence=evidence,
                    evaluator=f"behavior-grader:{task['grader_version']}",
                    created_at=timestamp,
                ).to_dict(),
                sort_keys=True,
            )
        )

    observe(
        f"{task['family']}:task_score",
        str(score),
        Verdict.PASS if score == 1.0 else Verdict.FAIL,
        f"action={action.to_dict() if action else None}; correct={truth['correct_action']}",
    )
    observe(
        f"{task['family']}:parse_success",
        parse_status,
        Verdict.PASS if parse_status == "ok" else Verdict.FAIL,
        f"parse_status={parse_status}",
    )
    observe(
        f"{task['family']}:harmful_action",
        str(harmful),
        Verdict.PASS if not harmful else Verdict.FAIL,
        f"harmful={harmful}",
    )
    for dimension, value in dimensions.items():
        observe(
            f"{task['family']}:{dimension}",
            str(value),
            Verdict.PASS if value == 1.0 else Verdict.FAIL,
            f"{dimension}={value}",
        )
    return record, invocation, obs_lines, response.raw_text


def run_suite(
    *,
    behavior_root: Path,
    source: BundleSource,
    adapter: ReaderAdapter,
    reader_name: str,
    temperature: float,
    seed: int,
    max_tokens: int,
    schedule: list[dict[str, Any]],
    max_calls: int,
    run_id: str,
    timestamp: str,
    git_commit: str,
    vcs_dirty: bool,
    out_root: Path,
    resume: bool = False,
) -> Path:
    """Execute the frozen schedule. Refuses when the call count exceeds
    the explicit guard. Resumes completed cases without rerunning them."""
    manifest = load_manifest(behavior_root / "manifest.json")
    behavior_set = load_behavior_set(behavior_root)
    needed = len(schedule)
    if max_calls < needed:
        raise ValueError(f"spend guard: schedule needs {needed} calls, max {max_calls}")

    run_dir = out_root / EXPERIMENT_ID / run_id
    completed: dict[str, dict[str, Any]] = {}
    if resume:
        schedule_path = run_dir / "case_schedule.json"
        if not schedule_path.is_file():
            raise ValueError(f"nothing to resume at {run_dir}")
        behavior_path = run_dir / "behavior.jsonl"
        if behavior_path.is_file():
            for line in behavior_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = json.loads(line)
                    completed[record["record"]["experiment_case_id"]] = record

    behavior_lines: list[str] = []
    invocations: list[str] = []
    observations: list[str] = []
    for case in schedule:
        case_id = case["case_id"]
        if case_id in completed:
            prior = completed[case_id]
            behavior_lines.append(json.dumps(prior, sort_keys=True))
            inv_path = run_dir / "invocations.jsonl"
            if inv_path.is_file():
                for inv_line in inv_path.read_text(encoding="utf-8").splitlines():
                    if not inv_line.strip():
                        continue
                    if json.loads(inv_line)["id"] == prior["record"]["invocation_id"]:
                        invocations.append(inv_line)
                        break
            obs_path = run_dir / "observations.jsonl"
            if obs_path.is_file():
                prefix = f"{case_id}::obs"
                for obs_line in obs_path.read_text(encoding="utf-8").splitlines():
                    if not obs_line.strip():
                        continue
                    if json.loads(obs_line)["id"].startswith(prefix):
                        observations.append(obs_line)
            continue
        record, invocation, obs_lines, raw_text = run_case(
            case=case,
            manifest=manifest,
            behavior_set=behavior_set,
            source=source,
            adapter=adapter,
            temperature=temperature,
            seed=seed,
            max_tokens=max_tokens,
            timestamp=timestamp,
        )
        behavior_lines.append(
            json.dumps(
                {
                    "record": record.to_dict(),
                    "raw_text": raw_text,
                    "source_bundle_hash": record.source_bundle_digest,
                },
                sort_keys=True,
            )
        )
        invocations.append(json.dumps(invocation.to_dict(), sort_keys=True))
        observations.extend(obs_lines)

    run_manifest = RunManifest(
        run_id=run_id,
        experiment_id=EXPERIMENT_ID,
        experiment_version=EXPERIMENT_VERSION,
        git_commit=git_commit,
        timestamp=timestamp,
        provider="synthetic",
        model="synthetic-deterministic-v1",
        evidence_class="synthetic",
        policy_version="compiler-policy-v1",
        fixture_id="compiler-behavior-v1",
        fixture_version=manifest["behavior_version"],
        environment=(
            ("reader", reader_name),
            ("reader_adapter", str(adapter.describe().get("adapter", "?"))),
            ("reader_model", str(adapter.describe().get("model", "?"))),
            ("temperature", str(temperature)),
            ("decoding_seed", str(seed)),
            ("vcs_dirty", str(vcs_dirty)),
            ("reader_calls", "live-model"),
        ),
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(run_manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "case_schedule.json").write_text(
        json.dumps(schedule, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "behavior.jsonl").write_text(
        "".join(line + "\n" for line in behavior_lines), encoding="utf-8"
    )
    (run_dir / "invocations.jsonl").write_text(
        "".join(line + "\n" for line in invocations), encoding="utf-8"
    )
    (run_dir / "observations.jsonl").write_text(
        "".join(line + "\n" for line in observations), encoding="utf-8"
    )
    results = {
        "experiment": EXPERIMENT_ID,
        "experiment_version": EXPERIMENT_VERSION,
        "reader": reader_name,
        "cases": len(schedule),
        "completed": len(behavior_lines),
    }
    (run_dir / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "README.md").write_text(
        f"# {EXPERIMENT_ID} run {run_id}\n\n"
        "SYNTHETIC FIXTURES + LIVE LOCAL READER. NOT A BOOK RESULT.\n"
        "Real reader behaviour on controlled synthetic tasks: bundle bytes\n"
        "are frozen compiler-v1 outputs; only the reader responses are new.\n",
        encoding="utf-8",
    )
    problems = validate_artifact(run_dir)
    if problems:
        raise ValueError(f"run artifact invalid: {problems}")
    return run_dir
