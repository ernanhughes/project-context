"""Compatibility shim: the canonical compiler lives in the external
`context_compiler` package (project-context-compiler).

DEPRECATED as an implementation home. This module contains no
compiler logic; it re-exports the canonical records so existing
`project_context.compiler.*` imports keep working during migration.
New code should import `context_compiler` directly.
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
from context_compiler.policy import (
    COMPILER_POLICY_SCHEMA,
    DEFAULT_POLICY_VERSION,
    CompilerPolicy,
    default_policy,
)

__all__ = [
    "COMPILE_FAILURE_SCHEMA",
    "COMPILER_POLICY_SCHEMA",
    "COMPILATION_RESULT_SCHEMA",
    "CONTEXT_CANDIDATE_SCHEMA",
    "CONTEXT_REQUEST_SCHEMA",
    "DECISION_TRACE_SCHEMA",
    "CompileFailure",
    "CompilerPolicy",
    "CompilationResult",
    "ContextCandidate",
    "ContextRequest",
    "DecisionTrace",
    "DEFAULT_POLICY_VERSION",
    "FailureReason",
    "RequirementClass",
    "TraceDecision",
    "TraceEntry",
    "default_policy",
]
