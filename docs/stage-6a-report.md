# Stage 6A report — Context Ledger foundation

## Purpose

Build the persistent state and lifecycle substrate for a future
stateful context runtime, without deciding anything about model
context. Stage 6A demonstrates that typed durable context-state can be
represented, updated, and replayed deterministically. It does not
demonstrate that the state is useful to a model.

Design first: `experiments/designs/F4B-stateful-context-ledger.md`
(question, scope, future conditions C0–C5, null outcomes). No
behavioural run is attached; nothing here is book evidence.

## Architecture

```text
explicit structured state
        ↓  append-only events (JSONL, schema-versioned)
deterministic projection (no clock, no model, no network)
        ↓
LedgerState: items + lifecycle + verification + relationships + lineage

No retrieval. No activation. No compiler admission.
No OpenCode mutation. No model calls.
```

Four concepts stay separate: observation, state, event, context
admission. Stage 6A implements the first three. Persistence is not
admission.

## Records introduced

- `LedgerItem`: `item_id`, kind, statement, authority, scope,
  provenance. Frozen, schema `project_context.ledger_item.v1`, strict
  loader. Fixture IDs are authored constants; live IDs are UUIDs by
  convention; neither derives from secret content.
- Kinds: `obligation | constraint | decision | assumption |
  unresolved_failure | dependency | pending_verification | result`.
- `LedgerScope`: repo/workspace/branch/paths/component/task/session/
  agent, all optional, never inferred. Recorded for Stage 6B; unused
  in 6A.
- `SourceProvenance`: session/invocation/note. Carries no hidden truth.
- Authority: `user | system | project | tool | agent | derived`,
  mapped to the governance channels (`tool` → `tool_output`,
  `agent`/`derived` → `declared`) rather than duplicating them.
- Verification (`unverified | verified | contradicted`) is a separate
  dimension from lifecycle status.

## Lifecycle

`active | blocked | satisfied | failed | superseded | cancelled |
expired | contradicted`. `active ↔ blocked` plus `active/blocked →`
any terminal state; terminal states have no outgoing transitions.
Reopening means a new item and new events, never history mutation.
`TRANSITIONS` in `lifecycle.py`; invalid transitions raise
`LedgerError(invalid_transition)`.

## Event model

`item_created | blocked | unblocked | verified (passed|failed) |
contradicted | satisfied | failed | superseded | cancelled |
expired | relationship_added`. Every event carries `event_id`,
`recorded_at` (projection never reads a clock), and optional
actor/reason/evidence. `verified` records already-supplied evidence;
a `failed` outcome moves the item to `contradicted`, and contradicted
state can never become `verified` (`verification_conflict`).

## Relationships

`depends_on | blocks | supersedes | contradicts | verifies |
derived_from`, stable IDs, directional, no prose inference. Only two
have projection effects: `supersedes` (target → `superseded`) and
`contradicts` (target → `contradicted`); the rest are recorded
lineage. Dependency rule: an unmet `depends_on` target blocks an
active dependent; a blocked dependent whose every dependency is
satisfied or verified returns to active. Met = satisfied or verified.
Nothing is executed; only representable state changes, each recorded
in item history with its cause.

## Fixtures

`fixtures/ledger-v1/` (SYNTHETIC): 24 events, 13 items —
user constraint, conditional docs obligation, decision supersession,
failed race-condition claim, unresolved Windows failure, adapter
obligation with dependency satisfaction, irrelevant telemetry
assumption, expired token obligation, benchmark-vs-cache
contradiction, plus `verifies`/`blocks` lineage. Expected state in
`ledger-v1.truth.json`, read by tests only; runtime sources and the
events file carry no evaluator tokens (pinned by tests).

## CLI

`contextlab ledger inspect|history|validate|replay <fixture-or-store>`
(structural text default, `--format json`). `inspect` groups items by
status; `history` shows the event lineage for one item; `validate`
checks schema, references, transitions, and replay determinism;
`replay` shows the state digest. Fixture output is labelled
`[SYNTHETIC]`; truth is never loaded or printed.

## Tests

`tests/test_ledger.py`, 31 tests: record/event round-trips, strict
loaders, replay determinism, history reconstruction, legal/illegal
transitions, terminality, directional supersession, contradiction
provenance, evidence retention, failed-verification finality,
dependency references and refusal to unblock early, fixture-vs-truth
equality, hidden-truth separation, store round-trip and corruption
behaviour, git-ignored live paths, CLI behaviour and determinism,
forbidden imports, import direction (ledger touches only ledger;
compiler/opencode/evaluation/readers/behavior never touch ledger),
no ledger privilege in the compiler, no ledger presence in OpenCode
capture.

Results: 322 passed at session start (commit `97a2ddc`), 361 passed
at finish (`ebc3052` plus Stage 6A: 330 tracked + 31 new ledger
tests). `ruff check .` clean. No historical artifacts modified; no
run outputs fabricated; no behavioural run executed.

## Privacy boundary

Fixtures are synthetic and labelled at creation, in CLI output, and
in the manifest. Live stores default to `.local/ledger/`
(`LIVE_STORE_DIR`); `.local/` is git-ignored (pinned by test). No
real or private state committed.

## Compiler boundary

Unchanged and unprivileged: the compiler never imports the ledger
(pinned), contains no ledger-specific admission path (pinned), and
the full existing suite passes unmodified. A future activator will
produce ordinary `ContextCandidate[]`; the compiler stays sovereign
over admission.

## OpenCode boundary

`integrations/opencode/` untouched (pinned: no `ledger` string in
its sources); the read-only capture invariant holds; no hook
results, injection, filtering, or rewriting added. A future
intervention-capable integration is explicitly out of scope.

## What Stage 6A demonstrates

Typed durable context-state with lifecycle, provenance, verification,
and relationships can be represented, updated, and replayed
deterministically, with every current state traceable to the events
that caused it.

## What Stage 6A does NOT demonstrate

Usefulness to a model; activation; automatic extraction; compiler
admission; injection outcomes; ecological prevalence or necessity.

## Deferred work

Stages 6B (activation against `ContextRequest`), 6C (compiler
adapter), 6D (runtime injection), 6E (extraction), 6F (behavioural
evaluation against C0–C5), 6G/F10 (full runtime). Only mechanisms
that survive their own families enter F10.

## Deviations and notes

- Repository reality vs the originating prompt: `specs/` and
  `experiments/designs/F4*` live here (not under `spec/…` with an
  experiment-contract split the prompt assumed); naming follows this
  repo (`LedgerError` codes, `project()` projection,
  `ledger-v1.truth.json` mirroring `compiler-v1` truth conventions).
- The prompt's proposed `integrations/opencode-runtime/` was
  documented as a non-goal, not scaffolded: no empty packages.
- Name collision noted: `src/project_context/corpus/ledger.py` (the
  F1 ecological-capture ledger, committed in parallel during this
  session) is a different component from `src/project_context/ledger/`
  (this Context Ledger). A future rename of one of them would avoid
  confusion; Stage 6A changes neither's interface.
- During this session two parallel F1 commits landed on `main`
  (`b4ad7e4`, `ebc3052`, including AGENTS.md rule 41). Stage 6A files
  do not overlap them; final validation ran against the merged tree.
