---
family: F8
title: Clean reader-transfer replication
version: 1
status: draft
depends_on: [F5]
model_calls: local
---

# F8 — Clean reader-transfer replication

Status: **draft, not frozen.** Tier 1 can run on existing frozen bundles. Tier 2 waits
for the generated fixtures from F5.

## Question

When the bundle, the task, the wrapper and the decoding settings are all identical,
does the effect of a context policy on behaviour hold across different readers?

This is not a comparison of readers. The purpose is to learn how much of an
observed effect belongs to the bundle and how much to the reader.

## Why the earlier probe is replaced

The first transfer probe changed the reader and the budget together, so its bundles
differed from the ones the first reader saw. Nothing about reader dependence can be
concluded from it. Here only the reader changes.

## Hypotheses

- **H1 Direction transfers.** For each contrast (no context against supplied
  context; naive against governed bundles), the sign of the effect is the same for
  every reader on most tasks.
- **H2 Some outcomes are reader-dependent.** On some cells, the same bundle produces
  different outcomes for different readers.
- **H3 Interactions.** On some tasks the effect of the condition has a different
  sign for different readers.

The result is a partition, not a verdict on any reader. Each cell (a task under a
condition) is labelled:

- **bundle-dependent:** the outcome moves with the condition, in the same direction,
  for every reader;
- **reader-dependent:** with the bundle held fixed, the outcome differs between
  readers;
- **interaction:** the effect of the condition has opposite sign for different
  readers;
- **inert:** the outcome is the same everywhere.

## Population

**Tier 1 (existing bundles, descriptive).** The six frozen tasks under seven bundle
conditions at the tight budget, plus the slice of the mixed-facts fixture at the
medium budget. Bundle bytes come from the first construction experiment and are
verified by digest. Six tasks can describe agreement but cannot support an
inference, and Tier 1 is reported as description.

**Tier 2 (generated, inferential).** The generated fixtures from F5: at least 60
tasks across authority, scope and freshness, each under five bundle conditions
(no context, dump, heuristic gates, derived eligibility, oracle). The reader's
action is a structured choice graded deterministically, for example whether it
takes the forbidden action.

## Intervention and conditions

Only the reader varies. **At least three readers**, each pinned by its recorded
model digest, from different model families and sizes, run locally. All are re-run
in full: no output from the earlier probe or the earlier primary run is reused.

## Controls

Held identical for every reader:

- bundle bytes (digest-verified at run time; a mismatch stops the run);
- task text, wrapper, response schema and grader;
- decoding: temperature 0, the same seed, the same maximum output;
- case schedule, interleaved by task;
- isolation: one fresh request per case, no shared session or memory.

Where a server does not honour the seed, that is recorded per reader.

**Reader selection is fixed before freezing,** by a rule applied to a calibration
task that is not in the confirmatory set: locally served, follows the response
schema, and parses at least 95% of responses. A reader that fails is replaced
before freezing, and never afterwards.

## Measurements

Per case: parse success, the parsed action, task success, harmful action, and the
failure state (from the shared taxonomy) for each failure; plus input and output
tokens, latency and call count. Model identity and digest per reader.

## Trial design and rationale

Tasks are the unit of replication. Two repeats at temperature 0 measure residual
nondeterminism. A sampling arm at temperature 0.7 with five repeats, on Tier 1
only, measures how much outcomes move when sampling is allowed.

**Size of Tier 2.** For a paired contrast analysed on the tasks where the two
outcomes differ, about 20 disagreeing pairs detect a true 80/20 split with 80% power
(about 30 for 75/25). If two conditions disagree on 40–50% of tasks, 60 tasks give
24–30 disagreeing pairs. That is why Tier 2 needs at least 60 tasks and Tier 1
cannot be inferential.

**Volume.** Tier 1: 49 cells, three readers, two repeats, plus the sampling arm,
about 1,000 local calls. Tier 2: 300 cells, three readers, two repeats, about 1,800
local calls. At the earlier mean of about 11 seconds a call, roughly 3 hours and
5.5 hours respectively, and no monetary cost.

## Exclusions

Transport and provider errors are retried with bounded backoff and are not task
failures. Parse failures are outcomes on their own ledger and are never repaired. A
reader is dropped only before freezing, by the selection rule.

## Failure criteria

- **Control failure:** any bundle digest mismatch, or a schedule that differs
  between readers. The run stops and is not used.
- **Reader failure:** a reader parses under 90% of confirmatory responses. Its results
  are reported separately and flagged, never dropped silently.
- **Nondeterminism:** more than 5% disagreement between repeats for a reader. The
  reader's outcomes are then reported as the majority of repeats with the
  disagreement shown.

## Stopping rule

Fixed design. Tier 2 begins only after F5 has passed its own criteria and its
generator is frozen. No adaptive stopping.

## Analysis plan

- Per reader and per contrast: the effect as paired counts with exact 95%
  (Clopper–Pearson) intervals. Never averaged across readers.
- The cell partition above, with counts and proportions, and a table of every
  interaction cell.
- Agreement between readers on identical cells, with the disagreements listed.
- Failure states for failed cells.
- No ranking of readers, and no "best reader" statement.

## Claims this result may support

- Whether the direction of a context policy's effect held across the tested readers
  on the tested tasks.
- Which outcomes depended on the bundle, which on the reader, and where they
  interacted.
- How much residual nondeterminism the readers show.

## Claims this result may not support

- That any reader is better than another.
- That the effect generalises to models not tested, hosted models, or production
  agents.
- That a mechanism helps in real repositories; these are synthetic tasks.
- Anything about cost or latency beyond the local measurements recorded.

## Deviations

None yet.
