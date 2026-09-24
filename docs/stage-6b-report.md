# Stage 6B report — Context Activation

## Purpose

Add exactly one question to the runtime: given this computation, which
valid ledger items have a reason to wake up? Stage 6B demonstrates that
deterministic activation selects currently relevant durable state while
leaving valid but irrelevant state dormant and rejecting
stale/superseded/contradicted state. It does not demonstrate model
utility.

Design: `experiments/activation-v1/` (frozen eval contract, question,
conditions, measurements, falsification). No behavioural run is
attached; nothing here is book evidence.

## Housekeeping first: the ledger rename

Two unrelated concepts were both named ledger: `corpus/ledger.py`
(ecological session bookkeeping) and `project_context/ledger/` (Stage 6
durable state). Before any 6B code, the ecological component became the
**session index**: `corpus/session_index.py` (`SessionIndex`,
`SessionIndexError`), `Outcome.session_ordinal`, stage
`session_index`, script constants and paths, `experiments/f1/
session-index.public.json`, and matching test/prose updates. Behaviour
is preserved (full suite green throughout); the persisted schema string
`project_context.f1_ledger.v1` is frozen by design with a comment.
From here, **Context Ledger** unambiguously means the Stage 6
mechanism. (The frozen Stage 6A report still names the old path; that
record is left intact.)

## Architecture

```text
Stage 6A:  events → LedgerState
Stage 6B:  LedgerState + ActivationRequest → ActivationResult
Stage 6C:  (future) activated state → ContextCandidate[]
Stage 6D:  (future) compiler output → explicit runtime injection
```

Key invariant: **activation means potentially relevant now; it does
not mean admitted to context.** The activator is not a miniature
compiler: no budget, representation, ordering, rendering, or admission.

## Activation model

Two stages, kept apart. Eligibility (validity): terminal lifecycle →
INELIGIBLE per-status code; contradicted verification → INELIGIBLE;
recorded repo disagreeing on both sides → INELIGIBLE
(`scope_repo_mismatch`, the world boundary). Relevance (typed reasons,
never similarity): `scope_path_match` (either-direction prefix),
`scope_component_match`, `scope_task_match`,
`operation_in_governed_scope` (constraint + recorded operation in its
area), `evidence_match` (recorded evidence ref present now),
`dependency_ready` (obligation modifier, never sufficient alone),
`blocking_condition_relevant` (blocked obligation whose blocker the
request is about), one snapshot propagation pass over `depends_on`
(`dependency_active`, non-propagating). DORMANT when valid without
reason (`no_activation_reason`, or `blocked_dependency_unmet` with the
overlap preserved in `matched_scope`). UNKNOWN abstains:
featureless request (`request_features_absent`) or scopeless item
(`insufficient_scope_to_decide`) — never a guess, never ACTIVE by
default. Repo equality alone never activates; unresolved never implies
relevant. Decisions carry reason codes (sorted), matched scope,
matched dependencies, consulted request features, epistemic marker
(set for assumptions/pending verification, never a promotion), and the
policy id. Output order is item-id sort, not a ranking.

Blocked obligations stay eligible (not ineligible): lifecycle
readiness is a relevance question, answered per request.

## Request features used

`ActivationRequest` (versioned, frozen): repo/workspace/branch,
paths, components, task, operation, evidence_refs — all but the
identities optional, absence never matches. The compiler's
`ContextRequest` was deliberately not reused: it carries budget and
admission fields for a decision activation must not make; Stage 6C
will bridge the two.

## Kind-specific rules

Constraints wake on governed-area entry; decisions on component/task
dependence; failures on touched component/symptom; obligations on
scope plus dependency readiness; assumptions/pending verification wake
with epistemic status attached; results wake on direct requirement
(scope or evidence). Exact semantics per kind are pinned by the core
fixtures.

## Relationship handling

`depends_on` alone propagates (one hop, snapshot, ACTIVE only);
`supersedes`/`contradicts` targets are ineligible by gate;
`verifies`/`blocks`/`derived_from` are recorded lineage with no
activation effect in 6B.

## Fixture family

`fixtures/activation-v1/` (SYNTHETIC): 10 authored core cases
(migration, schema, obligation-pre/post, windows-failure,
pending-claim, contradicted-claim, irrelevant-valid, scope-leak,
missing-metadata, multi-item; 19 requests) plus 8 seeded held-out
cases (40 decisions, disjoint vocabulary) from
`experiments/activation-v1/generate.py --seed 7` with an independent
oracle. Oracle truth is evaluator-only; runtime sources, events, and
requests carry no oracle tokens (pinned).

## Naive baselines

`all_unresolved` (every active/blocked item wakes),
`scope_only` (overlap alone, no validity gate),
`newest` (3 most recent non-terminal, request ignored). Each fails
adversarial families by construction; if any ever matches the oracle
everywhere, the fixtures are too easy.

## Held-out evaluation

Held-out tests generality (no id memorisation), not correctness (core
cases do that). Regeneration is byte-stable (`generate.py --check`).

## Results (offline, deterministic)

Typed policy: precision 1.0, recall 1.0, zero false/missed across all
19 cases (87/87 decisions incl. exact reason codes); UNKNOWN only
where the oracle abstains (12 decisions). Baselines: all_unresolved
P 0.32 with 48 false activations (5 scope leaks); scope_only 13
false, 1 missed, 8 scope leaks, 7 stale and 2 superseded activations;
newest 47 false. Dimensions reported separately; no composite score.

## UNKNOWN behaviour

12/87 typed decisions abstain, all matching the oracle: featureless
requests, and scopeless items against featured requests. Abstention is
measured, not hidden.

## Tests

`tests/test_activation.py`, 33 tests: determinism, round-trips,
terminal/superseded/contradicted exclusion (typed, everywhere),
dormancy of valid-but-irrelevant state, scope activation, repo-mismatch
rejection, repo-equality-insufficiency, UNKNOWN behaviour, dependency
gating, blocking-condition wake, bounded propagation, multi-activation,
epistemic preservation, core + held-out oracle match, held-out
reproducibility, baseline failures, perfect typed precision/recall,
runtime-file and source truth separation, forbidden imports, import
direction (activation touches only activation + ledger; compiler,
opencode, evaluation, readers, behaviour never touch activation),
6A projection digest pinned, no compiler/OpenCode presence.

Results: 376 passing at rename baseline; **409 passing** at finish (33
new), `ruff check .` clean. No historical artifacts modified; no run
outputs fabricated; no behavioural run executed.

## Architectural invariants

Activation never imports the compiler (pinned); the compiler never
imports activation (pinned); ledger 6A behaviour byte-identical
(digest pinned); OpenCode capture read-only and activation-free
(pinned); no model/network calls (pinned); hidden truth never in
runtime (pinned).

## What the result establishes

Structured state can be activated selectively according to explicit
current-task criteria, better than all-state or shallow-scope policies
on the controlled fixtures.

## What it does not establish

Real-world utility, correct extraction, correct compiler admission,
token savings, model gains, ecological prevalence.

## Deferred work

Stage 6C (activated item → ordinary ContextCandidate without
privilege) is next and explicitly not started. F4B remains the
eventual behavioural test: 6B proves structural selectivity; F4B will
ask whether the right unresolved state beats all unresolved state for
a reader.
