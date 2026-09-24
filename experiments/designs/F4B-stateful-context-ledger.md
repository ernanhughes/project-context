# F4B — Stateful context ledger (design)

Status: design only. Stage 6A implements representation and lifecycle
mechanics; no behavioural run is attached to this design.

**Tests:** state representation and lifecycle mechanics only. It does not
test whether the ledger improves model behaviour.

## Question

Can agent- or tool-produced information be externalised as typed durable
state while retaining enough provenance, lifecycle, authority and
verification information for later admission decisions?

## Scope

Stage 6A owns only:

```text
events
   ↓
typed ledger state
   ↓
lifecycle transitions
   ↓
provenance
   ↓
relationships
   ↓
deterministic inspection
```

It does **not** claim that the ledger improves model behaviour. It
implements no retrieval, no activation, no compiler admission, no
OpenCode mutation, and no model calls.

## Why this belongs to F4

F4 already separates:

```text
externalisation → admission → recall
```

and carries an arm for agent-authored state with status and provenance.
Stage 6A introduces the state substrate that arm needs: without typed
state, lifecycle, and verification, the seeded-status question
("does an unverified hypothesis persisted without its status get
treated as fact?") cannot be asked rigorously.

F10 will eventually test whether this state mechanism composes with the
rest of the Context Compiler. Only mechanisms that survive their own
family enter F10.

## Core distinction

Four concepts stay separate:

```text
observation          what happened
state                what durable proposition/obligation currently exists
event                what changed that state
context admission    whether this state is shown to a model
```

Stage 6A implements the first three. Persistence is not admission: an
item may exist in the ledger indefinitely and never belong in any
particular context window.

## Future experimental comparison (not executed here)

When activation (Stage 6B) and the compiler adapter (Stage 6C) exist,
trajectories should compare:

```text
C0 no persisted state
C1 full historical context
C2 all unresolved state
C3 task-activated state
C4 activated + Context Compiler
C5 oracle required state
```

Future trajectories should contain useful active state, irrelevant
active state, stale state, superseded state, contradictory state,
unverified claims, failed verification, conditional obligations,
resolved obligations, and scope mismatches. Stage 6A does not test
these behavioural outcomes; it makes them representable.

## Measurements (future; Stage 6A defines no behavioural metrics)

Task success, false admission, missed required state, stale-state use,
contradiction use, requirement survival, token consumption, extra
retrieval calls, harmful action, decision-trace completeness — all per
`specs/measurement-contract.md`, all deferred until Stage 6F.

## Null and negative outcomes

- **The substrate is never used:** if no later family can turn ledger
  state into better bundles, the ledger stays a representation exercise
  and F10 excludes it.
- **All-unresolved beats activated:** the activation stage loses its
  experiment and the ledger feeds the compiler unfiltered or not at all.
- **Status marking changes nothing:** as in F4, the self-generated-state
  material is kept as illustration, not evidence.

## Depends on

F4 (externalisation framing and the status arm); the compiler's
authority vocabulary, which the ledger maps to rather than duplicates.
