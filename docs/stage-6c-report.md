# Stage 6C report — Ledger-to-Compiler Candidate Adapter

## Purpose

Bridge one narrow gap: ACTIVE ledger state becomes ordinary compiler
candidates for the unchanged Context Compiler. Stage 6C demonstrates
that the boundary works — faithful conversion, normal competition, no
privilege. It does not demonstrate utility, optimal representation, or
anything behavioural.

Design: `experiments/adapter-v1/` (frozen compatibility contract,
question, conditions, measurements, falsification). No behavioural run
is attached; nothing here is book evidence.

## Architecture

```text
Stage 6A:  events → LedgerState
Stage 6B:  LedgerState + ActivationRequest → ActivationResult
Stage 6C:  ActivationResult → ContextCandidate[] → EXISTING compiler
Stage 6D:  (future) selected bundle → explicit runtime injection
```

Dependency direction: ledger → activation → ledger_adapter →
compiler domain interface. The compiler never imports upward (pinned).

## Adapter mapping

`adapt(state, activation)` consumes Stage 6B output without
recomputing it. Only ACTIVE decisions yield candidates; everything
else yields a receipt with no candidate. Per ACTIVE item:
`candidate_id = ledger-<item>-<digest12>` over id, status,
verification, statement digest, policy id and sorted reasons
(deterministic; state changes alter it); `content_identity =
ledger-item-<item>`; content is the verbatim statement except
unverified assumptions/pending claims keep a deterministic status tag
(`[Unverified assumption]`, `[Pending verification]`), because the
render joins contents only and would otherwise flatten them into fact;
`kind` is the ledger kind (decoration only, zero admission effect);
`source_kind = "ledger"`, `source_ref = item id` (lineage, never
standing); requirement PREFERRED for user/system/project authority,
DISCRETIONARY otherwise (authority-derived, mirroring ordinary pools;
never MANDATORY/REQUIRED); one fixed relevance for all adapted
candidates (no adapter ranking; engine tie-breaks by id); order roles
instruction/task/state/evidence by kind (render order only);
eligibility flags True with reasons recording scope, verification and
authority facts; single canonical form (full, floor 0); token counts
from the existing word approximation, labelled as such; `depends_on`
remapped to co-adapted candidate ids, outsiders named in the receipt;
no coverage keys, no groups. `adapt_case` merges with an ordinary pool
sorted by candidate id.

## Authority mapping

user → PREFERRED ("user-derived directive standing"); system/project
→ PREFERRED; tool → DISCRETIONARY ("data, never directive"); agent →
DISCRETIONARY ("never user/project authority"); derived →
DISCRETIONARY. Unknown authorities cannot occur (closed enum); any
future addition maps explicitly or fails at the mapping table, never
silently promotes.

## Scope, epistemic, lifecycle, identity, provenance

Scope dimensions preserved in reasons and receipts, never inferred,
never defaulted to global. Epistemic state preserved three ways:
kind, freshness reason, and render-visible tag; verified items carry
no tag. Lifecycle enters identity (status/verification in the digest)
and eligibility (only ACTIVE arrives). Provenance is
source_kind/source_ref plus per-decision receipts answering which item
produced which candidate, why it was allowed through, and what was
kept. Full event history is deliberately not copied.

## Compiler compatibility cases

Seven synthetic cases (required_ids always empty, so everything is
earned): ledger items admitted (A); stronger ordinary candidate wins
the budget (B); valid items omitted by budget with success preserved
(C); user outranks agent by authority metadata (D); pending claim
renders marked (E); three ledger candidates convert unranked (F);
mixed pool with full trace coverage (G).

## Legacy compatibility

Existing compiler fixtures produce byte-identical results; the staged
engine, policy, and domain records are untouched. No new candidate
field was added, so no hash/trace changed.

## Tests

`tests/test_adapter.py`, 29 tests: conversion cardinality,
no-recomputation, authority/epistemic/scope/provenance preservation,
receipt round-trips, identity determinism and state sensitivity,
no-ranking, dependency remap, no mandatory bands, lose-by-policy,
omit-by-budget, source-swap trace identity (relabelled source_kind
changes no decision), compiler source scans, all seven oracle cases,
mixed-pool trace coverage, legacy determinism, forbidden imports,
one-way import direction, 6A digest and 6B oracle re-verified,
runtime-file truth separation, OpenCode absence, CLI behaviour.

Results: 409 passing at baseline; **438 passing** at finish (29 new),
`ruff check .` clean. No historical artifacts modified; no run outputs
fabricated; no behavioural run executed. No 6B defect was found; no
activation semantics were touched.

## Invariants

Activation is not admission (compiler decides); ledger provenance
never grants privilege (behavioural + scan pins); compiler sources
branch on no origin (pinned); adapter ranks nothing (pinned);
budgets bind adapted candidates like all others.

## What Stage 6C demonstrates

Activated durable state can be presented to the existing compiler as
ordinary context candidates while retaining its important metadata
and without bypassing ordinary compiler decisions.

## What it does NOT demonstrate

Ledger utility, admission correctness, activation ecology, optimal
representation, injection safety/usefulness, extraction.

## Deferred work

Stage 6D (explicit intervention-capable runtime rendering and
injecting a compiler-selected bundle; observer stays read-only;
invocations captured for evaluation) is next and explicitly not
started. F10 is untouched.
