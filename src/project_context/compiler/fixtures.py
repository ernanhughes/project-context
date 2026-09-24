"""Compatibility shim for strict fixture loaders.

Canonical implementation: `context_compiler.fixtures` (external
project-context-compiler package). No logic here.
"""

from context_compiler.fixtures import (
    CANDIDATE_KEYS,
    REQUEST_KEYS,
    load_candidate_file,
    load_fixture_set,
    load_request_file,
)

__all__ = [
    "CANDIDATE_KEYS",
    "REQUEST_KEYS",
    "load_candidate_file",
    "load_fixture_set",
    "load_request_file",
]
