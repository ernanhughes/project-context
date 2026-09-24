"""Live-wave orchestration for oracle-leverage-v1 (pre-run frozen harness).

Consumes the frozen schedule.json in order. The single inference
boundary is `run_inference`: everything up to it runs in preflight
mode with zero model calls. Production execution shells out to a
fresh `opencode run` per slot; tests inject a fake executor through
the same boundary, clearly labelled TEST-ONLY.

N-condition semantics (frozen-spec compliant): the runtime pair is
deployed and the observer captures in every condition, but the
intervention opt-in is disengaged for N because the frozen runtime
has no empty-selection path (its block loader refuses unmarked
content, and any marked content would violate observer-verified
absence). Absence is proven by the observer, not assumed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from project_context.domain.bundles import ContextBundle
from project_context.domain.items import ContextItem
from project_context.leverage.grade import grade_fixture, grade_utilisation
from project_context.leverage.model import GRADER_VERSION, RESULT_SCHEMA, RUNNER_VERSION
from project_context.opencode.bridge import integrity_of, validate_record
from project_context.runtime.model import BLOCK_OPEN, RenderPolicy
from project_context.runtime.render import render_bundle

REPO = Path(__file__).resolve().parents[3]
FIXTURES_ROOT = REPO / "fixtures" / "oracle-leverage-v1"
SCHEDULE_PATH = REPO / "experiments" / "oracle-leverage-v1" / "schedule.json"

EMPTY_PAYLOAD_DIGEST = hashlib.sha256(b"").hexdigest()

# Model-visible workspace may contain only these fixture inputs.
ALLOWED_WORKSPACE_NAMES = {"repo"}
FORBIDDEN_WORKSPACE_TOKENS = ("truth.json", "fixture.json", "schedule.json", "counterfactual")


class WaveStop(Exception):
    """Frozen validity condition requiring the whole wave to stop."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class ExecutorResult:
    """Outcome of one inference-boundary crossing. Production fills this
    from the opencode subprocess; tests use a fake."""

    returncode: int
    stdout: str
    stderr: str
    session_id: str | None = None
    status: str = "ok"  # ok | provider_failure_before_response


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_schedule(path: Path = SCHEDULE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_freeze(schedule: dict, fixtures_root: Path = FIXTURES_ROOT) -> list[str]:
    """Recompute every frozen identity. Returns error strings (empty = PASS)."""
    errors: list[str] = []
    man = json.loads((fixtures_root / "manifest.json").read_text(encoding="utf-8"))
    if man.get("freeze_status") != "PRE-RUN FROZEN":
        errors.append("manifest not PRE-RUN FROZEN")
    corpus = hashlib.sha256()
    for entry in man.get("fixtures", []):
        task_dir = fixtures_root / entry["fixture_id"]
        digest = _fixture_input_digest(task_dir)
        if digest != entry.get("input_digest"):
            errors.append(f"fixture digest mismatch: {entry['fixture_id']}")
        corpus.update(digest.encode())
    if corpus.hexdigest() != man.get("corpus_digest"):
        errors.append("fixture corpus digest mismatch")
    core = {
        k: schedule[k]
        for k in sorted(schedule)
        if k not in ("schedule_digest", "model_config_digest")
    }
    if _sha(json.dumps(core, sort_keys=True).encode()) != schedule.get("schedule_digest"):
        errors.append("schedule digest mismatch")
    model_config = schedule.get("subject_model", {})
    if _sha(json.dumps(model_config, sort_keys=True).encode()) != schedule.get(
        "model_config_digest"
    ):
        errors.append("model config digest mismatch")
    runs = schedule.get("runs", [])
    if len(runs) != 24:
        errors.append(f"expected 24 slots, found {len(runs)}")
    conditions = [r["condition"] for r in runs]
    if not (conditions.count("N") == conditions.count("D") == conditions.count("O") == 8):
        counts = (conditions.count("N"), conditions.count("D"), conditions.count("O"))
        errors.append(f"condition imbalance: {counts[0]}/{counts[1]}/{counts[2]}")
    if len({r["run_id"] for r in runs}) != len(runs):
        errors.append("duplicate run IDs")
    for slot in runs:
        task_dir = fixtures_root / slot["fixture_id"]
        fix = json.loads((task_dir / "fixture.json").read_text(encoding="utf-8"))
        if slot["condition"] == "N":
            expected = EMPTY_PAYLOAD_DIGEST
        elif slot["condition"] == "D":
            expected = _sha(fix["distractor_context"]["content"].encode())
        else:
            expected = _sha(fix["oracle_context"]["content"].encode())
        if expected != slot["payload_digest"]:
            errors.append(f"payload digest mismatch: {slot['run_id']}")
    return errors


def _fixture_input_digest(task_dir: Path) -> str:
    fix = json.loads((task_dir / "fixture.json").read_text(encoding="utf-8"))
    truth = json.loads((task_dir / "truth.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    for key in (
        "fixture_id",
        "title",
        "task",
        "visible_default",
        "latent_state",
        "oracle_context",
        "distractor_context",
        "expected_counterfactual",
        "deterministic_observable",
    ):
        digest.update(json.dumps(fix[key], sort_keys=True).encode())
    digest.update(json.dumps(truth, sort_keys=True).encode())
    for path in sorted((task_dir / "repo").iterdir()):
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def check_model_digest(
    expected: str, model: str = "mistral-small:latest", timeout: int = 20
) -> tuple[bool, str | None]:
    """Metadata-only model identity check. No inference call is made."""
    try:
        request = urllib.request.Request(
            "http://localhost:11434/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False, None
    for entry in payload.get("models", []):
        if entry.get("name") == model:
            actual = str(entry.get("digest", ""))
            return actual == expected, actual or None
    return False, None


def seed_workspace(fixture_id: str, fixtures_root: Path, workdir: Path) -> str:
    """Copy ONLY repo/ into the model-visible workspace and verify the
    repo digest. Truth, fixture metadata, and schedule must never enter.
    Returns the verified repo digest; raises WaveStop on any violation."""
    task_dir = fixtures_root / fixture_id
    repo_src = task_dir / "repo"
    if workdir.exists():
        raise WaveStop(f"workspace not fresh: {workdir}")
    workdir.mkdir(parents=True)
    digest = hashlib.sha256()
    for path in sorted(repo_src.iterdir()):
        if not path.is_file():
            continue
        shutil.copy2(path, workdir / path.name)
        digest.update((workdir / path.name).read_bytes())
    blob = "\n".join(p.name for p in workdir.iterdir())
    lowered = (blob + "\n" + str(workdir)).lower()
    for token in FORBIDDEN_WORKSPACE_TOKENS:
        if token in lowered:
            raise WaveStop(f"hidden-truth token in model workspace: {token}")
    for name in ("truth.json", "fixture.json", "manifest.json", "schedule.json"):
        if (workdir / name).exists():
            raise WaveStop(f"evaluation file leaked into workspace: {name}")
    return digest.hexdigest()


def render_condition_payload(
    slot: dict, fixtures_root: Path, block_path: Path
) -> tuple[str | None, str]:
    """Render the slot payload through the frozen Stage 6D renderer.
    Returns (rendered text or None for N, rendered digest or empty digest).
    Fails closed on payload mismatch. Never paraphrases."""
    task_dir = fixtures_root / slot["fixture_id"]
    fix = json.loads((task_dir / "fixture.json").read_text(encoding="utf-8"))
    condition = slot["condition"]
    if condition == "N":
        return None, EMPTY_PAYLOAD_DIGEST
    content = (
        fix["distractor_context"]["content"]
        if condition == "D"
        else fix["oracle_context"]["content"]
    )
    if _sha(content.encode()) != slot["payload_digest"]:
        raise WaveStop(f"payload digest mismatch at render: {slot['run_id']}")
    item = ContextItem(
        id=f"{slot['fixture_id']}-r1",
        source="ledger",
        kind="test_constraint",
        content=content,
        token_provenance="approximation",
    )
    bundle = ContextBundle(
        id=f"{slot['fixture_id']}-bundle",
        items=(item,),
        created_at="2026-09-24T12:00:00Z",
        layout_trace=(item.id,),
        evidence_class="synthetic",
    )
    rendered = render_bundle(bundle, RenderPolicy())
    block_path.write_bytes(rendered.text.encode("utf-8"))
    return rendered.text, rendered.digest


def production_executor(
    slot: dict, schedule: dict, workspace: Path, run_dir: Path, env: dict[str, str]
) -> ExecutorResult:
    """THE inference boundary for real execution. Never called in preflight,
    tests, or this freeze stage. One fresh opencode session per invocation.
    session_id stays None: opencode run output does not reliably report it;
    observer records carry their own session identity."""
    task_dir = FIXTURES_ROOT / slot["fixture_id"]
    fix = json.loads((task_dir / "fixture.json").read_text(encoding="utf-8"))
    model = str(schedule["subject_model"]["model"])
    cmd = [
        "opencode",
        "run",
        "--standalone",
        "--auto",
        "--model",
        model,
        fix["task"]["description"],
    ]
    proc = subprocess.run(cmd, env=env, cwd=workspace, capture_output=True, text=True, timeout=3600)
    return ExecutorResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def build_run_env(run_dir: Path, slot: dict) -> dict[str, str]:
    """Child-only probe environment. N disengages the intervention
    opt-in (the frozen runtime has no empty path); the observer stays
    active and proves absence. Never mutates the parent environment."""
    import os

    env = dict(os.environ)
    spool_dir = run_dir / "spool"
    spool_dir.mkdir(parents=True, exist_ok=True)
    env["PROJECT_CONTEXT_CAPTURE"] = "1"
    env["PROJECT_CONTEXT_SPOOL_DIR"] = str(spool_dir)
    trace_dir = run_dir / "trace"
    trace_dir.mkdir(parents=True, exist_ok=True)
    env["PROJECT_CONTEXT_RUNTIME_TRACE_DIR"] = str(trace_dir)
    if slot["condition"] == "N":
        env.pop("PROJECT_CONTEXT_RUNTIME", None)
        env.pop("PROJECT_CONTEXT_RUNTIME_BLOCK", None)
    else:
        env["PROJECT_CONTEXT_RUNTIME"] = "inject"
        env["PROJECT_CONTEXT_RUNTIME_BLOCK"] = str(run_dir / "runtime-block.txt")
    return env


def execute_slot(
    slot: dict,
    schedule: dict,
    fixtures_root: Path,
    wave_dir: Path,
    executor: object,
) -> dict:
    """Execute one schedule slot with append-only attempt records. The
    executor crosses the inference boundary exactly once per attempt;
    a second attempt happens only on pre-response provider failure."""

    run_id = slot["run_id"]
    run_dir = wave_dir / run_id
    if run_dir.exists():
        raise WaveStop(f"run directory not fresh: {run_id}")
    run_dir.mkdir(parents=True)
    workspace = run_dir / "workspace"
    starting_digest = seed_workspace(slot["fixture_id"], fixtures_root, workspace)
    if starting_digest != slot["repo_digest"]:
        raise WaveStop(f"wrong starting repo state: {run_id}")
    task_dir = fixtures_root / slot["fixture_id"]
    fix = json.loads((task_dir / "fixture.json").read_text(encoding="utf-8"))
    task_digest = _sha(fix["task"]["description"].encode())
    if task_digest != slot["task_digest"]:
        raise WaveStop(f"task digest mismatch: {run_id}")
    block_path = run_dir / "runtime-block.txt"
    rendered_text, rendered_digest = render_condition_payload(slot, fixtures_root, block_path)
    _ = rendered_text
    env = build_run_env(run_dir, slot)
    spool_dir = run_dir / "spool"
    attempts: list[dict] = []
    attempt_no = 0
    started_wall = time.monotonic()
    while True:
        attempt_no += 1
        if attempt_no > 2:
            raise WaveStop(f"attempt overflow: {run_id}")
        started = _utcnow()
        snapshot_spool(spool_dir, run_dir)
        result = executor(slot, schedule, workspace, run_dir, env)  # type: ignore[operator]
        assert isinstance(result, ExecutorResult), "executor must return ExecutorResult"
        ended = _utcnow()
        (run_dir / f"attempt_{attempt_no}.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "attempt": attempt_no,
                    "session_id": result.session_id,
                    "started_at": started,
                    "ended_at": ended,
                    "returncode": result.returncode,
                    "stdout_tail_digest": _sha(result.stdout[-2000:].encode()),
                    "stderr_tail_digest": _sha(result.stderr[-2000:].encode()),
                    "infra_status": result.status
                    if result.status == "provider_failure_before_response"
                    else "ok",
                }
            ),
            encoding="utf-8",
        )
        if result.status == "provider_failure_before_response" and attempt_no == 1:
            attempts.append(
                {
                    "attempt": attempt_no,
                    "infra_status": "provider_failure_before_response",
                    "started_at": started,
                    "ended_at": ended,
                }
            )
            continue
        if result.status == "provider_failure_before_response":
            attempts.append(
                {
                    "attempt": attempt_no,
                    "infra_status": "provider_failure_before_response",
                    "started_at": started,
                    "ended_at": ended,
                }
            )
            break
        attempts.append({"attempt": attempt_no, "infra_status": "ok"})
        break
    new_records = _new_spool_records(spool_dir, run_dir)
    latency_s = round(time.monotonic() - started_wall, 3)
    transport = _reconcile_run(slot, rendered_digest, new_records)
    truth = json.loads((task_dir / "truth.json").read_text(encoding="utf-8"))
    parse, behaviour, required_holds, adherence = grade_fixture(
        slot["fixture_id"], workspace, truth
    )
    admitted = bool(transport.get("decisive_admitted", False))
    utilisation = grade_utilisation(admitted, required_holds)
    valid, exclusion = _apply_exclusions(slot, transport)
    economics = {
        "latency_s": latency_s,
        "call_count": transport.get("records"),
        "input_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
        "cached_tokens": None,
        "reported_cost": None,
    }
    graded = {
        "run_id": run_id,
        "fixture_id": slot["fixture_id"],
        "grader_version": GRADER_VERSION,
        "parse": parse.to_dict(),
        "behaviour": behaviour.to_dict(),
        "adherence": [adherence.to_dict()],
        "utilisation": utilisation.to_dict(),
        "economics": economics,
        "valid": valid,
        "exclusion_reason": exclusion,
    }
    (run_dir / "graded_run.json").write_text(json.dumps(graded, indent=2), encoding="utf-8")
    return {
        "run_id": run_id,
        "attempts": attempts,
        "transport": transport,
        "graded": graded,
        "economics": economics,
    }


def _new_spool_records(spool_dir: Path, run_dir: Path) -> list[dict]:
    """Records appended to the wave spool since the slot started. The
    runner snapshots byte offsets before inference; only new bytes
    belong to the run (sequential isolated execution)."""
    marker = run_dir / "spool_offsets.json"
    offsets: dict[str, int] = {}
    if marker.exists():
        offsets = json.loads(marker.read_text(encoding="utf-8"))
    records: list[dict] = []
    current: dict[str, int] = {}
    if spool_dir.exists():
        for path in sorted(spool_dir.rglob("*.jsonl")):
            rel = str(path.relative_to(spool_dir))
            start = int(offsets.get(rel, 0))
            raw = path.read_bytes()[start:]
            current[rel] = start + len(raw)
            for line in raw.decode("utf-8").splitlines():
                if line.strip():
                    records.append(json.loads(line))
    marker.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return records


def snapshot_spool(spool_dir: Path, run_dir: Path) -> None:
    """Record pre-inference spool offsets so later bytes attribute cleanly."""
    offsets: dict[str, int] = {}
    if spool_dir.exists():
        for path in sorted(spool_dir.rglob("*.jsonl")):
            offsets[str(path.relative_to(spool_dir))] = path.stat().st_size
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spool_offsets.json").write_text(json.dumps(offsets, indent=2), encoding="utf-8")


def _system_texts(record: dict) -> list[str]:
    system = record.get("system")
    if not isinstance(system, list):
        return []
    return [b["text"] for b in system if isinstance(b, dict) and isinstance(b.get("text"), str)]


def _reconcile_run(slot: dict, rendered_digest: str, records: list[dict]) -> dict:
    """6D-R1-style transport check per run. Context-kind records only.
    N verifies absence of experiment-supplied runtime content."""
    context_records = [r for r in records if r.get("request_kind") == "context"]
    if not context_records:
        return {"status": "FAIL", "reason": "no observed context records", "records": 0}
    per_record = []
    for record in context_records:
        texts = _system_texts(record)
        marked = [t for t in texts if BLOCK_OPEN in t]
        if slot["condition"] == "N":
            passed = not validate_record(record) and not marked
            per_record.append(
                {
                    "valid": not validate_record(record),
                    "markers_absent": not marked,
                    "passed": passed,
                }
            )
            continue
        expected = _expected_block_text(slot)
        occurrences = sum(1 for t in texts if t == expected)
        checks = {
            "record_valid": not validate_record(record),
            "markers_present": len(marked) >= 1,
            "block_exact": occurrences >= 1,
            "block_once": occurrences == 1,
            "order_preserved": bool(texts) and texts[-1] == expected,
            "integrity_match": integrity_of(record) == record.get("integrity", {}).get("sha256"),
        }
        per_record.append({**checks, "passed": all(checks.values())})
    all_pass = all(r["passed"] for r in per_record)
    decisive_admitted = all_pass and slot["condition"] in ("D", "O")
    return {
        "status": "PASS" if all_pass else "FAIL",
        "records": len(context_records),
        "per_record": per_record,
        "decisive_admitted": decisive_admitted,
        "rendered_digest": rendered_digest,
    }


def _expected_block_text(slot: dict, fixtures_root: Path = FIXTURES_ROOT) -> str:
    """Exact expected block bytes for D/O, produced by the frozen
    renderer over the frozen payload (same code path as injection, so
    no manual reconstruction can drift)."""
    task_dir = fixtures_root / slot["fixture_id"]
    fix = json.loads((task_dir / "fixture.json").read_text(encoding="utf-8"))
    content = (
        fix["distractor_context"]["content"]
        if slot["condition"] == "D"
        else fix["oracle_context"]["content"]
    )
    item = ContextItem(
        id=f"{slot['fixture_id']}-r1",
        source="ledger",
        kind="test_constraint",
        content=content,
        token_provenance="approximation",
    )
    bundle = ContextBundle(
        id=f"{slot['fixture_id']}-bundle",
        items=(item,),
        created_at="2026-09-24T12:00:00Z",
        layout_trace=(item.id,),
        evidence_class="synthetic",
    )
    return render_bundle(bundle, RenderPolicy()).text


def _apply_exclusions(slot: dict, transport: dict) -> tuple[bool, str | None]:
    if transport.get("status") != "PASS":
        return False, "observer reconciliation failure"
    return True, None


def grade_workspace(fixture_id: str, workspace: Path) -> dict:
    """Condition-blind grading entry point used by tests and the runner."""

    task_dir = FIXTURES_ROOT / fixture_id
    truth = json.loads((task_dir / "truth.json").read_text(encoding="utf-8"))
    parse, behaviour, required_holds, adherence = grade_fixture(fixture_id, workspace, truth)
    return {
        "parse": parse.to_dict(),
        "behaviour": behaviour.to_dict(),
        "adherence": [adherence.to_dict()],
        "required_holds": required_holds,
        "utilisation_ungraded": grade_utilisation(False, required_holds).to_dict(),
    }


def build_result_artifact(
    schedule: dict,
    run_results: list[dict],
    actual_model_digest: str | None,
    grader_digest: str,
    runner_digest: str,
) -> dict:
    """Assemble the frozen result artifact. No model calls; pure construction."""
    artifact = {
        "schema_version": RESULT_SCHEMA,
        "experiment_id": "oracle-leverage-v1",
        "spec": "experiments/oracle-leverage-v1/spec.md",
        "fixture_freeze_commit": schedule.get("fixture_freeze_commit"),
        "fixture_corpus_digest": schedule.get("fixture_corpus_digest"),
        "schedule_digest": schedule.get("schedule_digest"),
        "model_config_digest": schedule.get("model_config_digest"),
        "actual_model_digest": actual_model_digest,
        "grader_version": GRADER_VERSION,
        "grader_digest": grader_digest,
        "runner_version": RUNNER_VERSION,
        "runner_digest": runner_digest,
        "runs": run_results,
        "run_count": len(run_results),
    }
    blob = json.dumps(artifact, sort_keys=True).encode()
    artifact["result_digest"] = _sha(blob)
    return artifact


def preflight(
    schedule_path: Path = SCHEDULE_PATH,
    fixtures_root: Path = FIXTURES_ROOT,
    expected_model: str = "mistral-small:latest",
    model_check: object = None,
) -> dict:
    """Static preflight: every frozen identity, no inference calls."""
    schedule = load_schedule(schedule_path)
    report: dict[str, object] = {"checks": {}, "subject_model_calls": 0, "fixture_probing_calls": 0}
    checks = report["checks"]
    assert isinstance(checks, dict)
    errors = verify_freeze(schedule, fixtures_root)
    checks["freeze_identities"] = "PASS" if not errors else f"FAIL: {errors}"
    expected_digest = str(schedule["subject_model"].get("expected_digest", ""))
    check = model_check if model_check is not None else check_model_digest
    ok, actual = check(expected_digest, expected_model)  # type: ignore[operator]
    checks["model_metadata_identity"] = (
        "PASS" if ok else f"FAIL: expected {expected_digest[:12]} got {(actual or 'none')[:12]}"
    )
    checks["schedule_slots"] = "PASS" if len(schedule.get("runs", [])) == 24 else "FAIL"
    try:
        from project_context.leverage.grade import _GRADERS

        checks["grader_registry"] = "PASS" if len(_GRADERS) == 8 else "FAIL"
    except Exception as exc:
        checks["grader_registry"] = f"FAIL: {exc}"
    checks["payload_binding"] = _check_payload_binding(schedule, fixtures_root)
    checks["hidden_truth_isolation"] = _check_hidden_truth_isolation(schedule, fixtures_root)
    checks["runtime_wiring"] = _check_runtime_wiring(schedule)
    checks["overall"] = "PASS" if all(str(v) == "PASS" for v in checks.values()) else "FAIL"
    return report


def _check_payload_binding(schedule: dict, fixtures_root: Path) -> str:
    """Every slot payload digest recomputes from frozen fixtures; N is canonical empty."""
    try:
        for slot in schedule.get("runs", []):
            task_dir = fixtures_root / slot["fixture_id"]
            fix = json.loads((task_dir / "fixture.json").read_text(encoding="utf-8"))
            if slot["condition"] == "N":
                expected = EMPTY_PAYLOAD_DIGEST
            elif slot["condition"] == "D":
                expected = _sha(fix["distractor_context"]["content"].encode())
            elif slot["condition"] == "O":
                expected = _sha(fix["oracle_context"]["content"].encode())
            else:
                return f"FAIL: unknown condition {slot['condition']}"
            if expected != slot["payload_digest"]:
                return f"FAIL: {slot['run_id']}"
        return "PASS"
    except Exception as exc:
        return f"FAIL: {exc}"


def _check_hidden_truth_isolation(schedule: dict, fixtures_root: Path) -> str:
    """Seed every fixture to a throwaway dir and prove evaluation files
    and truth tokens cannot enter model-visible state."""
    import tempfile

    seen = set()
    try:
        for slot in schedule.get("runs", []):
            seen.add(slot["fixture_id"])
        for fixture_id in sorted(seen):
            with tempfile.TemporaryDirectory() as tmp:
                digest = seed_workspace(fixture_id, fixtures_root, Path(tmp) / "ws")
                slot = next(r for r in schedule["runs"] if r["fixture_id"] == fixture_id)
                if digest != slot["repo_digest"]:
                    return f"FAIL: repo digest {fixture_id}"
                blob = "\n".join(
                    p.name + "\n" + p.read_text(encoding="utf-8", errors="replace")
                    for p in sorted((Path(tmp) / "ws").iterdir())
                    if p.is_file()
                )
                for token in (
                    "correct_action",
                    "counterfactual",
                    "ORACLE",
                    "DISTRACTOR",
                    "truth.json",
                ):
                    if token in blob:
                        return f"FAIL: token {token} in {fixture_id} workspace"
        return "PASS"
    except WaveStop as exc:
        return f"FAIL: {exc.reason}"
    except Exception as exc:
        return f"FAIL: {exc}"


def _check_runtime_wiring(schedule: dict) -> str:
    """Observer/runtime packages present with expected versions; opencode binary on PATH."""
    try:
        import shutil

        integ = REPO / "integrations"
        for package, version in (
            ("opencode", schedule["subject_model"].get("observer_plugin_version", "0.3.0")),
            ("opencode-runtime", schedule["subject_model"].get("runtime_plugin_version", "0.1.0")),
        ):
            manifest = json.loads((integ / package / "package.json").read_text(encoding="utf-8"))
            if manifest.get("version") != version:
                return f"FAIL: {package} version {manifest.get('version')}"
            if not (integ / package / "src" / "index.ts").is_file():
                return f"FAIL: {package} entrypoint missing"
        if shutil.which("opencode") is None:
            return "FAIL: opencode not on PATH"
        return "PASS"
    except Exception as exc:
        return f"FAIL: {exc}"


def run_wave(
    schedule: dict,
    fixtures_root: Path,
    wave_dir: Path,
    executor: object,
    model_digest: str | None,
    model_check: object = None,
) -> dict:
    """Execute schedule slots in recorded order. Hard validity failures
    stop the wave with completed runs preserved; transport failure marks
    one run invalid and the wave continues. No schedule deviation."""
    check = model_check if model_check is not None else check_model_digest
    expected = str(schedule["subject_model"].get("expected_digest", ""))
    model = str(schedule["subject_model"].get("model", "mistral-small:latest"))
    ok, actual = check(expected, model)  # type: ignore[operator]
    if not ok:
        raise WaveStop(
            f"model digest mismatch: expected {expected[:12]} got {(actual or 'none')[:12]}"
        )
    errors = verify_freeze(schedule, fixtures_root)
    if errors:
        raise WaveStop(f"frozen identity failure: {errors}")
    if wave_dir.exists():
        raise WaveStop(f"wave directory not fresh: {wave_dir}")
    wave_dir.mkdir(parents=True)
    results: list[dict] = []
    hard_stop: str | None = None
    for slot in schedule.get("runs", []):
        try:
            results.append(execute_slot(slot, schedule, fixtures_root, wave_dir, executor))
        except WaveStop as exc:
            hard_stop = exc.reason
            break
    grader_digest = _code_digest(REPO / "src" / "project_context" / "leverage" / "grade.py")
    runner_digest = _code_digest(REPO / "src" / "project_context" / "leverage" / "run.py")
    artifact = build_result_artifact(
        schedule, results, model_digest or actual, grader_digest, runner_digest
    )
    artifact["hard_stop"] = hard_stop
    return artifact


def _code_digest(path: Path) -> str:
    return _sha(path.read_bytes())
