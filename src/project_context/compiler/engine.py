"""Compatibility shim for the deterministic compiler engine.

Canonical implementation: `context_compiler.engine` (external
project-context-compiler package). No logic here. Private helpers
(`_closure_ids`, `_decoration_tokens`, ...) are re-exported because
evaluation and behavior modules use them; they remain
implementation details of the canonical engine.
"""

from context_compiler.engine import (
    _SEPARATOR_TOKENS,
    BAND_ORDER,
    SEPARATOR,
    CompileOutput,
    _closure_ids,
    _decoration_tokens,
    _depends_on_id,
    compile_context,
    eligibility,
    header_tokens,
)

__all__ = [
    "SEPARATOR",
    "BAND_ORDER",
    "CompileOutput",
    "_closure_ids",
    "_decoration_tokens",
    "_depends_on_id",
    "_SEPARATOR_TOKENS",
    "compile_context",
    "eligibility",
    "header_tokens",
]
