"""Strict loaders for compiler-v1 fixture JSON. Unknown keys are rejected
so malformed experiments fail loudly (invalid configuration) rather than
silently changing meaning. Evaluator truth files (`*.truth.json`) are
never touched here; only the hidden-truth loader may read them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_context.compiler.domain import ContextCandidate, ContextRequest

CANDIDATE_KEYS = frozenset(
    {
        "candidate_id",
        "content_identity",
        "representation_id",
        "form_rank",
        "min_rank",
        "source_kind",
        "source_ref",
        "kind",
        "content",
        "token_count",
        "token_source",
        "requirement",
        "order_role",
        "scope_eligible",
        "scope_reason",
        "freshness_eligible",
        "freshness_reason",
        "authority_eligible",
        "authority_reason",
        "depends_on",
        "group_id",
        "group_required",
        "coverage_keys",
        "relevance",
        "is_default_form",
    }
)

REQUEST_KEYS = frozenset(
    {
        "request_id",
        "task_id",
        "usable_token_budget",
        "created_at",
        "active_scope",
        "required_ids",
        "policy_version",
    }
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_candidate_file(path: Path) -> list[ContextCandidate]:
    """Load one `*.candidates.json` file: {"candidates": [...]}."""
    raw = _read_json(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("candidates"), list):
        raise ValueError(f"bad candidate file (need {{'candidates': [...]}}): {path}")
    loaded = []
    for record in raw["candidates"]:
        unknown = set(record) - CANDIDATE_KEYS
        if unknown:
            raise ValueError(f"unknown candidate keys {sorted(unknown)} in {path}")
        candidate = ContextCandidate.from_dict(record)
        if not isinstance(candidate.token_count, int) or candidate.token_count < 0:
            raise ValueError(f"invalid token_count in {path}: {candidate.candidate_id}")
        if not 0.0 <= candidate.relevance <= 1.0:
            raise ValueError(f"relevance out of range in {path}: {candidate.candidate_id}")
        loaded.append(candidate)
    return loaded


def load_request_file(path: Path) -> ContextRequest:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError(f"bad request file (need object): {path}")
    unknown = set(raw) - REQUEST_KEYS
    if unknown:
        raise ValueError(f"unknown request keys {sorted(unknown)} in {path}")
    return ContextRequest.from_dict(raw)


def load_fixture_set(root: Path) -> dict[str, dict[str, Path]]:
    """Map fixture name -> {"candidates": ..., "request": ...} paths.
    Truth files are deliberately not listed here."""
    found: dict[str, dict[str, Path]] = {}
    for path in sorted(root.glob("*.candidates.json")):
        name = path.name[: -len(".candidates.json")]
        request_path = root / f"{name}.request.json"
        if not request_path.is_file():
            raise ValueError(f"fixture {name}: missing {request_path.name}")
        found[name] = {"candidates": path, "request": request_path}
    return found
