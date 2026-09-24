"""Ledger-to-compiler candidate adapter (Stage 6C): ordinary candidates, no privilege.

Boundary (pinned by tests):

- only Stage 6B ACTIVE items become candidates; DORMANT, INELIGIBLE and
  UNKNOWN produce receipts with no candidate;
- no MANDATORY/REQUIRED bands, no per-item relevance scoring, no ranking;
- standing derives from ledger authority metadata, never from
  ledger source; the compiler treats adapted candidates through its
  ordinary policy;
- no model calls, no network, no wall-clock reads, no randomness;
- the compiler never imports this package (one-way dependency:
  ledger -> activation -> adapter -> compiler domain interface).
"""

from project_context.ledger_adapter.adapter import (
    LedgerAdapterReceipt,
    adapt,
    adapt_case,
)

__all__ = ["LedgerAdapterReceipt", "adapt", "adapt_case"]
