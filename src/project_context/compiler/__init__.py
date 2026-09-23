"""Stage 3 deterministic synthetic Context Compiler.

Book mapping: Chapter 22 ("Assemble for the Task"). This package turns the
frozen compiler contract into executable machinery over synthetic,
versioned candidates. No models, no network, no retrieval, no memory
system, no tool execution. Every decision is deterministic and traced.

Layout:

```text
compiler/
  domain.py    records: candidate, request, policy, trace, failure, result
  policy.py    CompilerPolicy defaults and JSON loading
  engine.py    compile_context: eligibility, alternatives, deps, budget, render
  fixtures.py  strict JSON loaders for compiler-v1 fixture files
```

Purity rule: engine.py imports only stdlib dataclasses/typing/enum plus
sibling domain/policy modules and existing domain/telemetry records. It
never reads files, clocks, randomness, network, or models. A source scan
test pins this.
"""

from project_context.compiler.domain import (
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
    RequirementClass,
    TraceDecision,
    TraceEntry,
)
from project_context.compiler.policy import (
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
    "RequirementClass",
    "TraceDecision",
    "TraceEntry",
    "default_policy",
]
