"""Context Activation (Stage 6B): which valid ledger items have a reason to wake up.

Boundary (pinned by tests):

- activation means potentially relevant now; it never means admitted;
- no budgeting, representation choice, ordering, or rendering;
- no ContextCandidate conversion and no compiler modification;
- no model calls, no network, no wall-clock reads, no randomness;
- unresolved never implies relevant; UNKNOWN never defaults to ACTIVE;
- activation code never imports compiler, evaluation, providers, readers,
  behaviour, or fixture truth.
"""

from project_context.activation.engine import activate
from project_context.activation.model import (
    ActivationDecision,
    ActivationMode,
    ActivationPolicy,
    ActivationRequest,
    ActivationResult,
    ActivationState,
)

__all__ = [
    "ActivationDecision",
    "ActivationMode",
    "ActivationPolicy",
    "ActivationRequest",
    "ActivationResult",
    "ActivationState",
    "activate",
]
