# compiler-v1 — deterministic synthetic Context Compiler experiment

SYNTHETIC. NO MODEL CALLS. NOT A BOOK RESULT UNTIL EXPLICITLY PROMOTED.

## Question

Given a fixed heterogeneous candidate pool and finite token budget, can a
deterministic staged compiler produce a policy-valid bundle with higher
required-information coverage and fewer illegal/harmful admissions than
dump, top-k, weighted, and hard-gated greedy baselines?

No behavioural task success is measured here. Chapter 23 owns behaviour;
this experiment owns bundle legality, coverage, budget, and trace.

## Hypotheses (until the run)

- H1: hard eligibility gates reduce policy violations vs dump/top-k/weighted.
- H2: dependency-aware staged assembly avoids locally cheap but globally
  expensive admissions.
- H3: representation alternatives reduce rendered cost while preserving
  legal floors.
- H4: the staged compiler emits explicit failure when no legal bundle exists.
- H5: the staged compiler leaves positive slack when nothing earns admission.

## Falsification

If hard-gated greedy matches staged everywhere, or dependency costing never
changes a choice, or alternatives never reduce cost, or weighted packing is
violation-free, or required groups never matter — the extra mechanism has not
earned itself and the report must say so.

## Layout

```text
experiments/compiler-v1/
  README.md                 this file
  spec.yaml                 frozen contract (see specs/experiment-contract.md)
  weights.json              fixed weighted-baseline weights (never tuned)
  policies/                 versioned compiler policies for backtests
  build_fixtures.py         deterministic fixture generator (run once;
                            committed JSON under fixtures/compiler-v1/ is canonical)
```

## Reproduce

```text
contextlab compiler run compiler-v1 --run-id <id>
contextlab compiler validate-run runs/compiler-v1/<id>
```
