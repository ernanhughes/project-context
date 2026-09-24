"""The F1 session index: one row per session, written when the session ends.

It exists before the first session so that inclusion is decided by rules, never by how a
session turned out. The index has two faces:

* the **local index** (git-ignored) holds everything, including the private index that
  links a raw capture to its derivative by digest;
* the **public projection** holds ordinals, coarse structure and states only: no session
  identity, no timestamps, no digests.

Three kinds of index exist and cannot be mixed. An ``ecological`` index accepts only
genuine sessions. A ``dry_run`` index accepts only synthetic ones, and a ``calibration``
index only the deliberate tool-testing session used to check the instrument. Neither can be
loaded as the corpus, and the ecological index refuses both. A pipeline test or a calibration
session therefore cannot enter the ecological corpus by accident.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_context.corpus.strata import STRATA, UNCLASSIFIED

# Persisted schema identifier. The string is frozen: index files already
# written name it, so only the constant name follows the rename.
SESSION_INDEX_SCHEMA = "project_context.f1_ledger.v1"
ECOLOGICAL = "ecological"
DRY_RUN = "dry_run"
CALIBRATION = "calibration"

# Reserved prefixes: anything carrying one is synthetic, whatever else it claims.
SYNTHETIC_MARKERS = ("synthetic-", "dry-run-")
CALIBRATION_MARKERS = ("calibration-",)
NON_CORPUS_MARKERS = SYNTHETIC_MARKERS + CALIBRATION_MARKERS

# Sidecar vocabulary (closed). Free text is not accepted anywhere.
LANGUAGE_FAMILIES = (
    "python",
    "typescript",
    "javascript",
    "go",
    "rust",
    "java",
    "csharp",
    "cpp",
    "other",
)
SIZE_BANDS = ("small", "medium", "large")
TASK_TYPES = ("question", "bugfix", "feature", "refactor", "debug", "investigation", "other")
OUTCOMES = ("tests_passing", "build_passing", "change_accepted", "abandoned", "not_applicable")
SIDECAR_KEYS = {
    "language_family": LANGUAGE_FAMILIES,
    "size_band": SIZE_BANDS,
    "task_type": TASK_TYPES,
    "outcome": OUTCOMES,
    "has_tests": (True, False),
    "project_instructions": (True, False),
    "scope_crossover": (True, False),
    "authority_conflict": (True, False),
    "other_context_plugins": (True, False),
}

# From the preregistration. A session is excluded only for one of these.
EXCLUSION_REASONS = (
    "capture_incomplete",
    "secret_or_identifier_hit",
    "repository_not_on_allow_list",
    "tool_testing_session",
    "author_withdrawal",
    "version_block_not_validated",
    "fewer_than_one_primary_request",
    "instrument_reconciliation_failure",
    "privacy_gate_failure",
)

PRIVACY_STATES = ("raw_local", "scanned_clean", "scan_hit")
SANITISATION_STATES = ("none", "derived", "gate_clean", "approved_public")

STOP_MIN_TOTAL = 24
STOP_MAX_TOTAL = 30
STOP_MIN_PER_STRATUM = 3
STOP_MAX_PRIMARY_SAME = 6
STOP_MAX_WEEKS = 10


class SessionIndexError(ValueError):
    pass


def validate_sidecar(sidecar: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, value in sidecar.items():
        if key not in SIDECAR_KEYS:
            errors.append(f"sidecar key {key!r} is not in the closed vocabulary")
        elif value not in SIDECAR_KEYS[key] or (
            isinstance(value, bool) != isinstance(SIDECAR_KEYS[key][0], bool)
        ):
            errors.append(f"sidecar {key} has a value outside the closed vocabulary")
    return errors


@dataclass
class Entry:
    ordinal: int
    session_key: str  # local only
    captured_at: str  # local only, ISO 8601 UTC
    campaign_week: int
    primary_stratum: str
    tags: list[str]
    satisfied_basis: dict[str, str]
    language_family: str | None
    size_band: str | None
    has_tests: bool | None
    task_type: str | None
    outcome: str | None
    readers: list[str]  # "provider/model" identities seen in the session
    turn_count: int
    tools_available: int | str
    complete: bool
    incomplete_reasons: list[str]
    privacy_state: str
    sanitisation_state: str
    derivative_present: bool
    shape_cards: list[str]
    other_context_plugins: bool | None = None  # declared: other plugins that can change context
    withdrawn: bool = False
    excluded: bool = False
    exclusion_reason: str | None = None
    evidence_class: str = ECOLOGICAL
    link: dict[str, str] = field(default_factory=dict)  # local only: raw and derivative digests


PUBLIC_FIELDS = (
    "ordinal",
    "campaign_week",
    "primary_stratum",
    "tags",
    "language_family",
    "size_band",
    "has_tests",
    "task_type",
    "outcome",
    "readers",
    "turn_count",
    "tools_available",
    "complete",
    "incomplete_reasons",
    "privacy_state",
    "sanitisation_state",
    "derivative_present",
    "shape_cards",
    "withdrawn",
    "excluded",
    "exclusion_reason",
    "other_context_plugins",
)


def session_class(session_key: str, evidence_class: str) -> str:
    """ecological, synthetic or calibration. Anything that is not plainly ecological is not."""
    if evidence_class == CALIBRATION or session_key.startswith(CALIBRATION_MARKERS):
        return CALIBRATION
    if evidence_class != ECOLOGICAL or session_key.startswith(SYNTHETIC_MARKERS):
        return "synthetic"
    return ECOLOGICAL


def is_synthetic(session_key: str, evidence_class: str) -> bool:
    return session_class(session_key, evidence_class) != ECOLOGICAL


class SessionIndex:
    def __init__(self, path: Path, kind: str, campaign_id: str, created_at: str):
        if kind not in (ECOLOGICAL, DRY_RUN, CALIBRATION):
            raise SessionIndexError(f"unknown session-index kind {kind!r}")
        self.path, self.kind, self.campaign_id, self.created_at = (
            path,
            kind,
            campaign_id,
            created_at,
        )
        self.entries: list[Entry] = []

    # -- persistence
    @classmethod
    def create(
        cls, path: Path, kind: str, campaign_id: str, now: str | None = None
    ) -> SessionIndex:
        if path.exists():
            raise SessionIndexError(f"{path.name} already exists; an index is created once")
        index = cls(path, kind, campaign_id, now or datetime.now(timezone.utc).isoformat())
        index.save()
        return index

    @classmethod
    def load(cls, path: Path, expected_kind: str) -> SessionIndex:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != SESSION_INDEX_SCHEMA:
            raise SessionIndexError("not an F1 session index")
        if data["kind"] != expected_kind:
            raise SessionIndexError(f"index is {data['kind']!r}, expected {expected_kind!r}")
        index = cls(path, data["kind"], data["campaign_id"], data["created_at"])
        index.entries = [Entry(**row) for row in data["entries"]]
        return index

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "schema": SESSION_INDEX_SCHEMA,
            "kind": self.kind,
            "campaign_id": self.campaign_id,
            "created_at": self.created_at,
            "entries": [asdict(e) for e in self.entries],
        }
        self.path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # -- writing
    def add(self, entry: Entry) -> Entry:
        klass = session_class(entry.session_key, entry.evidence_class)
        if self.kind == ECOLOGICAL and klass != ECOLOGICAL:
            raise SessionIndexError(
                "synthetic, dry-run or calibration material is refused by the ecological index"
            )
        if self.kind == DRY_RUN and klass != "synthetic":
            raise SessionIndexError("only synthetic material may enter a dry-run index")
        if self.kind == CALIBRATION and klass != CALIBRATION:
            raise SessionIndexError("only calibration sessions may enter a calibration index")
        if any(e.session_key == entry.session_key for e in self.entries):
            raise SessionIndexError("session already in the index")
        if entry.exclusion_reason is not None and entry.exclusion_reason not in (EXCLUSION_REASONS):
            raise SessionIndexError(
                f"exclusion reason {entry.exclusion_reason!r} is not on the list"
            )
        if entry.primary_stratum not in (*STRATA, UNCLASSIFIED):
            raise SessionIndexError("unknown stratum")
        entry.ordinal = len(self.entries) + 1
        self.entries.append(entry)
        self.save()
        return entry

    def _get(self, ordinal: int) -> Entry:
        return next(e for e in self.entries if e.ordinal == ordinal)

    def withdraw(self, ordinal: int) -> None:
        """Author withdrawal, at any time and unread. Recorded, never deleted."""
        entry = self._get(ordinal)
        entry.withdrawn, entry.excluded, entry.exclusion_reason = True, True, "author_withdrawal"
        self.save()

    def exclude(self, ordinal: int, reason: str) -> None:
        if reason not in EXCLUSION_REASONS:
            raise SessionIndexError(f"exclusion reason {reason!r} is not on the list")
        entry = self._get(ordinal)
        entry.excluded, entry.exclusion_reason = True, reason
        self.save()

    # -- reading
    def usable(self) -> list[Entry]:
        return [e for e in self.entries if not e.excluded and e.complete and e.derivative_present]

    def genuine_count(self) -> int:
        return len([e for e in self.entries if e.evidence_class == ECOLOGICAL])

    def stopping_status(self, weeks_elapsed: float) -> dict[str, Any]:
        """Evaluate the preregistered stopping rule. Reads the index; changes nothing."""
        usable = self.usable()
        primary: dict[str, int] = {}
        anywhere: dict[str, int] = {}
        for e in usable:
            primary[e.primary_stratum] = primary.get(e.primary_stratum, 0) + 1
            for s in {e.primary_stratum, *e.tags}:
                anywhere[s] = anywhere.get(s, 0) + 1
        achievable = sorted(s for s in STRATA if anywhere.get(s, 0) > 0)
        short = [s for s in achievable if anywhere[s] < STOP_MIN_PER_STRATUM]
        rule_1 = len(usable) >= STOP_MIN_TOTAL and not short
        rule_2 = len(usable) >= STOP_MAX_TOTAL
        rule_3 = weeks_elapsed >= STOP_MAX_WEEKS
        return {
            "usable": len(usable),
            "achievable_strata": achievable,
            "strata_below_minimum": short,
            # Absence is only meaningful once something has been observed.
            "naturally_absent": sorted(set(STRATA) - set(achievable)) if usable else [],
            "assessable": bool(usable),
            "primary_over_cap": sorted(s for s, n in primary.items() if n > STOP_MAX_PRIMARY_SAME),
            "stop": rule_1 or rule_2 or rule_3,
            "because": [
                name
                for name, hit in (
                    ("every achievable stratum has 3 and there are 24", rule_1),
                    ("30 usable sessions", rule_2),
                    ("ten calendar weeks", rule_3),
                )
                if hit
            ],
        }

    def public_projection(self) -> dict[str, Any]:
        """What may be published about the index, before any approval step.

        Ordinals and coarse structure only. Session identity, capture time and every digest
        stay local.
        """
        rows = [{k: getattr(e, k) for k in PUBLIC_FIELDS} for e in self.entries]
        return {
            "schema": SESSION_INDEX_SCHEMA + ".public",
            "kind": self.kind,
            "sessions_recorded": len(rows),
            "entries": rows,
        }


def campaign_week(first_capture: str, this_capture: str) -> int:
    a = datetime.fromisoformat(first_capture.replace("Z", "+00:00"))
    b = datetime.fromisoformat(this_capture.replace("Z", "+00:00"))
    return max(0, (b - a).days // 7) + 1
