"""Stage 6A Context Ledger tests: records, lifecycle, replay, fixtures, boundaries.

Nothing here calls models or network. The fixture truth file is loaded
only to assert outcomes; ledger runtime code never reads it.
"""

import json
import re
from pathlib import Path

import pytest

from project_context.cli.main import main as cli_main
from project_context.ledger import events as E
from project_context.ledger import projection as P
from project_context.ledger import records as R
from project_context.ledger import relationships as Rel
from project_context.ledger import store as S
from project_context.ledger.lifecycle import TRANSITIONS, is_legal
from project_context.ledger.records import (
    TERMINAL_STATUSES,
    Authority,
    ItemKind,
    LedgerItem,
    LedgerScope,
    LifecycleStatus,
    SourceProvenance,
    VerificationState,
)

ROOT = Path("fixtures") / "ledger-v1"
EVENTS_PATH = ROOT / "events.jsonl"
TRUTH_PATH = ROOT / "ledger-v1.truth.json"


def _event(event_id, kind, item_id, recorded_at, **extra):
    doc = {
        "schema_version": E.LEDGER_EVENT_SCHEMA,
        "event_id": event_id,
        "event": kind,
        "item_id": item_id,
        "recorded_at": recorded_at,
        **extra,
    }
    return E.LedgerEvent.from_dict(doc)


def _item_doc(item_id, kind="obligation", authority="agent"):
    return {
        "schema_version": R.LEDGER_ITEM_SCHEMA,
        "item_id": item_id,
        "kind": kind,
        "statement": f"statement for {item_id}",
        "authority": authority,
        "scope": {},
        "source": {},
    }


def _created(item_id, stamp="2026-09-24T10:00:00Z", **kwargs):
    return _event(
        f"create-{item_id}", "item_created", item_id, stamp, item=_item_doc(item_id, **kwargs)
    )


def _truth():
    return json.loads(TRUTH_PATH.read_text(encoding="utf-8"))["expected"]


# --- records ------------------------------------------------------------------


def test_record_round_trip():
    item = LedgerItem(
        item_id="x-001",
        kind=ItemKind.DECISION,
        statement="Schema v2 is canonical.",
        authority=Authority.PROJECT,
        scope=LedgerScope(repo="r", paths=("a/b",), component="schema"),
        source=SourceProvenance(session="s", invocation="i", note="n"),
    )
    assert LedgerItem.from_dict(item.to_dict()) == item


def test_event_round_trip():
    event = _event(
        "e1",
        "verified",
        "x-001",
        "2026-09-24T10:00:00Z",
        outcome="passed",
        evidence={"kind": "test_run", "ref": "pytest t.py"},
        actor="tool",
        reason="r",
    )
    assert E.LedgerEvent.from_dict(event.to_dict()) == event


def test_strict_loaders_reject_unknown_keys():
    item = LedgerItem.from_dict(_item_doc("x-1")).to_dict()
    item["surprise"] = 1
    with pytest.raises(ValueError, match="unknown LedgerItem keys"):
        LedgerItem.from_dict(item)
    bad = _created("x-2").to_dict()
    bad["surprise"] = 1
    with pytest.raises(E.LedgerError) as exc:
        E.LedgerEvent.from_dict(bad)
    assert exc.value.code == "unsupported_schema"
    with pytest.raises(ValueError, match="unknown ledger scope keys"):
        LedgerScope.from_dict({"surprise": 1})


def test_unsupported_schema_fails_loudly():
    bad = _created("x-1").to_dict()
    bad["schema_version"] = "project_context.ledger_event.v99"
    with pytest.raises(E.LedgerError) as exc:
        E.LedgerEvent.from_dict(bad)
    assert exc.value.code == "unsupported_schema"


# --- replay and projection ----------------------------------------------------


def test_replay_is_deterministic():
    events = S.load_events(EVENTS_PATH)
    assert P.project(events).digest() == P.project(events).digest()


def test_append_only_history_reconstructs_state():
    state = P.project(S.load_events(EVENTS_PATH))
    item = state.get("obligation-001")
    assert item.status is LifecycleStatus.ACTIVE
    kinds = [step.to_status for step in item.history]
    assert kinds[0] == "active"
    assert "blocked" in kinds
    assert kinds[-1] == "active"
    assert state.explain("obligation-001")


def test_explain_traces_every_state_to_events():
    state = P.project(S.load_events(EVENTS_PATH))
    lines = state.explain("decision-001")
    assert any("evt-002" in line for line in lines)
    assert any("evt-009" in line for line in lines)
    assert any("superseded_by=decision-002" in line for line in lines)


# --- lifecycle ----------------------------------------------------------------


def test_valid_transitions_succeed():
    events = [
        _created("a"),
        _event("b1", "blocked", "a", "2026-09-24T10:01:00Z", reason="wait"),
        _event("u1", "unblocked", "a", "2026-09-24T10:02:00Z", reason="ready"),
        _event("s1", "satisfied", "a", "2026-09-24T10:03:00Z"),
    ]
    state = P.project(events)
    assert state.get("a").status is LifecycleStatus.SATISFIED


def test_invalid_transitions_fail_loudly():
    events = [
        _created("a"),
        _event("s1", "satisfied", "a", "2026-09-24T10:01:00Z"),
        _event("u1", "unblocked", "a", "2026-09-24T10:02:00Z"),
    ]
    with pytest.raises(E.LedgerError) as exc:
        P.project(events)
    assert exc.value.code == "invalid_transition"


def test_terminal_state_cannot_silently_become_active():
    for terminal, code in (
        ("satisfied", "s1"),
        ("failed", "f1"),
        ("cancelled", "c1"),
        ("expired", "e1"),
        ("superseded", None),
        ("contradicted", None),
    ):
        if terminal in ("superseded", "contradicted"):
            continue  # covered by dedicated tests below
        events = [
            _created("a"),
            _event(code, terminal, "a", "2026-09-24T10:01:00Z"),
            _event("b9", "blocked", "a", "2026-09-24T10:02:00Z"),
        ]
        with pytest.raises(E.LedgerError) as exc:
            P.project(events)
        assert exc.value.code == "invalid_transition"
    assert TERMINAL_STATUSES == frozenset(
        {
            LifecycleStatus.SATISFIED,
            LifecycleStatus.FAILED,
            LifecycleStatus.SUPERSEDED,
            LifecycleStatus.CANCELLED,
            LifecycleStatus.EXPIRED,
            LifecycleStatus.CONTRADICTED,
        }
    )
    assert not is_legal(LifecycleStatus.SATISFIED, LifecycleStatus.ACTIVE)
    assert is_legal(LifecycleStatus.BLOCKED, LifecycleStatus.ACTIVE)
    assert set(TRANSITIONS) == set(LifecycleStatus)


def test_unknown_item_fails_loudly():
    with pytest.raises(E.LedgerError) as exc:
        P.project([_event("x1", "satisfied", "ghost", "2026-09-24T10:00:00Z")])
    assert exc.value.code == "unknown_item"


# --- relationships --------------------------------------------------------------


def test_supersession_is_directional_and_deterministic():
    events = [_created("old", kind="decision"), _created("new", kind="decision")]
    forward = events + [
        _event(
            "r1",
            "relationship_added",
            "new",
            "2026-09-24T10:01:00Z",
            relationship={"type": "supersedes", "source_id": "new", "target_id": "old"},
        )
    ]
    state = P.project(forward)
    assert state.get("old").status is LifecycleStatus.SUPERSEDED
    assert state.get("old").superseded_by == "new"
    assert state.get("new").status is LifecycleStatus.ACTIVE
    assert P.project(forward).digest() == P.project(forward).digest()


def test_contradiction_preserves_provenance():
    state = P.project(S.load_events(EVENTS_PATH))
    claim = state.get("claim-002")
    assert claim.status is LifecycleStatus.CONTRADICTED
    assert claim.contradicted_by == "result-001"
    assert claim.verification is VerificationState.CONTRADICTED
    assert state.get("result-001").status is LifecycleStatus.ACTIVE
    assert state.get("result-001").verification is VerificationState.VERIFIED


def test_unknown_relationship_target_fails_validation():
    events = [
        _created("a"),
        _event(
            "r1",
            "relationship_added",
            "a",
            "2026-09-24T10:01:00Z",
            relationship={"type": "depends_on", "source_id": "a", "target_id": "ghost"},
        ),
    ]
    with pytest.raises(E.LedgerError) as exc:
        P.project(events)
    assert exc.value.code == "broken_reference"


def test_relationship_kinds_parse():
    rel = Rel.Relationship.from_dict({"type": "derived_from", "source_id": "a", "target_id": "b"})
    assert rel.to_dict() == {"type": "derived_from", "source_id": "a", "target_id": "b"}
    with pytest.raises(E.LedgerError):
        Rel.Relationship.from_dict({"type": "reminds", "source_id": "a", "target_id": "b"})
    with pytest.raises(E.LedgerError):
        Rel.Relationship.from_dict({"type": "blocks", "source_id": "a", "target_id": "a"})


# --- verification -----------------------------------------------------------------


def test_verification_evidence_is_retained():
    state = P.project(S.load_events(EVENTS_PATH))
    verified = state.get("verification-001")
    assert verified.verification is VerificationState.VERIFIED
    assert verified.evidence[0]["ref"] == "pytest tests/test_parser_compat.py"
    assert verified.evidence[0]["event_id"] == "evt-013"


def test_failed_verification_cannot_become_verified():
    events = [
        _created("c", kind="pending_verification"),
        _event(
            "v1",
            "verified",
            "c",
            "2026-09-24T10:01:00Z",
            outcome="failed",
            evidence={"kind": "test_run", "ref": "pytest t.py"},
        ),
    ]
    state = P.project(events)
    assert state.get("c").status is LifecycleStatus.CONTRADICTED
    with pytest.raises(E.LedgerError) as exc:
        P.project(
            events
            + [
                _event(
                    "v2",
                    "verified",
                    "c",
                    "2026-09-24T10:02:00Z",
                    outcome="passed",
                    evidence={"kind": "test_run", "ref": "pytest t.py"},
                )
            ]
        )
    assert exc.value.code in ("verification_conflict", "invalid_transition")


def test_dependencies_reference_stable_ids():
    state = P.project(S.load_events(EVENTS_PATH))
    assert state.get("obligation-001").depends_on == ("verification-001",)
    assert state.get("obligation-002").depends_on == ("verification-004",)


def test_unblock_refused_while_dependency_unmet():
    events = [
        _created("dep", kind="pending_verification"),
        _created("task"),
        _event(
            "r1",
            "relationship_added",
            "task",
            "2026-09-24T10:01:00Z",
            relationship={"type": "depends_on", "source_id": "task", "target_id": "dep"},
        ),
        _event("u1", "unblocked", "task", "2026-09-24T10:02:00Z"),
    ]
    with pytest.raises(E.LedgerError) as exc:
        P.project(events)
    assert exc.value.code == "dependency_unmet"
    assert P.project(events[:3]).get("task").status is LifecycleStatus.BLOCKED


# --- fixtures ---------------------------------------------------------------------


def test_fixture_replay_produces_expected_state():
    state = P.project(S.load_events(EVENTS_PATH))
    truth = _truth()
    assert {item.item.item_id for item in state.items} == set(truth)
    for item in state.items:
        want = truth[item.item.item_id]
        assert item.status.value == want["status"], item.item.item_id
        assert item.verification.value == want["verification"], item.item.item_id
        if "authority" in want:
            assert item.item.authority.value == want["authority"]
        if "superseded_by" in want:
            assert item.superseded_by == want["superseded_by"]
        if "contradicted_by" in want:
            assert item.contradicted_by == want["contradicted_by"]
        if "depends_on" in want:
            assert list(item.depends_on) == want["depends_on"]
        for ref in want.get("evidence_refs", []):
            assert any(e.get("ref") == ref for e in item.evidence), item.item.item_id
    assert len(state.relationships) == 6


def test_fixture_events_carry_no_evaluator_truth():
    blob = EVENTS_PATH.read_text(encoding="utf-8").lower()
    for token in ("oracle", "expected", "truth", "eval_class", "distractor", "harmful"):
        assert token not in blob, token
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence_class"] == "synthetic"
    assert manifest["event_count"] == 24
    assert manifest["item_count"] == 13


def test_hidden_truth_never_enters_runtime_state():
    import project_context.ledger as ledger_pkg

    root = Path(ledger_pkg.__file__).parent
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in ("oracle", "eval_class", "DISTRACTOR", "HARMFUL", "truth.json"):
            assert token not in text, (path.name, token)


# --- store --------------------------------------------------------------------------


def test_store_append_and_load_round_trip(tmp_path):
    path = tmp_path / "ledger.jsonl"
    event = _created("a")
    S.append_event(path, event)
    S.append_event(path, _event("b1", "blocked", "a", "2026-09-24T10:01:00Z", reason="w"))
    loaded = S.load_events(path)
    assert [e.event_id for e in loaded] == ["create-a", "b1"]
    assert P.project(loaded).get("a").status is LifecycleStatus.BLOCKED


def test_store_rejects_duplicates_and_corruption(tmp_path):
    path = tmp_path / "ledger.jsonl"
    S.append_event(path, _created("a"))
    S.append_event(path, _created("a"))
    with pytest.raises(E.LedgerError) as exc:
        S.load_events(path)
    assert exc.value.code == "duplicate_event"
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(E.LedgerError):
        S.load_events(path)
    with pytest.raises(E.LedgerError) as exc:
        S.load_events(tmp_path / "missing.jsonl")
    assert exc.value.code == "broken_reference"


def test_live_store_defaults_to_git_ignored_local_path():
    assert str(S.LIVE_STORE_DIR).startswith(".local")
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    assert ".local/" in gitignore


# --- CLI ------------------------------------------------------------------------------


def test_cli_ledger_commands(capsys):
    assert cli_main(["ledger", "inspect", "ledger-v1"]) == 0
    out = capsys.readouterr().out
    assert "[SYNTHETIC]" in out
    assert "superseded_by=decision-002" in out
    assert "truth" not in out.lower()
    assert cli_main(["ledger", "history", "ledger-v1", "claim-001"]) == 0
    assert "evt-015" in capsys.readouterr().out
    assert cli_main(["ledger", "validate", "ledger-v1"]) == 0
    assert "ledger valid" in capsys.readouterr().out
    assert cli_main(["ledger", "replay", "ledger-v1"]) == 0
    assert "state digest" in capsys.readouterr().out
    assert cli_main(["ledger", "inspect", "nope"]) == 2
    assert cli_main(["ledger", "history", "ledger-v1", "ghost"]) == 2


def test_cli_ledger_inspect_deterministic(capsys):
    assert cli_main(["ledger", "inspect", "ledger-v1"]) == 0
    first = capsys.readouterr().out
    assert cli_main(["ledger", "inspect", "ledger-v1"]) == 0
    assert capsys.readouterr().out == first


# --- boundaries -------------------------------------------------------------------------


def test_no_forbidden_imports_in_ledger():
    import project_context.ledger as ledger_pkg

    denied = {
        "os",
        "sys",
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "http",
        "time",
        "datetime",
        "random",
        "openai",
        "anthropic",
        "torch",
        "numpy",
    }
    pattern = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_]+)", re.M)
    root = Path(ledger_pkg.__file__).parent
    for path in root.glob("*.py"):
        if path.name == "__init__.py":
            continue
        found = set(pattern.findall(path.read_text(encoding="utf-8")))
        assert not (found & denied), f"{path}: {found & denied}"
        assert "project_context.evaluation" not in path.read_text(encoding="utf-8"), path


def test_ledger_import_direction():
    import ast

    import project_context

    root = Path(project_context.__file__).parent

    def imports_of(package):
        found = set()
        for path in (root / package).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module:
                    found.add(node.module)
                elif isinstance(node, ast.Import):
                    found.update(a.name for a in node.names)
        return found

    ledger_imports = imports_of("ledger")
    assert {m for m in ledger_imports if "project_context" in m} <= {
        "project_context.ledger.events",
        "project_context.ledger.lifecycle",
        "project_context.ledger.projection",
        "project_context.ledger.records",
        "project_context.ledger.relationships",
        "project_context.ledger.store",
    }
    for package in ("compiler", "opencode", "evaluation", "readers", "behavior"):
        target = root / package
        if not target.is_dir():
            continue
        for path in target.rglob("*.py"):
            assert "project_context.ledger" not in path.read_text(encoding="utf-8"), path


def test_compiler_has_no_ledger_privilege():
    import project_context

    root = Path(project_context.__file__).parent
    for path in (root / "compiler").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "ledger" not in text.lower(), path
        assert "always_include" not in text, path


def test_opencode_capture_has_no_ledger_presence():
    import project_context

    root = Path(project_context.__file__).parent
    for path in (root / "opencode").rglob("*.py"):
        assert "ledger" not in path.read_text(encoding="utf-8").lower(), path
    ts_root = Path("integrations") / "opencode" / "src"
    if ts_root.is_dir():
        for path in ts_root.rglob("*.ts"):
            assert "ledger" not in path.read_text(encoding="utf-8").lower(), path
