"""Stage 4 behavioural records. One minimal linkage/action record plus
existing domain records (ModelInvocation, EvaluationObservation,
RunManifest); no new hierarchies."""

from project_context.behavior.domain import (
    BEHAVIOR_RECORD_SCHEMA,
    BehaviorRecord,
)

__all__ = ["BEHAVIOR_RECORD_SCHEMA", "BehaviorRecord"]
