"""Compatibility shim for the compiler policy record.

Canonical implementation: `context_compiler.policy` (external
project-context-compiler package). No logic here.
"""

from context_compiler.policy import (
    COMPILER_POLICY_SCHEMA,
    DEFAULT_POLICY_VERSION,
    CompilerPolicy,
    default_policy,
)

__all__ = [
    "COMPILER_POLICY_SCHEMA",
    "DEFAULT_POLICY_VERSION",
    "CompilerPolicy",
    "default_policy",
]
