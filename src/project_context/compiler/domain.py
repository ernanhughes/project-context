"""Compatibility shim for compiler domain records.

Canonical implementation: `context_compiler.domain` (external
project-context-compiler package). No logic here.
"""

from context_compiler.domain import (
    COMPILATION_RESULT_SCHEMA,
    COMPILE_FAILURE_SCHEMA,
    CONTEXT_CANDIDATE_SCHEMA,
    CONTEXT_REQUEST_SCHEMA,
    DECISION_TRACE_SCHEMA,
    CompilationResult,
    CompileFailure,
    ContextCandidate,
    ContextRequest,
    DecisionTrace,
    FailureReason,
    RequirementClass,
    TraceDecision,
    TraceEntry,
)

__all__ = [
    "COMPILATION_RESULT_SCHEMA",
    "COMPILE_FAILURE_SCHEMA",
    "CONTEXT_CANDIDATE_SCHEMA",
    "CONTEXT_REQUEST_SCHEMA",
    "DECISION_TRACE_SCHEMA",
    "CompilationResult",
    "CompileFailure",
    "ContextCandidate",
    "ContextRequest",
    "DecisionTrace",
    "FailureReason",
    "RequirementClass",
    "TraceDecision",
    "TraceEntry",
]
