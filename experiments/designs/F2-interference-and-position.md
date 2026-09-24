# F2 — Interference and position (design)

Status: design only. Execution deferred until the ecological corpus has been analysed.
Supports the chapters on more context, order, and (partly) the layers of the stack.

**Tests:** a mechanism (what extra material and its placement do to use of the
decisive fact).

## Question

Holding the decisive fact fixed, how do the *amount*, the *kind* and the *placement*
of surrounding material change whether a reader finds and uses it?

## What is separated (and must stay separated)

Five factors, never varied together:

| Factor | Levels |
|---|---|
| Volume of irrelevant material | none, small, medium, large (in tokens, fixed in advance) |
| Kind of extra material | irrelevant, plausible but unrelated, near-miss or superseded |
| Position of the decisive fact | five normalised positions from first to last |
| Adjacency | claim next to its evidence, or separated by a fixed span |
| Grouping | related items contiguous, or dispersed |

**Rule against confounding:** each experiment varies one factor. A small factorial
(volume × kind) is allowed only as a pre-declared crossing. Distractor placement is
frozen or counterbalanced across position conditions, so a position effect cannot be
an interference effect in disguise.

## Population

A generated task set (at least 50 tasks): a small project fact must be extracted and
applied (a configuration value, a constraint, an identifier). Distractor material is
recreated from the shape cards the ecological corpus produced: duplicate reads,
superseded documents, near-identical values.

## Conditions and controls

- Minimal bundle (decisive fact only) is the baseline for every task.
- Total tokens are matched across position conditions; the token difference is
  reported.
- Bundle bytes are frozen and digest-verified; two pinned readers.
- The "one plausible extra document" comparison from the opening chapter is simply
  the smallest cell of the kind × volume crossing.

## Measurements

Evidence use, task success, unsupported claim, abstention, latency, rendered tokens;
the failure state for each failure (`UNRECOVERED`, `MISAPPLIED`, `INTERFERENCE`; not
`ABSENT`, because the fact is always present).

## Size

At least 50 tasks per contrast so that a moderate effect is detectable; about 1,600
local calls.

## Null and negative outcomes

- **No gradient across readers:** the chapters reduce to the external evidence,
  and the "canonical layout" becomes a stated preference, not a rule.
- **Position matters, kind does not (or the reverse):** the chapter keeps only the
  factor that moved.
- **Interference only for the weaker reader:** stated as reader-dependent.

## What would remove or merge a chapter

If neither position nor kind produces a detectable effect on either reader, the
position chapter merges into the interference chapter as a short section of
external evidence, and the fixtures are kept only as teaching tools.

## Depends on

The shape cards from the ecological corpus (soft), the generated task machinery
shared with the governance family.
