---
family: F5
title: Governance gates with derived eligibility
version: 1
status: draft
depends_on: []
model_calls: none
---

# F5 — Governance gates with derived eligibility

Status: **draft, not frozen.** Needs a small build first (see Population).

## Question

Given only candidate metadata and a declared policy, can a deterministic assembler
**derive** whether each candidate may enter (authority, scope, freshness,
provenance), build a valid bundle or refuse, and explain every decision, in cases
where naive assembly builds an invalid bundle?

## Why the first construction experiment does not answer this

In the first construction experiment, each candidate arrived with its authority,
scope and freshness verdicts already resolved as inputs. That result shows the
gates *apply* an eligibility verdict correctly. It does not show that a policy can
*reach* the verdict from metadata, which is the harder and more useful claim. This
family tests the derivation.

## Hypotheses

- **H1 Fixture validity.** On at least 90% of adversarial instances in each class,
  at least one naive strategy produces a violation. If not, that class does not
  expose the mechanism, and it is redesigned before any result counts.
- **H2 Correctness.** The derived-eligibility assembler produces no violation on any
  adversarial instance, as judged by an independent checker.
- **H3 No over-rejection.** On legitimate-need controls (delegated instructions,
  shared dependencies, historical queries) it wrongly rejects none.
- **H4 No invented winner.** Where policy is silent and sources conflict, it
  preserves the conflict, marked unresolved, in every instance.
- **H5 Unknown stays unknown.** Where metadata is missing, the candidate is excluded
  or deferred with an `UNKNOWN` reason, never treated as global, current or
  authorised, in every instance.
- **H6 Explained.** Every inclusion and exclusion carries a reason derived from
  metadata.
- **H7 Deterministic.** Two runs give byte-identical bundles and traces.

## Population

A **generated fixture set**, so that no result depends on a hand-built example. A
generator produces instances from a seed, randomising names and values while
holding the structure fixed. It writes two separate outputs: **metadata**, which the
assembler may see, and **truth**, which only the checker may see.

| Class | What varies | Legitimate control shape |
|---|---|---|
| Authority | the source channel (system, project, user, tool output, quoted text, self-declared rhetoric in a payload); delegation to a vetted revision against a changed one | a delegated runbook the task owner legitimately authorised |
| Scope | two projects or environments with similar but incompatible facts; missing scope | a shared dependency that genuinely serves both |
| Freshness | old and current states; a fast change inside the validity window; a stable source beyond it; a historical query | a historical question that correctly wants the old state |
| Provenance | two contradictory claims with different source authority; a canonical-source policy present, silent, or equal-authority | a corroborating source that must not be dropped |
| Combined | two or three of the above at once, and a tight budget | — |

**Size:** 30 adversarial instances in each of the four single classes, 20 combined,
and 100 legitimate-need controls spread across the classes: **240 instances**.

**Prerequisites to build** (small, deterministic, no model): the instance
generator; the eligibility resolver; an independent checker that reads only the
truth; and a source-scan test that the resolver cannot import truth.

## Intervention and conditions

The independent variable is the assembly strategy. Every strategy sees the same
candidates and the same budget.

| Condition | What it is |
|---|---|
| Dump | admit everything that fits, in arrival order |
| Top-k | rank by relevance, take the top |
| Heuristic gates | gates driven by plausible shortcuts: newest timestamp is authoritative, path prefix decides scope, a source's own rhetoric counts |
| **Derived eligibility** | the resolver, from metadata and declared policy |
| Oracle | the truth, as a ceiling |

Component ablations of the derived-eligibility assembler, each removing one
resolver (authority, scope, freshness, provenance handling) to show which component
prevents which violation.

## Controls

- One budget regime (roomy) so that governance is the only factor, plus a tight
  regime on the combined class to test governance together with infeasibility.
- The same candidates, relevance scores and renderer across conditions.
- Hidden truth never reaches the assembler; the import direction is tested.
- A change to the resolver after seeing failures is a new version and a full replay
  of every instance; earlier results are not edited.

## Measurements

- Violations per class, by the independent checker: authority, scope, freshness,
  provenance handling.
- Outcome correctness: valid bundle, correct refusal, or conflict preserved.
- False-rejection rate on the controls.
- Trace completeness: reason codes present and derived from metadata.
- Attempts by self-declared rhetoric to gain authority, and how many succeeded.
- Determinism: byte equality across two runs.

## Trial design and rationale

The assembler is deterministic, so replication means repeatability, not repeated
sampling. The instance count is chosen for coverage and for bounds:

- each axis level appears in at least 5 instances;
- zero false rejections in 100 controls bounds the true rate below 3.6% (95%,
  exact);
- zero violations in 140 adversarial instances bounds the rate below 2.6%.

## Exclusions

Only instances whose truth fails the generator's own consistency checks, removed
before any strategy runs and counted. Nothing is excluded after results.

## Failure criteria

- **Protocol failure:** an instance in which truth leaks into the assembler input, or
  the two runs differ. The run stops.
- **Fixture failure:** H1 fails for a class. That class is rebuilt and the run
  restarted.
- **Result failure (a valid outcome):** the derived assembler violates a class, or
  over-rejects. Reported as such.

## Stopping rule

Fixed set, one confirmatory run per version. No adaptive stopping.

## Analysis plan

Tables of violations per class and strategy; the per-instance list of every
violation and its cause; the ablation matrix; exact 95% bounds for zero-event
claims; the failure taxonomy applied at bundle level (a bundle that admits an item
whose induced action is forbidden is a `STALE`, `SCOPE_LEAK` or `OVERRIDDEN`
bundle). No aggregate score.

## Claims this result may support

- That a deterministic resolver can derive authority, scope, freshness and
  provenance eligibility from declared metadata and policy on these generated cases,
  and where naive strategies fail on the same cases.
- Which resolver component prevents which violation class.
- That conflicts are preserved rather than silently resolved, and unknown metadata
  is not defaulted.

## Claims this result may not support

- That a reader behaves better with these bundles (a reader run is a separate
  family, using the same instances).
- That the declared policy is the right policy; it is taken as given.
- That real harnesses expose the metadata the resolver needs; the corpus family
  informs that.
- Robustness against forged metadata; metadata is assumed to come from a trusted
  channel.
- Anything about prevalence.

## Deviations

None yet.
