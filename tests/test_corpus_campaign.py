"""Stage 2 corpus campaign tests: counting, gates, weighting, safety."""

import json
from pathlib import Path

from project_context.cli.main import main as cli_main
from project_context.corpus.campaign import CampaignManifest
from project_context.corpus.campaign_store import add_spool
from project_context.domain.bundles import build_bundle
from project_context.domain.items import make_item
from project_context.opencode.ingest import SequenceTracker, ingest_record
from project_context.opencode.prevalence import (
    analyse_bundles,
    assert_exportable,
    composition_report,
    export_report,
    repetition_report,
    session_bundles,
    session_weighted_tool_share,
)


def _spool(tmp_path: Path, files: dict[str, list[dict]]) -> Path:
    spool = tmp_path / "spool"
    spool.mkdir()
    for name, records in files.items():
        (spool / name).write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in records),
            encoding="utf-8",
        )
    return spool


def _record(capture_id, hook, session, payload_extra=None, evidence="opencode_capture"):
    record = {
        "schema": "project_context.opencode_capture.v1",
        "capture_id": capture_id,
        "captured_at": "2026-09-23T00:00:00Z",
        "capture_stage": "opencode.v1.pre_dispatch_partial",
        "hook_kind": hook,
        "session_id": session,
        "agent": None,
        "model": None,
        "sequence_scope": session or "unlinked",
        "sequence_index": 1,
        "adapter_version": "0.1.0",
        "opencode_version": "1.18.27",
        "plugin_api_version": "@opencode-ai/plugin 1.18.27",
        "observer_position": "last-registered",
        "payload": payload_extra or {},
        "integrity": {"sha256": "0" * 64},
        "timings_ms": {"serialize": 0, "write": 0, "total": 0},
        "evidence_class": evidence,
    }
    return record


def _blank_campaign():
    return CampaignManifest(
        campaign_id="test",
        target_sessions=10,
        capture_schema="project_context.opencode_capture.v1",
        capture_stage="opencode.v1.pre_dispatch_partial",
        opencode_version="1.18.27",
        adapter_version="0.1.0",
        started_at="2026-09-23T00:00:00Z",
    )


def _add(campaign, spool, root, label="batch-a"):
    return add_spool(campaign, spool, label, root)


def test_synthetic_evidence_refused_from_campaign(tmp_path):
    spool = _spool(
        tmp_path,
        {
            "a.jsonl": [
                _record(
                    "c1", "system.transform", "ses-1", {"system": ["x"]}, evidence="synthetic-test"
                )
            ]
        },
    )
    updated, result, _index = _add(_blank_campaign(), spool, tmp_path)
    assert result.sessions_added == 0
    assert updated.genuine_session_count() == 0
    assert any(e.reason == "synthetic-evidence" for e in updated.exclusions)


def test_unique_genuine_sessions_counted_once(tmp_path):
    recs_a = [
        _record("c1", "system.transform", "ses-1", {"system": ["x"]}),
        _record(
            "c2",
            "tool.execute.after",
            "ses-1",
            {
                "tool_result": {
                    "tool": "t",
                    "callID": "k",
                    "title": "",
                    "output": "out",
                    "metadata": {},
                }
            },
        ),
    ]
    recs_b = [_record("c3", "system.transform", "ses-1", {"system": ["x"]})]
    spool = _spool(tmp_path, {"a.jsonl": recs_a, "b.jsonl": recs_b})
    updated, result, _index = _add(_blank_campaign(), spool, tmp_path)
    assert result.sessions_seen == 1
    assert updated.genuine_session_count() == 1
    assert updated.sessions[0].invocation_count == 3


def test_corrupt_session_excluded_with_reason(tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    (spool / "bad.jsonl").write_text(
        '{"schema": "project_context.opencode_capture.v1", "oops"\n', encoding="utf-8"
    )
    updated, result, _index = _add(_blank_campaign(), spool, tmp_path)
    assert updated.genuine_session_count() == 0
    assert result.skipped_lines == 1


def test_observed_zero_vs_unobserved(tmp_path):

    tracker = SequenceTracker()
    bundles = [
        ingest_record(
            _record(
                "c1",
                "tool.execute.after",
                "ses-1",
                {
                    "tool_result": {
                        "tool": "t",
                        "callID": "k",
                        "title": "",
                        "output": "out",
                        "metadata": {},
                    }
                },
            ),
            tracker,
        )[0]
    ]
    report = composition_report(bundles)
    assert report["items_by_role"].get("tool_call", 0) == 0
    assert report["tool_definitions"] == "UNOBSERVED"


def test_session_vs_invocation_weighting():

    tracker = SequenceTracker()
    bundles = []
    for i in range(4):
        bundle, _ = ingest_record(
            _record(
                f"a{i}",
                "tool.execute.after",
                "big",
                {
                    "tool_result": {
                        "tool": "t",
                        "callID": f"k{i}",
                        "title": "",
                        "output": "x" * 100,
                        "metadata": {},
                    }
                },
            ),
            tracker,
        )
        bundles.append(bundle)
    bundle, _ = ingest_record(
        _record("b0", "system.transform", "small", {"system": ["y" * 10]}),
        tracker,
    )
    bundles.append(bundle)
    sessions = session_bundles(bundles)
    weighted = session_weighted_tool_share(sessions)
    assert weighted["invocation_weighted_share"] > weighted["session_weighted_share"]
    assert weighted["sessions"] == 2


def test_prefix_never_crosses_sessions():
    from project_context.opencode.ingest import SequenceTracker, ingest_record
    from project_context.opencode.prevalence import structural_shared_prefix

    tracker = SequenceTracker()
    first, _ = ingest_record(
        _record("c1", "system.transform", "ses-a", {"system": ["same"]}), tracker
    )
    second, _ = ingest_record(
        _record("c2", "system.transform", "ses-b", {"system": ["same"]}), tracker
    )
    result = structural_shared_prefix(first, second)
    assert result["comparable"] is False


def test_repetition_exact_identity_only():

    items = [
        make_item(id="a", source="s", kind="k", content="identical bytes"),
        make_item(id="b", source="s", kind="k", content="identical bytes!"),
        make_item(id="c", source="s", kind="k", content="identical bytes"),
    ]
    bundle = build_bundle(items, bundle_id="b", created_at="t")
    report = repetition_report([bundle])
    assert report["within_bundle_duplicate_items"] == 1


def test_aggregate_export_clean_and_rekeyed(tmp_path):

    tracker = SequenceTracker()
    bundles = [
        ingest_record(
            _record("c1", "system.transform", "ses-real-9", {"system": ["zzz"]}),
            tracker,
        )[0]
    ]
    exported = export_report(analyse_bundles(bundles))
    assert assert_exportable(exported) == []
    assert "ses-real-9" not in json.dumps(exported)
    assert "session-001" in json.dumps(exported) or "S01" in json.dumps(exported)


def test_export_rejects_local_paths_and_hashes():
    from project_context.opencode.prevalence import assert_exportable

    bad = {
        "bundles": 1,
        "growth_by_session": {"S01": {"sizes": [10]}},
        "content": "hello",
        "digest": "abc",
        "path": "C:\\secret\\x",
    }
    errors = assert_exportable(bad)
    assert any("content" in e for e in errors)
    assert any("digest" in e for e in errors)


def test_under_target_readiness(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli_main(["corpus", "campaign", "create", "--id", "camp1"]) == 0
    assert cli_main(["corpus", "campaign", "status", "--id", "camp1"]) == 0
    out = capsys.readouterr().out
    assert "UNDER TARGET" in out
    assert "genuine sessions: 0" in out


def test_exclusion_ledger_deterministic(tmp_path):
    spool = _spool(
        tmp_path,
        {
            "a.jsonl": [
                _record(
                    "c1", "system.transform", "ses-1", {"system": ["x"]}, evidence="synthetic-test"
                ),
                {"schema": "project_context.opencode_capture.v9"},
            ]
        },
    )
    first, _, _ = _add(_blank_campaign(), spool, tmp_path)
    second, _, _ = _add(_blank_campaign(), spool, tmp_path)
    assert [e.to_dict() for e in first.exclusions] == [e.to_dict() for e in second.exclusions]
    reasons = sorted(e.reason for e in first.exclusions)
    assert reasons == ["invalid-schema", "synthetic-evidence"]


def test_analysis_run_records_versions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli_main(["corpus", "campaign", "create", "--id", "camp2"]) == 0
    code = cli_main(
        [
            "corpus",
            "prevalence",
            str(tmp_path),
            "--run-id",
            "run-x",
            "--runs-dir",
            str(tmp_path / "runs-out"),
        ]
    )
    assert code == 0
    manifest = json.loads(
        (tmp_path / "runs-out" / "ecological-prevalence-v1" / "run-x" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["evidence_class"] == "ecological-observation"
    assert "git_commit" in manifest


def test_publication_gate_still_rejects_raw():
    from project_context.corpus.manifest import (
        CorpusManifest,
        UnsanitisedCorpusError,
        assert_publishable,
    )

    manifest = CorpusManifest(
        corpus_id="c",
        trace_id="t",
        source_type="opencode",
        captured_at="t",
        turn_count=1,
        tool_call_count=1,
        rendered_token_min=1,
        rendered_token_max=2,
        sanitisation_status="raw-local",
        content_hash="withheld-local",
    )
    try:
        assert_publishable(manifest)
    except UnsanitisedCorpusError:
        pass
    else:
        raise AssertionError("gate must refuse raw-local")


def test_no_process_management_code():
    import pathlib
    import re

    roots = [
        pathlib.Path("src"),
        pathlib.Path("integrations") / "opencode" / "src",
    ]
    tokens = [
        "taskkill",
        "pkill",
        "killall",
        "Stop-Process",
        "process.kill",
        "child_process",
        "os.kill",
        "SIGKILL",
        "terminateProcess",
    ]
    hits = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in tokens:
                if re.search(r"(?i)" + re.escape(token), text):
                    hits.append(f"{path}:{token}")
        for path in root.rglob("*.ts"):
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for token in tokens:
                if re.search(r"(?i)" + re.escape(token), text):
                    hits.append(f"{path}:{token}")
    assert hits == [], f"process-management code detected: {hits}"


def test_no_intervention_behaviour_in_new_modules():
    import pathlib
    import re

    for path in list(pathlib.Path("src/project_context/opencode").glob("*.py")) + list(
        pathlib.Path("src/project_context/corpus").glob("*.py")
    ):
        text = path.read_text(encoding="utf-8")
        for name in (
            "def prune",
            "def compact",
            "def decay",
            "def retrieve",
            "def assemble",
            "def rank",
            "def select",
        ):
            assert not re.search(rf"^{name}\(", text, re.M), f"{path}: {name}"
