# F3 — Typed transformation ladder (design)

Status: design only. Execution after the ecological corpus and the governance
family. Supports the chapters on retention, pruning, compression and fading.

**Tests:** a mechanism, staged so each step can be attributed.

## Question

When context must shrink, does treating items by type keep what matters better than
treating everything alike, and does each added step earn its place?

## One frozen corpus, not a grab bag

A generated set of at least 40 trajectories, each containing known item types with
hidden probes:

- an exact governing constraint;
- a numeric or configuration value;
- a durable decision with its rationale;
- a large but recoverable source;
- a duplicate observation;
- a stale or superseded item;
- a failed hypothesis;
- verbose tool output;
- narrative history.

Each trajectory ends with later tasks that need particular subsets, so what to keep
is decided before anyone sees the future. Item mixes and sizes come from the shape
cards.

## The ladder

Each rung adds one thing to the previous one, so a difference belongs to that thing.

| Rung | Adds |
|---|---|
| T0 raw | nothing removed (upper bound, subject to length effects) |
| Blunt baselines | blind truncation; uniform summarisation of everything |
| T1 safe removal | remove only what is provably redundant or superseded, with a mechanical placeholder |
| T2 typed compression | plus: keep exact items verbatim; compress the compressible under a keep-list; replace recoverable sources by a reference |
| T3 progressive fidelity | plus: tiers generated once, rendered deterministically as pressure rises |
| T4 oracle | exactly what the later tasks need |

T3 is run only if T2 leaves measurable headroom to the oracle. If it does not, the
fading chapter is reduced without running it.

Pressure is applied at three budgets (about half, a third and a sixth of raw size).

## Confounds

- **The summariser is a second model.** It is a fixed, pinned local model, distinct
  from the readers, and its prompts are frozen. Deterministic extractive
  compression is run beside it, so a typed-policy effect is not just a summariser
  effect.
- **Length.** Token counts are matched across compared rungs wherever possible and
  reported otherwise.
- **Recoverability is a design choice, not a free lunch:** a reference only counts
  if it resolves; unresolved references are scored as loss.

## Measurements: survival first, then behaviour

1. What survived: exact requirements retained, provenance and status retained,
   rationale retained.
2. What changed representation, what disappeared, what remains recoverable.
3. Only then task success, evidence use, constraint adherence, harmful action.
4. Cost of the transformation itself (summariser calls and tokens), net tokens saved,
   and the cache mutation each step would cause (first divergence and radius, computed,
   no provider needed).
5. Failure state per failed case (`LOST` against `UNRECOVERED` against `ABSENT`).

## Size

40 trajectories × 7 conditions × about 6 probes × 2 readers, plus about 120
summariser calls: about 2,600 local calls.

## Null and negative outcomes

- **Typed reduction does not beat uniform summarisation with a keep-list:** the
  typing chapter narrows to "keep-lists matter".
- **T1 saves little on natural shapes:** the pruning chapter becomes a conditional
  pass, with the prevalence measured.
- **T3 adds nothing over T2:** the fading chapter merges into the compression
  chapter.
- **Uniform summarisation does as well as typed:** stated plainly; the retention
  classes are then documentation, not mechanism.

## Depends on

The shape cards (soft); the generated-task machinery; a pinned summariser.
