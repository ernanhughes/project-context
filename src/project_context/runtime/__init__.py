"""Explicit context runtime injection (Stage 6D): render, inject, reconcile.

Boundary (pinned by tests):

- the runtime consumes only compiler-selected bundles, never ledger or
  activation state directly (no bypass around the compiler);
- rendering is pure and deterministic; injection is explicit and
  opt-in; observation stays with the existing read-only observer;
- intended injection and observed invocation are recorded separately
  and reconciled deterministically;
- no model calls, no network, no wall-clock reads, no randomness;
- the runtime never imports ledger, activation, providers, readers,
  behaviour, evaluation, or the OpenCode integration.
"""

from project_context.runtime.inject import RUNTIME_MODE, inject
from project_context.runtime.model import (
    INJECTION_LOCATION,
    InjectionReceipt,
    ReconciliationResult,
    RenderedBlock,
    RenderPolicy,
    RuntimeError,
)
from project_context.runtime.reconcile import reconcile
from project_context.runtime.render import render_bundle

__all__ = [
    "INJECTION_LOCATION",
    "RUNTIME_MODE",
    "InjectionReceipt",
    "ReconciliationResult",
    "RenderPolicy",
    "RenderedBlock",
    "RuntimeError",
    "inject",
    "reconcile",
    "render_bundle",
]
