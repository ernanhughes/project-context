"""Strict loaders for compiler-behavior-v1 fixtures. task.json is
reader-visible; truth.json and interventions.json are evaluator-only and
must never enter a reader payload (a leak scan test pins this)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TASK_KEYS = frozenset(
    {
        "task_id",
        "family",
        "prompt",
        "actions",
        "reason_options",
        "grader_version",
        "source_compiler_fixture",
        "borrowed_bundles",
        "calibration_only",
    }
)

TRUTH_KEYS = frozenset(
    {
        "correct_action",
        "harmful_actions",
        "expected_value",
        "decisive_unit",
        "wrong_unit",
        "token_matched_unit",
        "notes",
    }
)

INTERVENTION_KEYS = frozenset({"interventions"})

INTERVENTION_FIELDS = frozenset({"intervention_id", "kind", "remove_ids", "add_records"})

ADD_RECORD_FIELDS = frozenset(
    {
        "candidate_id",
        "content_identity",
        "representation_id",
        "content",
        "token_count",
        "source_kind",
        "kind",
    }
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _strict(raw: dict, allowed: frozenset, path: Path) -> dict:
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown keys {sorted(unknown)} in {path}")
    return raw


def load_task(path: Path) -> dict:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError(f"bad task file: {path}")
    return _strict(raw, TASK_KEYS, path)


def load_truth(path: Path) -> dict:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError(f"bad truth file: {path}")
    return _strict(raw, TRUTH_KEYS, path)


def load_interventions(path: Path) -> dict:
    raw = _read_json(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("interventions"), list):
        raise ValueError(f"bad interventions file: {path}")
    _strict(raw, INTERVENTION_KEYS, path)
    for entry in raw["interventions"]:
        _strict(entry, INTERVENTION_FIELDS, path)
        for record in entry.get("add_records", []):
            _strict(record, ADD_RECORD_FIELDS, path)
    return raw


def load_manifest(path: Path) -> dict:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError(f"bad behavior manifest: {path}")
    return raw


def load_behavior_set(root: Path) -> dict[str, dict[str, Path]]:
    """Map behavior fixture name -> task/truth/interventions paths."""
    found: dict[str, dict[str, Path]] = {}
    for path in sorted(root.glob("*/task.json")):
        name = path.parent.name
        truth_path = path.parent / "truth.json"
        interventions_path = path.parent / "interventions.json"
        if not truth_path.is_file() or not interventions_path.is_file():
            raise ValueError(f"behavior fixture {name}: missing truth/interventions")
        found[name] = {
            "task": path,
            "truth": truth_path,
            "interventions": interventions_path,
        }
    return found
