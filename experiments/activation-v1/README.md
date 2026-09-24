# activation-v1 — deterministic activation selection experiment

SYNTHETIC. NO MODEL CALLS. NOT A BOOK RESULT UNTIL EXPLICITLY PROMOTED.

## Question

Can deterministic activation select currently relevant durable state
while leaving valid but irrelevant state dormant and rejecting
stale/superseded/contradicted state — better than naive all-state or
shallow-scope policies on controlled fixtures?

## Non-claims

No model behaviour is measured here. A successful result establishes
only that structured state can be activated selectively according to
explicit current-task criteria. It says nothing about real-world
utility, extraction, compiler admission, token savings, or model gains.

## Hypotheses (until the run)

- H1: the typed policy matches the oracle on every core case.
- H2: each naive baseline fails at least one adversarial family
  (all_unresolved on irrelevant state, scope_only on superseded state,
  newest on scope traps).
- H3: the typed policy matches the oracle on held-out generated cases
  (generality, not id memory).

## Falsification

If a naive policy matches the oracle everywhere, the fixture family is
too easy and must be hardened. If the typed policy misses held-out
cases its author did not hand-tune, it is overfit and must be revised,
not patched per case.

## Layout

```text
experiments/activation-v1/
  README.md                 this file
  spec.yaml                 frozen contract (see specs/experiment-contract.md)
  policies/                 versioned activation policy (typed production rule set)
  generate.py               deterministic held-out case generator (seeded;
                            committed output under fixtures/activation-v1/heldout/
                            is canonical)
```

## Reproduce

```text
contextlab ledger eval-activations activation-v1
pytest tests/test_activation.py
uv run python experiments/activation-v1/generate.py --seed 7 --cases 8 --check
```
