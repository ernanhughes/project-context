"""Deterministic probe scoring: normalised exact match. No model calls."""

from __future__ import annotations

import re
import unicodedata

from project_context.domain.evaluation import EvaluationObservation, Verdict
from project_context.fixtures.base import Probe

EVALUATOR_ID = "project_context.scoring.exact_match.v1"


def normalise(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    folded = re.sub(r"\s+", " ", folded).strip()
    return folded.strip(".")


def score_probe(
    probe: Probe,
    candidate_answer: str,
    *,
    observation_id: str,
    target_id: str,
    created_at: str,
) -> EvaluationObservation:
    """PASS iff normalised candidate equals normalised expectation."""
    match = normalise(candidate_answer) == normalise(probe.expected)
    return EvaluationObservation(
        id=observation_id,
        target_type="probe",
        target_id=target_id,
        metric=f"probe:{probe.id}",
        value=candidate_answer,
        verdict=Verdict.PASS if match else Verdict.FAIL,
        evidence=(
            f"candidate normalised to {normalise(candidate_answer)!r}; "
            f"expected normalised to {normalise(probe.expected)!r}"
        ),
        evaluator=EVALUATOR_ID,
        created_at=created_at,
    )
