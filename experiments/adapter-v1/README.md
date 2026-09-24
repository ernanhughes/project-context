# adapter-v1 — ledger-to-compiler candidate compatibility experiment

SYNTHETIC. NO MODEL CALLS. NOT A BOOK RESULT UNTIL EXPLICITLY PROMOTED.

## Question

Can activated ledger state enter the existing Context Compiler as
ordinary candidates while preserving authority, scope, provenance and
epistemic state, without receiving ledger-specific admission privilege?

## Non-claims

No model behaviour is measured here. A successful result establishes
only that the architectural boundary works: adapted candidates compete
normally. It says nothing about ledger utility, activation ecology,
optimal representation, extraction, or injection.

## Hypotheses (until the run)

- H1: every ACTIVE fixture item converts to exactly one candidate with
  preserved metadata; non-ACTIVE items convert to none.
- H2: adapted candidates admit, lose, or are omitted by budget under
  the unchanged compiler policy across the seven compatibility cases.
- H3: standing differences between adapted candidates derive from
  authority metadata, never from ledger source.

## Falsification

If any adapted candidate is MANDATORY/REQUIRED, ranked by the adapter,
or admitted over budget; if compiler sources branch on ledger origin;
if legacy fixtures change output — the boundary has failed and the
report must say so.

## Layout

```text
experiments/adapter-v1/
  README.md                 this file
  spec.yaml                 frozen contract (see specs/experiment-contract.md)
```

Fixtures live under `fixtures/adapter-v1/` (committed JSON is
canonical). No generator: seven hand-built adversarial cases.

## Reproduce

```text
contextlab ledger candidates <case> --request-file <activation-request> --compile
pytest tests/test_adapter.py
```
