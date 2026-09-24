# Preregistration

Every experiment family that will produce evidence for the book has a
preregistration: a short document, committed **before** its first evidence run,
that says what will be tested and what the result is allowed to mean. The
commit that freezes it is recorded in the manifest of every run that follows
(`preregistration: <path>@<commit>`, see `specs/experiment-contract.md`).

It extends the frozen `spec.yaml` convention, it does not replace it: the
preregistration is the human-readable argument, `spec.yaml` is the machine
contract derived from it.

## Rules

1. **Freeze before running.** A preregistration has `status: draft` while it is
   being agreed and `status: frozen` once approved. Evidence runs require a
   frozen preregistration, committed and unmodified since.
2. **Never edit a frozen preregistration.** Changes go in a new version
   (`version: 2`) that supersedes it, and runs cite the version they used.
   Deviations that happen during a run go in the `Deviations` section, appended
   and dated, never rewriting the plan.
3. **Exploratory runs are welcome, and labelled.** A run made before freezing,
   or outside the plan, is `run_purpose: exploratory`. It can motivate a
   preregistration; it can never be cited as confirmatory evidence, and it is
   never silently promoted to one.
4. **Null and negative outcomes are designed in.** The plan must say what each
   of these would look like and what the book does in each case: the mechanism
   helps, harms, has no detectable effect, helps only under a stated pressure,
   depends on the reader, or the fixture fails to expose the mechanism.
5. **No self-report as evidence.** A model saying a summary helped, or that it
   ignored a distractor, is stored as a qualitative note. It decides nothing.
6. **Say what it may not support.** Every preregistration ends with the claims
   its result must not be used for.

## Required front matter

```text
family:      F5
title:       short plain name
version:     1
status:      draft | frozen
depends_on:  other families whose outputs it uses
model_calls: none | local | paid
```

## Required sections

```text
## Question
## Hypotheses
## Population
## Intervention and conditions
## Controls
## Measurements
## Trial design and rationale
## Exclusions
## Failure criteria
## Stopping rule
## Analysis plan
## Claims this result may support
## Claims this result may not support
## Deviations
```

`python scripts/check_preregistration.py <files>` checks the structure of
drafts, and for a frozen preregistration also that it is committed and
unmodified. `--commit <file>` prints the commit that froze it.

## Trial counts

Do not pick a repetition count because it is cheap. State the effect worth
detecting, and derive the count from it.

- **Paired conditions on the same task** are analysed on the tasks where the
  outcomes differ (the discordant pairs). With an exact two-sided sign test at
  the 5% level and 80% power, about 20 discordant pairs detect a true 80/20
  split, about 30 detect 75/25, about 49 detect 70/30, and about 12 detect
  90/10. If a comparison disagrees on 30–50% of tasks, that means roughly 40–67
  tasks. The six hand-built tasks in the first behavioural experiment can
  describe, but cannot support an inference; behavioural families therefore use
  a generated task population.
- **A "never happens" claim** needs its bound stated. Zero failures in 30 legitimate
  cases only bounds the true rate below about 11.6%; 60 cases, 6.0%; 100 cases,
  3.6%; 140 cases, 2.6% (95%, exact).
- **Descriptive surveys** are sized on sessions, not invocations: with 24 sessions
  and a between-session standard deviation of 0.10, a mean share is known to about
  ±0.04; at 0.15, about ±0.06.
- **Deterministic components** (compilers, validators, renderers) are checked by
  repeatability, not by stochastic replication: the same inputs must reproduce the
  same bytes.
- **Stochastic readers** at temperature zero are nearly, not perfectly,
  repeatable. Use tasks as the unit of replication, run a small repeat check to
  measure residual nondeterminism, and report per-task outcomes and paired counts
  with exact intervals rather than bare fractions.

## Template

Copy this and fill every section. A section may say "not applicable" only with
a reason.

```text
---
family:
title:
version: 1
status: draft
depends_on: []
model_calls: none
---

# <family> — <title>

## Question
## Hypotheses
## Population
## Intervention and conditions
## Controls
## Measurements
## Trial design and rationale
## Exclusions
## Failure criteria
## Stopping rule
## Analysis plan
## Claims this result may support
## Claims this result may not support
## Deviations
```
