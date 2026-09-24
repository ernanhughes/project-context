# F4 — Externalise, admit, recall (design)

Status: design only. Execution after the transformation family. Supports the
chapters on externalisation, admission, self-generated state and memory as a source.

**Tests:** a mechanism made of three separate decisions, plus a boundary.

## Question

Can information leave the live context, stay recoverable, and come back at the right
moment, and does that beat keeping it resident?

## Three decisions, kept apart

```text
externalisation   where the information lives, and whether it can be recovered
admission         whether it enters this bundle
recall            how a need triggers its return
```

A good retriever must not hide a bad externalisation, and an oracle query must not
make recall look solved. So each decision is scored on its own.

## Population

At least 40 generated tasks, each following the same arc: the information starts
resident, is externalised with a durable pointer, later becomes relevant, and must be
re-admitted. Each task also has decoy pointers, and some tasks never need the
externalised item (the restraint case, including a remembered fact that is valid but
unnecessary).

The candidate pool is **frozen** in every task, so retrieval quality is never a
variable.

## Conditions

| Condition | What it is |
|---|---|
| N0 resident | never externalised (control) |
| N1 pointer only | externalised, never returned (lower bound) |
| N2 oracle recall | returned by a deterministic trigger that knows the need (upper bound) |
| N3 rule recall | returned by declared rules (an identifier or scope is mentioned) |
| N4 reader-requested | the reader chooses a load from a list, executed by a simulator |

A separate arm admits agent-authored state and remembered items through the same
candidate interface, with their status and provenance attached, to test the null path
(admit nothing) and the seeded-error case: does an unverified hypothesis persisted
without its status get treated as fact?

## Measurements

- Was the material recoverable: pointer resolves, right version, intact bytes,
  provenance kept (deterministic).
- Recall rate and false admission.
- Tokens saved while the item is absent, and tokens spent to bring it back.
- Task success and failure state (`ABSENT` against `LOST` against `UNRECOVERED`).
- Recovery cost in extra calls.

## Boundary with long-term memory

This experiment concerns relocating and re-admitting context *during* a computation.
It says nothing about consolidating, ranking or forgetting a durable store across
sessions. That belongs to the memory work and is out of scope here.

## Size

About 40 tasks × 5 conditions × 2 readers, plus the status arm: about 600 local
calls.

## Null and negative outcomes

- **Resident (N0) wins under realistic budgets:** externalisation is described as
  pressure-conditional, and the chapters keep the accounting, not the mechanism.
- **Recall triggers are the whole story (N2 ≫ N3, N4):** the recall chapter becomes
  about triggers, and admission is thin.
- **The status marking changes nothing:** the self-generated-state chapter loses its
  experiment and is kept as an illustration.
- **Pointer integrity fails often:** the chapter's main finding is how references
  break.

## Depends on

The shape cards, and the pressure-prevalence trigger from the ecological corpus (if
sessions rarely near the window, these chapters are framed as conditional).
