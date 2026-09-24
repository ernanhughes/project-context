# activation-v1 fixtures (SYNTHETIC)

Deterministic activation cases: each case pairs a small append-only
ledger stream with one or more structured `ActivationRequest` inputs.
Expected states live in `truth.json`, which tests and the eval CLI may
read but activation runtime code must never import.

## Layout

```text
cases/<case>/events.jsonl          ledger stream for the case
cases/<case>/requests/<id>.json   ActivationRequest inputs
cases/<case>/truth.json            oracle: request -> item -> state + reasons
heldout/<case>/...                 same layout, produced by the seeded generator
```

## Core cases

| Case | What it proves |
|---|---|
| migration | governed-operation entry activates; unrelated edit leaves it dormant |
| schema | v2 activates on schema work; v1 never activates; frontend work wakes nothing |
| obligation-pre/post | blocked obligation is not actionable; satisfied obligation activates on related work, stays dormant otherwise; a request about the blocking condition wakes it |
| windows-failure | failure activates on related work only |
| pending-claim | unverified claim activates with epistemic status preserved |
| contradicted-claim | contradicted claim never activates, even on its own subject |
| irrelevant-valid | valid + unresolved still means dormant |
| scope-leak | cross-repo lookalikes do not leak; mismatch is ineligible |
| missing-metadata | featureless request and scopeless item abstain as UNKNOWN |
| multi-item | one request wakes several items while leaving others dormant |

## Held-out cases

`held-00`–`held-07` use a disjoint vocabulary (repos, components,
paths) from the core cases. They are produced by
`experiments/activation-v1/generate.py --seed 7` from construction
rules with an independently implemented oracle, and committed. They
test generality (no id memorisation), not correctness.
