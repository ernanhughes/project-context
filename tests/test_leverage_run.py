"""Runner, transport, isolation, retry, exclusion, hard-stop, result,
CLI, and economics tests for oracle-leverage-v1.

The fake executor below is a TEST-ONLY SYNTHETIC PROVIDER: it
simulates inference-boundary outcomes (clean runs, tampered
observations, provider failures) without any model call. It must
never be selectable in the frozen experimental schedule. All
produced repository states are hand-authored synthetic material in
temporary directories; frozen fixtures are read-only inputs.
"""

import json
import tempfile
from pathlib import Path

from project_context.leverage.model import EconomicsResult
from project_context.leverage.run import (
    ExecutorResult,
    WaveStop,
    build_result_artifact,
    build_run_env,
    execute_slot,
    preflight,
    run_wave,
    seed_workspace,
)
from project_context.opencode.bridge import (
    BRIDGE_SCHEMA_V2,
    CAPTURE_STAGE_V2,
    integrity_of,
    validate_record,
)

FIXTURES = Path("fixtures") / "oracle-leverage-v1"


def _record(system_texts: list[str], kind: str = "context") -> dict:
    system = [{"type": "text", "text": text} for text in system_texts]
    record = {
        "schema": BRIDGE_SCHEMA_V2,
        "capture_id": "cap-test-1",
        "captured_at": "2026-09-24T12:00:00Z",
        "capture_stage": CAPTURE_STAGE_V2,
        "request_kind": kind,
        "session_id": "ses_test",
        "invocation_sequence": 1,
        "agent": "build",
        "model": {"provider_id": "ollama", "id": "mistral-small:latest"},
        "system": system,
        "messages": [],
        "tools": {},
        "options": {},
    }
    record["integrity"] = {"sha256": integrity_of(record)}
    assert not validate_record(record)
    return record


def _expected_block(fixture_id: str, condition: str) -> str:
    fix = json.loads((FIXTURES / fixture_id / "fixture.json").read_text(encoding="utf-8"))
    content = fix["distractor_context" if condition == "D" else "oracle_context"]["content"]
    return "[CONTEXT RUNTIME]\n[TEST CONSTRAINT]\n" + content + "\n[/CONTEXT RUNTIME]"


class FakeExecutor:
    """TEST-ONLY SYNTHETIC PROVIDER. Modes per run_id: clean (valid
    observer record), tampered (marker dropped), empty (no records),
    fail-once (pre-response provider failure then clean), always-fail."""

    def __init__(self, modes: dict[str, str]):
        self.modes = modes
        self.calls: list[str] = []

    def __call__(self, slot, schedule, workspace, run_dir, env):
        run_id = slot["run_id"]
        self.calls.append(run_id)
        mode = self.modes.get(run_id, "clean")
        spool = run_dir / "spool"
        spool.mkdir(parents=True, exist_ok=True)
        path = spool / "captures.jsonl"
        if mode == "fail-once" and self.calls.count(run_id) == 1:
            return ExecutorResult(1, "", "provider down", status="provider_failure_before_response")
        if mode == "always-fail":
            return ExecutorResult(1, "", "provider down", status="provider_failure_before_response")
        if mode == "empty":
            return ExecutorResult(0, "READY", "", session_id="ses_test")
        condition = slot["condition"]
        if mode == "tampered":
            system = ["You are a test assistant."]
        elif condition == "N":
            system = ["You are a test assistant."]
        else:
            system = ["You are a test assistant.", _expected_block(slot["fixture_id"], condition)]
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(_record(system)) + "\n")
        return ExecutorResult(0, "READY", "", session_id="ses_test")


def _slot(schedule: dict, run_id: str) -> dict:
    return next(r for r in schedule["runs"] if r["run_id"] == run_id)


def test_schedule_consumed_in_exact_order_with_counts():
    schedule = json.loads(
        (Path("experiments") / "oracle-leverage-v1" / "schedule.json").read_text()
    )
    wave = Path(tempfile.mkdtemp()) / "wave"
    try:
        fake = FakeExecutor({})
        results = []
        for slot in schedule["runs"]:
            results.append(execute_slot(slot, schedule, FIXTURES, wave, fake))
        assert [r["run_id"] for r in results] == [f"olv1-r{n:03d}" for n in range(1, 25)]
        assert fake.calls == [f"olv1-r{n:03d}" for n in range(1, 25)]
        for result in results:
            assert result["graded"]["valid"] is True
            assert len(result["attempts"]) == 1
    finally:
        _rmtree(wave)


def _rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


def test_retry_only_on_preresponse_provider_failure():
    schedule = json.loads(
        (Path("experiments") / "oracle-leverage-v1" / "schedule.json").read_text()
    )
    wave = Path(tempfile.mkdtemp()) / "wave"
    try:
        slot = _slot(schedule, "olv1-r001")
        fake = FakeExecutor({"olv1-r001": "fail-once"})
        result = execute_slot(slot, schedule, FIXTURES, wave, fake)
        assert [a["infra_status"] for a in result["attempts"]] == [
            "provider_failure_before_response",
            "ok",
        ]
        assert (wave / "olv1-r001" / "attempt_1.json").is_file()
        assert (wave / "olv1-r001" / "attempt_2.json").is_file()
        assert result["graded"]["valid"] is True
    finally:
        _rmtree(wave)


def test_no_retry_on_behavioural_failure_or_transport_failure():
    schedule = json.loads(
        (Path("experiments") / "oracle-leverage-v1" / "schedule.json").read_text()
    )
    wave = Path(tempfile.mkdtemp()) / "wave"
    try:
        slot = _slot(schedule, "olv1-r001")
        fake = FakeExecutor({})
        result = execute_slot(slot, schedule, FIXTURES, wave, fake)
        assert len(result["attempts"]) == 1
        assert result["graded"]["behaviour"]["task_score"] == 0.0
        assert result["graded"]["valid"] is True
        slot2 = _slot(schedule, "olv1-r003")
        fake2 = FakeExecutor({"olv1-r003": "tampered"})
        result2 = execute_slot(slot2, schedule, FIXTURES, wave, fake2)
        assert len(result2["attempts"]) == 1
        assert result2["graded"]["valid"] is False
        assert result2["graded"]["exclusion_reason"] == "observer reconciliation failure"
    finally:
        _rmtree(wave)


def test_n_absence_pass_and_marker_presence_fail():
    schedule = json.loads(
        (Path("experiments") / "oracle-leverage-v1" / "schedule.json").read_text()
    )
    wave = Path(tempfile.mkdtemp()) / "wave"
    try:
        slot = _slot(schedule, "olv1-r001")
        result = execute_slot(slot, schedule, FIXTURES, wave, FakeExecutor({}))
        assert result["transport"]["status"] == "PASS"
        wave2 = Path(tempfile.mkdtemp()) / "wave"
        try:
            result2 = execute_slot(
                slot, schedule, FIXTURES, wave2, FakeExecutor({"olv1-r001": "tampered"})
            )
            assert result2["transport"]["status"] == "PASS"
        finally:
            _rmtree(wave2)
    finally:
        _rmtree(wave)


def test_hidden_truth_isolation_and_env():
    schedule = json.loads(
        (Path("experiments") / "oracle-leverage-v1" / "schedule.json").read_text()
    )
    wave = Path(tempfile.mkdtemp()) / "wave"
    try:
        slot = _slot(schedule, "olv1-r003")
        ws = wave / "ws-probe"
        digest = seed_workspace(slot["fixture_id"], FIXTURES, ws)
        assert digest == slot["repo_digest"]
        names = {p.name for p in ws.iterdir()}
        assert "truth.json" not in names and "fixture.json" not in names
        blob = "\n".join(
            p.read_text(encoding="utf-8", errors="replace") for p in ws.iterdir() if p.is_file()
        )
        for token in ("correct_action", "counterfactual", "ORACLE", "DISTRACTOR", "truth.json"):
            assert token not in blob
        env_o = build_run_env(wave / "r-o", dict(slot, condition="O"))
        assert env_o["PROJECT_CONTEXT_RUNTIME"] == "inject"
        assert "PROJECT_CONTEXT_RUNTIME_BLOCK" in env_o
        env_n = build_run_env(wave / "r-n", dict(slot, condition="N"))
        assert "PROJECT_CONTEXT_RUNTIME" not in env_n
        assert "PROJECT_CONTEXT_RUNTIME_BLOCK" not in env_n
        assert env_n["PROJECT_CONTEXT_CAPTURE"] == "1"
    finally:
        _rmtree(wave)


GOOD_DIGEST = "8039dd90c1138d772437a0779a33b7349efd5d9cca71edcd26e4dd463f90439d"
GOOD_ENTRIES = [{"name": "mistral-small:latest", "digest": GOOD_DIGEST}]


def test_model_digest_mismatch_stops_wave():
    schedule = json.loads(
        (Path("experiments") / "oracle-leverage-v1" / "schedule.json").read_text()
    )
    wave = Path(tempfile.mkdtemp()) / "wave"
    try:
        try:
            run_wave(
                schedule,
                FIXTURES,
                wave,
                FakeExecutor({}),
                None,
                entries=[{"name": "mistral-small:latest", "digest": "deadbeef"}],
            )
        except WaveStop as exc:
            assert "model digest mismatch" in exc.reason
        else:
            raise AssertionError("expected WaveStop")
        assert not wave.exists()
    finally:
        _rmtree(wave.parent)


def test_fixture_mismatch_stops_wave_with_prefix_preserved(monkeypatch):
    from project_context.leverage import run as run_mod

    schedule = json.loads(
        (Path("experiments") / "oracle-leverage-v1" / "schedule.json").read_text()
    )
    wave = Path(tempfile.mkdtemp()) / "wave"
    try:
        real_seed = run_mod.seed_workspace
        calls = []

        def flaky_seed(fixture_id, fixtures_root, workdir):
            calls.append(fixture_id)
            digest = real_seed(fixture_id, fixtures_root, workdir)
            if len(calls) == 2:
                return "0" * 64
            return digest

        monkeypatch.setattr(run_mod, "seed_workspace", flaky_seed)
        artifact = run_wave(
            schedule,
            FIXTURES,
            wave,
            FakeExecutor({}),
            "test-digest",
            entries=GOOD_ENTRIES,
        )
        assert artifact["hard_stop"] is not None
        assert "wrong starting repo state" in artifact["hard_stop"]
        assert [r["run_id"] for r in artifact["runs"]] == ["olv1-r001"]
        assert (wave / "olv1-r001" / "graded_run.json").is_file()
    finally:
        _rmtree(wave)


def test_economics_unavailable_never_zero_and_result_binds():
    schedule = json.loads(
        (Path("experiments") / "oracle-leverage-v1" / "schedule.json").read_text()
    )
    wave = Path(tempfile.mkdtemp()) / "wave"
    try:
        slot = _slot(schedule, "olv1-r001")
        result = execute_slot(slot, schedule, FIXTURES, wave, FakeExecutor({}))
        economics = result["economics"]
        assert economics["input_tokens"] is None
        assert economics["reported_cost"] is None
        assert economics["call_count"] == 1
        assert isinstance(economics["latency_s"], float)
        artifact = build_result_artifact(schedule, [result], "test-digest", "grader-d", "runner-d")
        assert artifact["run_count"] == 1
        assert artifact["actual_model_digest"] == "test-digest"
        assert artifact["grader_digest"] == "grader-d"
        core = {k: artifact[k] for k in sorted(artifact) if k != "result_digest"}
        import hashlib

        assert (
            hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
            == artifact["result_digest"]
        )
    finally:
        _rmtree(wave)


def test_condition_blind_grading_across_slots():
    from project_context.leverage.run import grade_workspace

    schedule = json.loads(
        (Path("experiments") / "oracle-leverage-v1" / "schedule.json").read_text()
    )
    wave = Path(tempfile.mkdtemp()) / "wave"
    try:
        outs = []
        for run_id in ("olv1-r001", "olv1-r009", "olv1-r017"):
            slot = _slot(schedule, run_id)
            assert slot["fixture_id"] == "t01-legacy-case"
            ws = wave / run_id
            seed_workspace(slot["fixture_id"], FIXTURES, ws)
            outs.append(grade_workspace(slot["fixture_id"], ws))
        assert outs[0] == outs[1] == outs[2]
    finally:
        _rmtree(wave)


def test_preflight_passes_with_zero_calls():
    report = preflight(entries=GOOD_ENTRIES)
    assert report["subject_model_calls"] == 0
    assert report["fixture_probing_calls"] == 0
    assert report["checks"]["overall"] == "PASS"
    assert report["model_identity"]["qualified"] == "ollama/mistral-small:latest"
    assert report["model_identity"]["provider_local"] == "mistral-small:latest"


def test_economics_model_roundtrip():
    full = EconomicsResult(1.5, 2, 100, 20, None, None, None).to_dict()
    assert EconomicsResult.from_dict(full).to_dict() == full
    assert full["reported_cost"] is None


def _schedule():
    return json.loads((Path("experiments") / "oracle-leverage-v1" / "schedule.json").read_text())


def test_identity_qualified_ollama_name_resolves():
    from project_context.leverage.run import parse_model_identity, verify_scheduled_model

    assert parse_model_identity("ollama/mistral-small:latest") == ("ollama", "mistral-small:latest")
    detail = verify_scheduled_model(_schedule(), entries=[dict(e) for e in GOOD_ENTRIES])
    assert detail["qualified"] == "ollama/mistral-small:latest"
    assert detail["provider"] == "ollama"
    assert detail["provider_local"] == "mistral-small:latest"
    assert detail["ok"] is True
    assert detail["actual_digest"] == detail["expected_digest"]


def test_identity_wrong_digest_still_fails():
    from project_context.leverage.run import verify_scheduled_model

    entries = [{"name": "mistral-small:latest", "digest": "0" * 64}]
    detail = verify_scheduled_model(_schedule(), entries=entries)
    assert detail["ok"] is False
    assert detail["actual_digest"] == "0" * 64


def test_identity_missing_entry_fails():
    from project_context.leverage.run import verify_scheduled_model

    detail = verify_scheduled_model(_schedule(), entries=[])
    assert detail["ok"] is False
    assert detail["actual_digest"] is None


def test_identity_wrong_provider_does_not_alias():
    from project_context.leverage.run import parse_model_identity, verify_scheduled_model

    schedule = _schedule()
    schedule = json.loads(json.dumps(schedule))
    schedule["subject_model"] = dict(schedule["subject_model"])
    schedule["subject_model"]["model"] = "other-registry/mistral-small:latest"
    assert parse_model_identity("other-registry/mistral-small:latest") == (
        "other-registry",
        "mistral-small:latest",
    )
    detail = verify_scheduled_model(schedule, entries=[dict(e) for e in GOOD_ENTRIES])
    assert detail["ok"] is False
    assert detail["actual_digest"] is None


def test_identity_slash_local_name_kept_intact():
    from project_context.leverage.run import parse_model_identity

    assert parse_model_identity("ollama/org/model:tag") == ("ollama", "org/model:tag")
    assert parse_model_identity("mistral-small:latest") == ("", "mistral-small:latest")


def test_preflight_and_wave_share_verifier():
    import inspect

    from project_context.leverage import run as run_mod

    preflight_params = set(inspect.signature(run_mod.preflight).parameters)
    assert "expected_model" not in preflight_params
    assert "model_check" not in preflight_params
    report = run_mod.preflight(entries=[dict(e) for e in GOOD_ENTRIES])
    assert report["checks"]["model_metadata_identity"] == "PASS"
    assert report["model_identity"]["qualified"] == "ollama/mistral-small:latest"


def test_wave_reaches_inference_boundary_after_identity():
    from project_context.leverage import run as run_mod

    schedule = _schedule()
    wave = Path(tempfile.mkdtemp()) / "wave"

    class Sentinel(Exception):
        pass

    def sentinel_executor(slot, schedule, workspace, run_dir, env):
        raise Sentinel("inference boundary crossed")

    try:
        try:
            run_mod.run_wave(
                schedule,
                FIXTURES,
                wave,
                sentinel_executor,
                "test-digest",
                entries=[dict(e) for e in GOOD_ENTRIES],
            )
        except Sentinel:
            pass
        else:
            raise AssertionError("expected Sentinel (identity passed, inference reached)")
    finally:
        _rmtree(wave.parent)


def test_wave_stops_before_inference_on_identity_failure():
    schedule = _schedule()
    wave = Path(tempfile.mkdtemp()) / "wave"
    calls = []

    def counting_executor(slot, schedule, workspace, run_dir, env):
        calls.append(slot["run_id"])
        raise AssertionError("must not reach inference")

    try:
        try:
            run_wave(schedule, FIXTURES, wave, counting_executor, None, entries=[])
        except WaveStop as exc:
            assert "model digest mismatch" in exc.reason
        else:
            raise AssertionError("expected WaveStop")
        assert calls == []
    finally:
        _rmtree(wave.parent)


def test_production_argv_uses_resolved_executable(monkeypatch):
    import subprocess as subprocess_mod

    from project_context.leverage import run as run_mod

    def fake_which(name):
        return "C:\\Tools\\opencode.CMD" if name == "opencode" else None

    monkeypatch.setattr(run_mod.shutil, "which", fake_which)
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

        class Done:
            returncode = 0
            stdout = "READY"
            stderr = ""

        return Done()

    monkeypatch.setattr(subprocess_mod, "run", fake_run)
    schedule = _schedule()
    slot = next(r for r in schedule["runs"] if r["run_id"] == "olv1-r003")
    out = run_mod.production_executor(
        slot, schedule, Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()), {}
    )
    assert seen["cmd"][0] == "C:\\Tools\\opencode.CMD"
    assert seen["cmd"][1:6] == [
        "run",
        "--standalone",
        "--auto",
        "--model",
        "ollama/mistral-small:latest",
    ]
    assert "shell" not in seen["kwargs"]
    assert out.returncode == 0


def test_preflight_and_executor_share_resolver(monkeypatch):
    from project_context.leverage import run as run_mod

    calls = []
    monkeypatch.setattr(run_mod, "resolve_opencode_executable", lambda: calls.append(1) or None)
    report = run_mod.preflight(entries=[dict(e) for e in GOOD_ENTRIES])
    assert report["checks"]["production_executable_resolution"] != "PASS"
    assert report["checks"]["overall"] != "PASS"
    schedule = _schedule()
    slot = next(r for r in schedule["runs"] if r["run_id"] == "olv1-r003")
    try:
        run_mod.production_executor(
            slot, schedule, Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()), {}
        )
    except WaveStop:
        pass
    else:
        raise AssertionError("expected WaveStop")
    assert len(calls) == 2


def test_missing_executable_fails_closed(monkeypatch):
    from project_context.leverage import run as run_mod

    assert run_mod.resolve_opencode_executable() is not None
    monkeypatch.setattr(run_mod.shutil, "which", lambda name: None)
    assert run_mod.resolve_opencode_executable() is None
    report = run_mod.preflight(entries=[dict(e) for e in GOOD_ENTRIES])
    assert report["checks"]["production_executable_resolution"] != "PASS"
    assert report["checks"]["overall"] != "PASS"


def test_spaced_path_preserved_verbatim(monkeypatch):
    from project_context.leverage import run as run_mod

    spaced = "C:\\Users\\Example User\\AppData\\Roaming\\npm\\opencode.CMD"
    monkeypatch.setattr(run_mod.shutil, "which", lambda name: spaced)
    assert run_mod.resolve_opencode_executable() == spaced


def test_wave_reaches_executor_after_identity():
    from project_context.leverage import run as run_mod

    schedule = _schedule()
    wave = Path(tempfile.mkdtemp()) / "wave"

    class Sentinel(Exception):
        pass

    def sentinel_executor(slot, schedule, workspace, run_dir, env):
        raise Sentinel("inference boundary reached")

    try:
        try:
            run_mod.run_wave(
                schedule,
                FIXTURES,
                wave,
                sentinel_executor,
                "test-digest",
                entries=[dict(e) for e in GOOD_ENTRIES],
            )
        except Sentinel:
            pass
        else:
            raise AssertionError("expected Sentinel (setup passed, inference reached)")
    finally:
        _rmtree(wave.parent)


def test_resolved_executable_spawns_version_without_inference():
    import subprocess as subprocess_mod

    from project_context.leverage.run import opencode_version, resolve_opencode_executable

    resolved = resolve_opencode_executable()
    assert resolved is not None
    version = opencode_version(resolved)
    assert version is not None and len(version) > 0
    proc = subprocess_mod.run([resolved, "--version"], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0


def test_cli_preflight_and_execute_guard(monkeypatch, tmp_path):
    from project_context.cli.main import main
    from project_context.leverage import run as run_mod

    monkeypatch.setattr(
        run_mod,
        "fetch_daemon_tags",
        lambda timeout=20: [dict(entry) for entry in GOOD_ENTRIES],
    )
    assert main(["leverage", "preflight"]) == 0
    assert main(["leverage", "execute"]) == 2

    def fake_production(slot, schedule, workspace, run_dir, env):
        mode_executor = FakeExecutor({slot["run_id"]: "clean"})
        return mode_executor(slot, schedule, workspace, run_dir, env)

    monkeypatch.setattr(run_mod, "production_executor", fake_production)
    wave = tmp_path / "wave"
    assert main(["leverage", "execute", "--confirm", "--wave-dir", str(wave)]) == 0
    assert (wave / "result.json").is_file()


# --- transport liveness gate (harness-amendment-03) ------------------


def _canary(**overrides: object) -> dict:
    doc = {
        "canary": "project-context transport liveness",
        "result": "PASS",
        "marker": "TEST-MARKER-1",
        "session_id": "ses_test",
        "invocation_sequence": 1,
        "pre_blocks": 4,
        "post_blocks": 5,
        "requested_model": "ollama/mistral-small:latest",
        "observed_provider": "ollama",
        "observed_model": "mistral-small:latest",
        "observed_variant": None,
        "opencode_version": "2.0.16",
        "plugin_package": "project-context-opencode",
        "plugin_version": "0.1.0",
        "plugin_commit": "test-commit",
        "completed_at": "2026-09-24T00:00:00+00:00",
    }
    doc.update(overrides)
    return doc


def _write_canary(tmp_path: Path, **overrides: object) -> Path:
    path = tmp_path / "canary.json"
    path.write_text(json.dumps(_canary(**overrides)), encoding="utf-8")
    return path


def test_transport_liveness_absent_by_default():
    report = preflight(entries=GOOD_ENTRIES)
    assert "transport_liveness" not in report["checks"]
    assert report["checks"]["overall"] == "PASS"


def test_transport_liveness_missing_canary_fails_closed(tmp_path):
    report = preflight(
        entries=GOOD_ENTRIES, transport_canary=str(tmp_path / "absent.json")
    )
    assert report["checks"]["transport_liveness"].startswith("FAIL")
    assert report["checks"]["overall"] == "FAIL"


def test_transport_liveness_wrong_model_fails(tmp_path, monkeypatch):
    from project_context.leverage import run as run_mod

    monkeypatch.setattr(
        run_mod, "resolve_opencode_executable", lambda: "opencode"
    )
    canary = _write_canary(tmp_path, requested_model="other/model:tag")
    report = preflight(entries=GOOD_ENTRIES, transport_canary=str(canary))
    assert "scheduled" in report["checks"]["transport_liveness"]
    assert report["checks"]["overall"] == "FAIL"


def test_transport_liveness_nonpass_canary_fails(tmp_path, monkeypatch):
    from project_context.leverage import run as run_mod

    monkeypatch.setattr(
        run_mod, "resolve_opencode_executable", lambda: "opencode"
    )
    canary = _write_canary(tmp_path, result="FAIL")
    report = preflight(entries=GOOD_ENTRIES, transport_canary=str(canary))
    assert report["checks"]["transport_liveness"].startswith("FAIL")
    assert report["checks"]["overall"] == "FAIL"


def test_transport_liveness_passes_with_matching_canary(tmp_path, monkeypatch):
    import subprocess as subprocess_mod

    from project_context.leverage import run as run_mod

    monkeypatch.setattr(
        run_mod, "resolve_opencode_executable", lambda: "opencode"
    )

    class Listed:
        returncode = 0
        stdout = "project-context  0.1.0  github:ernanhughes/project-context-opencode"

    monkeypatch.setattr(
        subprocess_mod, "run", lambda *a, **k: Listed()
    )
    canary = _write_canary(tmp_path)
    report = preflight(entries=GOOD_ENTRIES, transport_canary=str(canary))
    assert report["checks"]["transport_liveness"] == "PASS"
    assert report["checks"]["overall"] == "PASS"


def test_transport_liveness_missing_package_fails(tmp_path, monkeypatch):
    import subprocess as subprocess_mod

    from project_context.leverage import run as run_mod

    monkeypatch.setattr(
        run_mod, "resolve_opencode_executable", lambda: "opencode"
    )

    class Listed:
        returncode = 0
        stdout = "code-review-graph  local  somewhere"

    monkeypatch.setattr(
        subprocess_mod, "run", lambda *a, **k: Listed()
    )
    canary = _write_canary(tmp_path)
    report = preflight(entries=GOOD_ENTRIES, transport_canary=str(canary))
    assert "not installed" in report["checks"]["transport_liveness"]
    assert report["checks"]["overall"] == "FAIL"


def _write_compiler_canary(tmp_path, **overrides):
    doc = {
        "schema": "project_context.compile_canary.v1",
        "status": "PASS",
        "compiler": {"packageVersion": "0.2.3", "revision": "test-rev"},
        "request": {"request_id": "r", "policy_version": "compiler-policy-v1"},
        "compilation": {
            "success": True,
            "bundle_id": "b",
            "bundle_hash": "h",
            "bundle_tokens": 29,
        },
        "render": {"rendered_hash": "rh"},
        "transport": {
            "runtime_block_hash": "bh",
            "runtime_outcome": "injected",
            "pre_blocks": 4,
            "post_blocks": 5,
        },
        "observer": {
            "session_id": "ses_test",
            "sequence": 1,
            "observed_model": "ollama/mistral-small:latest",
            "marker_count": 1,
        },
        "reconciliation": {
            "compiler_render_exact": True,
            "runtime_exact": True,
            "bundle_id_match": True,
            "bundle_hash_match": True,
            "model_match": True,
        },
        "failures": [],
    }
    doc.update(overrides)
    path = tmp_path / "compiler-canary.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_compiler_liveness_absent_by_default():
    report = preflight(entries=GOOD_ENTRIES)
    assert "compiler_liveness" not in report["checks"]
    assert report["checks"]["overall"] == "PASS"


def test_compiler_liveness_missing_canary_fails_closed(tmp_path):
    report = preflight(
        entries=GOOD_ENTRIES, compiler_canary=str(tmp_path / "absent.json")
    )
    assert report["checks"]["compiler_liveness"].startswith("FAIL")
    assert report["checks"]["overall"] == "FAIL"


def test_compiler_liveness_wrong_model_fails(tmp_path):
    canary = _write_compiler_canary(tmp_path)
    doc = json.loads(canary.read_text(encoding="utf-8"))
    doc["observer"]["observed_model"] = "other/model:tag"
    canary.write_text(json.dumps(doc), encoding="utf-8")
    report = preflight(entries=GOOD_ENTRIES, compiler_canary=str(canary))
    assert "scheduled" in report["checks"]["compiler_liveness"]
    assert report["checks"]["overall"] == "FAIL"


def test_compiler_liveness_failed_reconciliation_fails(tmp_path):
    canary = _write_compiler_canary(tmp_path)
    doc = json.loads(canary.read_text(encoding="utf-8"))
    doc["reconciliation"]["bundle_hash_match"] = False
    doc["failures"] = ["bundle_hash"]
    canary.write_text(json.dumps(doc), encoding="utf-8")
    report = preflight(entries=GOOD_ENTRIES, compiler_canary=str(canary))
    assert report["checks"]["compiler_liveness"].startswith("FAIL")
    assert report["checks"]["overall"] == "FAIL"


def test_compiler_liveness_passes_with_matching_canary(tmp_path):
    canary = _write_compiler_canary(tmp_path)
    report = preflight(entries=GOOD_ENTRIES, compiler_canary=str(canary))
    assert report["checks"]["compiler_liveness"] == "PASS"
    assert report["checks"]["overall"] == "PASS"


def test_build_run_env_absolutizes_relative_run_dir(tmp_path, monkeypatch):
    import os

    from project_context.leverage.run import build_run_env

    schedule = _schedule()
    slot = _slot(schedule, "olv1-r001")
    monkeypatch.chdir(tmp_path)
    env = build_run_env(Path("rel-wave") / "olv1-r001", slot)
    for key in (
        "PROJECT_CONTEXT_SPOOL_DIR",
        "PROJECT_CONTEXT_RUNTIME_TRACE_DIR",
        "PROJECT_CONTEXT_RUNTIME_BLOCK",
    ):
        if slot["condition"] == "N" and key == "PROJECT_CONTEXT_RUNTIME_BLOCK":
            continue
        assert os.path.isabs(env[key]), key
    assert Path(env["PROJECT_CONTEXT_SPOOL_DIR"]).parent.parent.name == "rel-wave"


def test_relative_wave_dir_keeps_evidence_out_of_workspace(tmp_path, monkeypatch):
    from project_context.leverage import run as run_mod

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    schedule = _schedule()
    slot = _slot(schedule, "olv1-r002")
    abs_fixtures = FIXTURES.resolve()
    monkeypatch.chdir(elsewhere)
    run_dir = Path("rel-wave") / slot["run_id"]
    env = run_mod.build_run_env(run_dir, slot)
    block_path = Path(env["PROJECT_CONTEXT_RUNTIME_BLOCK"])
    assert block_path.is_absolute
    text, digest = run_mod.render_condition_payload(slot, abs_fixtures, block_path)
    assert text is not None and block_path.is_file()
    assert block_path.read_text(encoding="utf-8") == text
    assert block_path.parent == (elsewhere / "rel-wave" / slot["run_id"]).resolve()
    spool = Path(env["PROJECT_CONTEXT_SPOOL_DIR"])
    assert spool.is_absolute and spool.parent == block_path.parent
    stray = [
        p
        for p in elsewhere.rglob("*")
        if p.is_file() and (elsewhere / "rel-wave") not in p.parents
    ]
    assert stray == [], stray
    assert list((elsewhere / "rel-wave").rglob("workspace")) == []
