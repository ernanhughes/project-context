"""The F1 capture pipeline, stage by stage.

    live capture -> raw capture -> local validation -> secret/privacy scan
        -> structural extraction -> sanitised publishable derivative
        -> aggregate measurements -> shape card

Stages one and two happen in the harness adapter and land in a local, git-ignored spool.
Everything from local validation onwards is `process_session`. It never writes raw text
anywhere; it returns numbers, states and cards, and records the outcome in the ledger.

A session that fails a stage is excluded with a reason from the closed list and is not
repaired. A derivative that fails the gate is blocked, not edited.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from project_context.corpus import ledger as ledger_mod
from project_context.corpus.completeness import UNOBSERVED, Completeness, assess_session
from project_context.corpus.f1_analysis import analyse_session, dumps, reconcile
from project_context.corpus.ledger import Entry, Ledger, campaign_week, validate_sidecar
from project_context.corpus.privacy import GateResult, ScanReport, gate, scan_raw
from project_context.corpus.shapecards import Card, derive_cards, validate_card
from project_context.corpus.strata import Assignment, assign

STAGES = (
    "local_validation",
    "privacy_scan",
    "structural_extraction",
    "reconciliation",
    "publication_gate",
    "shape_cards",
    "ledger",
)


@dataclass
class Outcome:
    """What `process_session` did. Holds no raw text."""

    stage_reached: str
    excluded: bool
    exclusion_reason: str | None
    completeness: Completeness
    scan: ScanReport | None = None
    l1: dict[str, Any] | None = None
    cards: list[Card] = field(default_factory=list)
    assignment: Assignment | None = None
    gate: GateResult | None = None
    ledger_ordinal: int | None = None


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _readers(records: list[dict[str, Any]]) -> list[str]:
    seen = {
        f"{r['model'].get('provider_id')}/{r['model'].get('id')}"
        for r in records
        if isinstance(r.get("model"), dict)
    }
    return sorted(seen)


def process_session(
    records: list[dict[str, Any]],
    *,
    session_key: str,
    sidecar: dict[str, Any],
    ledger: Ledger,
    first_capture_at: str | None = None,
    skipped_lines: int = 0,
    sensitive_terms: tuple[str, ...] = (),
    force_derivative: bool = False,
) -> Outcome:
    """Run one captured session through every stage and record it.

    `force_derivative` builds and gates the derivative even for a session the scan excluded.
    It exists for the privacy dry run, which must show that the derivative is clean whether or
    not the scanner noticed anything. It never changes what the ledger records.
    """
    problems = validate_sidecar(sidecar)
    if problems:
        raise ledger_mod.LedgerError(f"sidecar rejected: {problems}")

    completeness = assess_session(records, skipped_lines)
    captured = min((str(r.get("captured_at", "")) for r in records), default="")

    def record(
        outcome: Outcome,
        *,
        privacy: str,
        sanitisation: str,
        derivative: bool,
    ) -> Outcome:
        l1 = outcome.l1 or {}
        session = l1.get("session", {})
        assignment = outcome.assignment
        entry = Entry(
            ordinal=0,
            session_key=session_key,
            captured_at=captured,
            campaign_week=campaign_week(first_capture_at or captured, captured) if captured else 1,
            primary_stratum=assignment.primary if assignment else ledger_mod.UNCLASSIFIED,
            tags=list(assignment.tags) if assignment else [],
            satisfied_basis=dict(assignment.basis) if assignment else {},
            language_family=sidecar.get("language_family"),
            size_band=sidecar.get("size_band"),
            has_tests=sidecar.get("has_tests"),
            task_type=sidecar.get("task_type"),
            outcome=sidecar.get("outcome"),
            readers=_readers(records),
            turn_count=completeness.primary_requests,
            tools_available=session.get("tools_available_first_request", UNOBSERVED),
            complete=completeness.complete,
            incomplete_reasons=list(completeness.reasons),
            privacy_state=privacy,
            sanitisation_state=sanitisation,
            derivative_present=derivative,
            shape_cards=sorted({c.shape for c in outcome.cards}),
            excluded=outcome.excluded,
            exclusion_reason=outcome.exclusion_reason,
            evidence_class=ledger_mod.ECOLOGICAL
            if not session_key.startswith(ledger_mod.SYNTHETIC_MARKERS)
            else "synthetic",
            link={"raw": _digest(records), "derivative": _digest(l1)} if outcome.l1 else {},
        )
        outcome.ledger_ordinal = ledger.add(entry).ordinal
        outcome.stage_reached = "ledger"
        return outcome

    # 1. local validation
    if not completeness.complete:
        reason = (
            "fewer_than_one_primary_request"
            if "no_primary_request" in completeness.reasons
            else "capture_incomplete"
        )
        out = Outcome("local_validation", True, reason, completeness)
        return record(out, privacy="raw_local", sanitisation="none", derivative=False)

    # 2. privacy scan
    scan = scan_raw(records, sensitive_terms)
    privacy = "scan_hit" if scan.excludes_session else "scanned_clean"
    out = Outcome("privacy_scan", False, None, completeness, scan=scan)
    if scan.excludes_session:
        out.excluded, out.exclusion_reason = True, "secret_or_identifier_hit"
        if not force_derivative:
            return record(out, privacy=privacy, sanitisation="none", derivative=False)

    # 3. structural extraction
    l1 = analyse_session(records, declared=sidecar)
    out.l1, out.stage_reached = l1, "structural_extraction"

    # 4. reconciliation (instrument control)
    if reconcile(records, l1):
        out.excluded, out.exclusion_reason = True, "instrument_reconciliation_failure"
        out.stage_reached = "reconciliation"
        return record(out, privacy=privacy, sanitisation="derived", derivative=False)

    # 5. publication gate: a blocked derivative is not published, and is not repaired
    out.gate = gate(l1, records, scan)
    out.stage_reached = "publication_gate"
    if not out.gate.content_clean:
        out.excluded, out.exclusion_reason = True, "privacy_gate_failure"
        return record(out, privacy=privacy, sanitisation="derived", derivative=False)

    # 6. shape cards and stratum
    out.cards = derive_cards(l1)
    bad = [e for c in out.cards for e in validate_card(c.to_dict())]
    if bad:
        raise ValueError(f"shape card failed its own schema: {bad}")
    out.assignment = assign(l1["session"], sidecar)
    out.stage_reached = "shape_cards"

    return record(out, privacy=privacy, sanitisation="gate_clean", derivative=True)


def derivative_bytes(outcome: Outcome) -> bytes:
    """The canonical publishable bytes for a session's derivative. Deterministic."""
    if outcome.l1 is None:
        raise ValueError("no derivative was built")
    return dumps(outcome.l1).encode("ascii")
